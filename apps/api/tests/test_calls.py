"""Regression tests for calls."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.models.call_session import VoiceCallSession
from app.models.organization import Organization
from app.services.telephony.call_session_service import get_daily_call_logs
from app.services.telephony.token_service import generate_livekit_token
from app.services.telephony.twilio_service import handle_twilio_inbound, handle_twilio_status
from app.services.voice.call_logger_service import (
    _TURN_QUEUE,
    finalize_voice_session,
    flush_pending_turns,
    initialize_call_session,
    queue_voice_turn,
)


def test_token_service_generates_canonical_call_id():
    async def _runner():
        org_id = uuid.uuid4()
        mock_org = Organization(id=org_id, name="City Clinic", closure_notice=None)

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_org)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]
        mock_db.commit = AsyncMock()

        maker = MagicMock()
        maker.return_value.__aenter__.return_value = mock_db
        maker.return_value.__aexit__.return_value = None

        with (
            patch("app.services.telephony.token_service.AsyncSessionLocal", maker),
            patch("app.services.telephony.token_service.enforce_voice_demo_allowance", AsyncMock(return_value=120)),
            patch("app.services.telephony.token_service.LIVEKIT_SDK_AVAILABLE", True),
            patch("app.services.telephony.token_service.AccessToken") as mock_token_cls,
            patch(
                "app.services.infra.redis_cache.presence_service.get_first_available_staff",
                MagicMock(return_value=None),
            ),
            patch("app.services.telephony.token_service.ws_manager.broadcast_to_org", AsyncMock()),
        ):
            mock_builder = MagicMock()
            mock_builder.to_jwt.return_value = "mock_jwt_token"
            mock_token_cls.return_value = mock_builder

            response = await generate_livekit_token(
                org_id=str(org_id),
                phone_number="+919876543210",
                caller_name="Test Caller",
            )

            assert response.call_id is not None
            parsed_id = uuid.UUID(response.call_id)
            assert str(parsed_id) == response.call_id
            assert response.room_name == f"call_{parsed_id.hex}"

            added_session = None
            for call_args in mock_db.add.call_args_list:
                obj = call_args[0][0]
                if isinstance(obj, VoiceCallSession):
                    added_session = obj
                    break

            assert added_session is not None
            assert added_session.id == parsed_id
            assert added_session.room_name == f"call_{parsed_id.hex}"
            assert added_session.triage_status == "ringing"
            assert added_session.call_outcome == "inquiry"
            assert added_session.attended_by == "Unattended / Missed"

    asyncio.run(_runner())


def test_agent_initialize_matches_canonical_call_row():
    async def _runner():
        canonical_call_id = uuid.uuid4()
        org_id = uuid.uuid4()
        room_name = f"call_{canonical_call_id.hex}"

        existing_session = VoiceCallSession(
            id=canonical_call_id,
            org_id=org_id,
            caller_phone="+919876543210",
            room_name=room_name,
            triage_status="ringing",
            call_outcome="inquiry",
            attended_by="Unattended / Missed",
        )

        mock_db = AsyncMock()
        mock_db.scalar.return_value = existing_session
        mock_db.execute.return_value = MagicMock(
            scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=existing_session)))
        )

        maker = MagicMock()
        maker.return_value.__aenter__.return_value = mock_db
        maker.return_value.__aexit__.return_value = None

        with patch("app.core.database.AsyncSessionLocal", maker):
            matched_id = await initialize_call_session(
                org_id=org_id,
                room_name=room_name,
                caller_phone="+919876543210",
                call_session_id=canonical_call_id,
            )

            assert matched_id == canonical_call_id
            mock_db.add.assert_not_called()

    asyncio.run(_runner())


def test_twilio_inbound_and_status_idempotency():
    async def _runner():
        org_id = uuid.uuid4()
        called_number = "+919876543211"
        caller_number = "+919876500000"
        call_sid = "CA1234567890abcdef"

        mock_org = Organization(id=org_id, name="City Health", phone=called_number)
        captured_session = None

        mock_inbound_db = AsyncMock()
        mock_inbound_db.execute.side_effect = [
            MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_org)))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))),
        ]

        def _capture_add(obj):
            nonlocal captured_session
            if isinstance(obj, VoiceCallSession):
                captured_session = obj

        mock_inbound_db.add = MagicMock(side_effect=_capture_add)
        mock_inbound_db.commit = AsyncMock()

        inbound_maker = MagicMock()
        inbound_maker.return_value.__aenter__.return_value = mock_inbound_db
        inbound_maker.return_value.__aexit__.return_value = None

        with (
            patch("app.services.telephony.twilio_service.enforce_voice_demo_allowance", AsyncMock(return_value=120)),
            patch("app.services.telephony.twilio_service.ws_manager.broadcast_to_org", AsyncMock()),
        ):
            response = await handle_twilio_inbound(
                From=caller_number,
                To=called_number,
                CallSid=call_sid,
                CallerName="Twilio Caller",
                session_factory=inbound_maker,
            )

            assert response.status_code == 200
            assert captured_session is not None
            assert captured_session.id is not None
            assert call_sid in captured_session.room_name
            assert captured_session.triage_status == "ringing"
            assert captured_session.call_outcome == "inquiry"
            assert f"X-Call-Id={captured_session.id}" in response.body.decode()

            mock_status_db = AsyncMock()
            mock_status_db.execute.return_value = MagicMock(
                scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=captured_session)))
            )
            mock_status_db.commit = AsyncMock()

            status_maker = MagicMock()
            status_maker.return_value.__aenter__.return_value = mock_status_db
            status_maker.return_value.__aexit__.return_value = None

            with patch("app.services.telephony.twilio_service.AsyncSessionLocal", status_maker):
                result = await handle_twilio_status(
                    CallSid=call_sid,
                    CallStatus="canceled",
                    CallDuration="0",
                )

                assert result["status"] == "recorded"
                assert captured_session.triage_status == "missed"
                assert captured_session.call_outcome == "caller_abandoned"
                assert captured_session.attended_by == "Unattended / Missed"
                mock_status_db.commit.assert_awaited()

    asyncio.run(_runner())


def test_finalize_voice_session_writes_transcript_and_turns():
    async def _runner():
        session_id = uuid.uuid4()
        org_id = uuid.uuid4()
        existing_session = VoiceCallSession(
            id=session_id,
            org_id=org_id,
            caller_phone="+919876543210",
            start_time=datetime.now(timezone.utc) - timedelta(seconds=70),
            triage_status="IN_PROGRESS",
            call_outcome="inquiry",
            attended_by="Unattended / Missed",
        )

        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=existing_session))
        mock_db.commit = AsyncMock()

        turns_data = [
            {"role": "user", "text": "Hello, I want to book an appointment with Dr. Rao."},
            {"role": "agent", "text": "Sure, Dr. Rao is available at 10 AM tomorrow. Should I book it?"},
            {"role": "user", "text": "Yes, please confirm."},
            {"role": "agent", "text": "Your appointment is confirmed for 10 AM tomorrow."},
        ]
        full_transcript = (
            "Caller: Hello, I want to book an appointment with Dr. Rao.\n"
            "Receptionist: Sure, Dr. Rao is available at 10 AM tomorrow. Should I book it?\n"
            "Caller: Yes, please confirm.\n"
            "Receptionist: Your appointment is confirmed for 10 AM tomorrow."
        )

        finalized = await finalize_voice_session(
            db=mock_db,
            session_id=session_id,
            call_outcome="appointment_booked",
            triage_status="completed",
            duration_seconds=70,
            attended_by="Handled by Tulsi (AI)",
            full_transcript=full_transcript,
            turns=turns_data,
            total_turns=4,
            chief_complaint="General consultation booking",
            caller_name="Ananya Rao",
        )

        assert finalized is not None
        assert finalized.call_outcome == "appointment_booked"
        assert finalized.triage_status == "completed"
        assert finalized.attended_by == "Handled by Tulsi (AI)"
        assert finalized.duration_seconds == 70
        assert finalized.total_turns == 4
        assert finalized.turns == turns_data
        assert finalized.full_transcript == full_transcript
        assert finalized.caller_name == "Ananya Rao"
        assert finalized.chief_complaint == "General consultation booking"
        mock_db.commit.assert_awaited_once()

    asyncio.run(_runner())


def test_flush_pending_turns_persists_queue_cleanly():
    async def _runner():
        while not _TURN_QUEUE.empty():
            _TURN_QUEUE.get_nowait()

        session_id = uuid.uuid4()
        org_id = uuid.uuid4()

        queue_voice_turn(
            session_id=session_id,
            org_id=org_id,
            turn_number=1,
            user_transcript="I need an appointment",
        )
        queue_voice_turn(
            session_id=session_id,
            org_id=org_id,
            turn_number=2,
            ai_response_text="Certainly, what time works for you?",
        )

        assert _TURN_QUEUE.qsize() == 2

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        await flush_pending_turns(db=mock_db)

        assert _TURN_QUEUE.empty()
        mock_db.execute.assert_awaited_once()
        mock_db.commit.assert_awaited_once()

    asyncio.run(_runner())


def test_daily_call_logs_serialization_includes_transcript_and_turns():
    async def _runner():
        org_id = uuid.uuid4()
        session_id = uuid.uuid4()

        session = VoiceCallSession(
            id=session_id,
            org_id=org_id,
            caller_phone="+919876543210",
            caller_name="Ananya Rao",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            duration_seconds=95,
            triage_status="completed",
            call_outcome="appointment_booked",
            attended_by="Handled by Tulsi (AI)",
            total_turns=4,
            turns=[{"role": "user", "text": "Booking"}, {"role": "agent", "text": "Confirmed"}],
            full_transcript="Caller: Booking\nReceptionist: Confirmed",
            chief_complaint="Fever checkup",
        )

        mock_db = AsyncMock()
        mock_db.get.return_value = SimpleNamespace(timezone="Asia/Kolkata", ai_voice_name="Tulsi")
        counts = dict(
            historical=1,
            today=1,
            missed_today=0,
            emergency_today=0,
            human_today=0,
            ai_today=1,
            scope_all=1,
            scope_missed=0,
            scope_emergency=0,
            scope_ai=1,
        )
        mock_db.execute.side_effect = [
            MagicMock(mappings=MagicMock(return_value=MagicMock(one=MagicMock(return_value=counts)))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[session])))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[session.id])))),
        ]

        maker = MagicMock()
        maker.return_value.__aenter__.return_value = mock_db
        maker.return_value.__aexit__.return_value = None

        result = await get_daily_call_logs(str(org_id), session_factory=maker)

        log = result["logs"][0]
        assert log["id"] == str(session_id)
        assert log["call_outcome"] == "appointment_booked"
        assert log["full_transcript"] == "Caller: Booking\nReceptionist: Confirmed"
        assert log["total_turns"] == 4
        assert len(log["turns"]) == 2

    asyncio.run(_runner())


def test_twilio_inbound_webhook_idempotency_on_retry():
    async def _runner():
        org_id = uuid.uuid4()
        called_number = "+919876543211"
        caller_number = "+919876500000"
        call_sid = "CA_RETRY_123456789"

        mock_org = Organization(id=org_id, name="City Health", phone=called_number)
        created_session = None

        mock_db = AsyncMock()

        def _capture_add(obj):
            nonlocal created_session
            if isinstance(obj, VoiceCallSession):
                created_session = obj

        mock_db.add = MagicMock(side_effect=_capture_add)
        mock_db.commit = AsyncMock()

        inbound_maker = MagicMock()
        inbound_maker.return_value.__aenter__.return_value = mock_db
        inbound_maker.return_value.__aexit__.return_value = None

        mock_db.execute.side_effect = [
            MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_org)))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))),
        ]

        with (
            patch("app.services.telephony.twilio_service.enforce_voice_demo_allowance", AsyncMock(return_value=120)),
            patch("app.services.telephony.twilio_service.ws_manager.broadcast_to_org", AsyncMock()),
        ):
            res1 = await handle_twilio_inbound(
                From=caller_number,
                To=called_number,
                CallSid=call_sid,
                CallerName="Retry Caller",
                session_factory=inbound_maker,
            )

            assert res1.status_code == 200
            assert created_session is not None
            assert mock_db.add.call_count == 1
            first_session_id = created_session.id

            mock_db.execute.side_effect = [
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_org)))),
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=created_session)))),
            ]

            res2 = await handle_twilio_inbound(
                From=caller_number,
                To=called_number,
                CallSid=call_sid,
                CallerName="Retry Caller",
                session_factory=inbound_maker,
            )

            assert res2.status_code == 200
            assert mock_db.add.call_count == 1
            assert f"X-Call-Id={first_session_id}" in res2.body.decode()

    asyncio.run(_runner())


def test_ringing_cut_call_is_classified_as_missed():
    org_id = uuid.uuid4()
    session = VoiceCallSession(
        id=uuid.uuid4(),
        org_id=org_id,
        caller_phone="+919876543212",
        start_time=datetime.now(timezone.utc),
        end_time=None,
        duration_seconds=0,
        triage_status="ringing",
        call_outcome="ringing",
        attended_by="Unattended / Missed",
        full_transcript="",
    )

    db = AsyncMock()
    db.get.return_value = SimpleNamespace(timezone="Asia/Kolkata", ai_voice_name="Tulsi")
    counts = dict(
        historical=1,
        today=1,
        missed_today=1,
        emergency_today=0,
        human_today=0,
        ai_today=0,
        scope_all=1,
        scope_missed=1,
        scope_emergency=0,
        scope_ai=0,
    )
    db.execute.side_effect = [
        MagicMock(mappings=MagicMock(return_value=MagicMock(one=MagicMock(return_value=counts)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[session])))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
    maker = MagicMock()
    maker.return_value.__aenter__.return_value = db

    result = asyncio.run(get_daily_call_logs(str(org_id), session_factory=maker))

    log = result["logs"][0]
    assert log["is_missed"] is True
    assert log["triage_status"] == "MISSED"
    assert log["handled_by"] == "Unattended / Missed"
    assert log["duration_seconds"] == 0


def test_emergency_call_classification():
    org_id = uuid.uuid4()
    session = VoiceCallSession(
        id=uuid.uuid4(),
        org_id=org_id,
        caller_phone="+919876543212",
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc),
        duration_seconds=45,
        triage_status="emergency",
        call_outcome="emergency_deflected",
        attended_by="AI Receptionist",
        chief_complaint="Patient having severe chest pain and breathlessness. Advised 108.",
        full_transcript="Help, I have severe chest pain and cannot breathe.",
    )

    db = AsyncMock()
    db.get.return_value = SimpleNamespace(timezone="Asia/Kolkata", ai_voice_name="Tulsi")
    counts = dict(
        historical=1,
        today=1,
        missed_today=0,
        emergency_today=1,
        human_today=0,
        ai_today=1,
        scope_all=1,
        scope_missed=0,
        scope_emergency=1,
        scope_ai=1,
    )
    db.execute.side_effect = [
        MagicMock(mappings=MagicMock(return_value=MagicMock(one=MagicMock(return_value=counts)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[session])))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
    maker = MagicMock()
    maker.return_value.__aenter__.return_value = db

    result = asyncio.run(get_daily_call_logs(str(org_id), session_factory=maker))

    log = result["logs"][0]
    assert log["is_missed"] is False
    assert log["triage_status"] == "EMERGENCY"
    assert log["handled_by"] == "Handled by Tulsi (AI)"
    assert log["duration_seconds"] == 45


def test_attended_ai_inquiry_call_classification():
    org_id = uuid.uuid4()
    session = VoiceCallSession(
        id=uuid.uuid4(),
        org_id=org_id,
        caller_phone="+919876543212",
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc),
        duration_seconds=120,
        triage_status="admin",
        call_outcome="inquiry",
        attended_by="AI Receptionist",
        chief_complaint="Inquired about doctor consultation timings and fees.",
        full_transcript="What time does Dr. Sharma consult tomorrow?",
    )

    db = AsyncMock()
    db.get.return_value = SimpleNamespace(timezone="Asia/Kolkata", ai_voice_name="Tulsi")
    counts = dict(
        historical=1,
        today=1,
        missed_today=0,
        emergency_today=0,
        human_today=0,
        ai_today=1,
        scope_all=1,
        scope_missed=0,
        scope_emergency=0,
        scope_ai=1,
    )
    db.execute.side_effect = [
        MagicMock(mappings=MagicMock(return_value=MagicMock(one=MagicMock(return_value=counts)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[session])))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
    maker = MagicMock()
    maker.return_value.__aenter__.return_value = db

    result = asyncio.run(get_daily_call_logs(str(org_id), session_factory=maker))

    log = result["logs"][0]
    assert log["is_missed"] is False
    assert log["triage_status"] == "ADMIN"
    assert log["handled_by"] == "Handled by Tulsi (AI)"
    assert log["duration_seconds"] == 120


@pytest.mark.parametrize("booked", [False, True])
def test_call_logs_match_booking_by_session_uuid(booked):
    org_id = uuid4()
    session_id = uuid4()
    session = VoiceCallSession(
        id=session_id,
        org_id=org_id,
        caller_phone="+919876543210",
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc),
        duration_seconds=0,
        triage_status="missed",
        call_outcome="missed",
    )
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(timezone="Asia/Kolkata")
    counts = dict(
        historical=201,
        today=180,
        missed_today=0 if booked else 1,
        emergency_today=0,
        human_today=0,
        ai_today=180 if booked else 179,
        scope_all=201,
        scope_missed=0 if booked else 1,
        scope_emergency=0,
        scope_ai=201 if booked else 200,
    )
    db.execute.side_effect = [
        MagicMock(mappings=MagicMock(return_value=MagicMock(one=MagicMock(return_value=counts)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[session])))),
        MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[session_id] if booked else [])))
        ),
    ]
    maker = MagicMock()
    maker.return_value.__aenter__.return_value = db

    result = asyncio.run(get_daily_call_logs(str(org_id), session_factory=maker))

    query = db.execute.call_args_list[2].args[0]
    compiled = query.compile(dialect=postgresql.dialect())
    assert compiled.params["org_id_1"] == org_id
    assert compiled.params["call_session_id_1"] == [session_id]
    assert compiled.params["source_1"] == "ai_voice"
    assert result["logs"][0]["call_outcome"] == ("appointment_booked" if booked else "missed")
    assert result["logs"][0]["is_missed"] is not booked
    assert result["metrics"]["missed_calls"] == (0 if booked else 1)
    assert result["metrics"]["total_calls_historical"] == 201
    assert result["metrics"]["total_calls_today"] == 180
    assert result["has_more"] is True
    page_query = db.execute.call_args_list[1].args[0].compile(dialect=postgresql.dialect())
    assert page_query.params["param_1"] == 50
    assert page_query.params["param_2"] == 0


def test_empty_call_logs_skip_booking_query():
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(timezone="UTC")
    counts = dict.fromkeys(
        [
            "historical",
            "today",
            "missed_today",
            "emergency_today",
            "human_today",
            "ai_today",
            "scope_all",
            "scope_missed",
            "scope_emergency",
            "scope_ai",
        ],
        0,
    )
    db.execute.side_effect = [
        MagicMock(mappings=MagicMock(return_value=MagicMock(one=MagicMock(return_value=counts)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
    maker = MagicMock()
    maker.return_value.__aenter__.return_value = db

    result = asyncio.run(get_daily_call_logs(str(uuid4()), session_factory=maker))

    assert result["logs"] == []
    assert result["metrics"]["total_calls_today"] == 0
    assert db.execute.await_count == 2
