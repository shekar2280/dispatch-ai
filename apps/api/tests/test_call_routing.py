"""Regression tests for call routing."""

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import get_current_tenant_org, get_current_user
from app.core.telephony_security import validate_twilio_request
from app.main import app
from app.models.call_session import CallLog, VoiceCallSession
from app.models.organization import Organization
from app.models.user import User
from app.services.telephony.twilio_service import (
    handle_twilio_dial_status,
    handle_twilio_inbound,
    handle_twilio_sip_status,
    handle_twilio_status,
)
from app.services.voice.call_logger_service import _TURN_QUEUE, flush_pending_turns, queue_voice_turn


@pytest.fixture
def mock_twilio_auth():
    app.dependency_overrides[validate_twilio_request] = lambda: True
    yield
    app.dependency_overrides.pop(validate_twilio_request, None)


def test_twilio_signature_missing_returns_403():
    async def _runner():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/telephony/twilio/inbound", data={"From": "+1234567890", "To": "+916302296868"}
            )
            assert resp.status_code == 403
            assert "Missing X-Twilio-Signature" in resp.json()["detail"]

    asyncio.run(_runner())


def test_inbound_routing_unregistered_number():
    async def _runner():
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        )
        maker = MagicMock()
        maker.return_value.__aenter__.return_value = mock_db
        maker.return_value.__aexit__.return_value = None

        resp = await handle_twilio_inbound(
            From="+19999999999",
            To="+10000000000",
            CallSid="CA_unregistered_123",
            session_factory=maker,
        )

        assert resp.status_code == 200
        assert resp.media_type == "application/xml"
        assert "This number is not registered" in resp.body.decode("utf-8")
        assert "<Hangup/>" in resp.body.decode("utf-8")

    asyncio.run(_runner())


def test_inbound_routing_registered_generates_dual_callback_twiml():
    async def _runner():
        org_id = uuid.uuid4()
        mock_org = Organization(id=org_id, name="City Clinic", phone="+916302296868")

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.execute.side_effect = [
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_org])))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))),
        ]

        maker = MagicMock()
        maker.return_value.__aenter__.return_value = mock_db
        maker.return_value.__aexit__.return_value = None

        call_sid = "CA_inbound_success_999"
        with (
            patch("app.services.telephony.twilio_service.enforce_voice_demo_allowance", AsyncMock(return_value=120)),
            patch("app.services.telephony.twilio_service.ws_manager.broadcast_to_org", AsyncMock()),
        ):
            resp = await handle_twilio_inbound(
                From="+19876543210",
                To="+916302296868",
                CallSid=call_sid,
                CallerName="Jane Doe",
                session_factory=maker,
            )

            assert resp.status_code == 200
            twiml = resp.body.decode("utf-8")
            assert 'action="/api/v1/telephony/twilio/dial-status"' in twiml
            assert f'statusCallback="/api/v1/telephony/twilio/sip-status?parent_call_sid={call_sid}"' in twiml
            assert "statusCallbackEvent=" in twiml
            assert "<Sip" in twiml

            added_call = None
            for call_args in mock_db.add.call_args_list:
                obj = call_args[0][0]
                if isinstance(obj, VoiceCallSession):
                    added_call = obj
                    break

            assert added_call is not None
            assert added_call.call_status == "ringing"
            assert added_call.triage_status == "ringing"
            assert added_call.start_time is not None
            assert added_call.connected_at is None
            expected_id = uuid.uuid5(uuid.NAMESPACE_OID, call_sid)
            assert added_call.id == expected_id

    asyncio.run(_runner())


def test_child_sip_progress_sets_connected_at():
    async def _runner():
        parent_call_sid = "CA_sip_progress_123"
        canonical_id = uuid.uuid5(uuid.NAMESPACE_OID, parent_call_sid)

        mock_call = CallLog(
            id=canonical_id,
            org_id=uuid.uuid4(),
            caller_phone="+1234567890",
            call_status="ringing",
            connected_at=None,
        )

        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(
            scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_call)))
        )
        mock_db.commit = AsyncMock()

        maker = MagicMock()
        maker.return_value.__aenter__.return_value = mock_db
        maker.return_value.__aexit__.return_value = None

        result = await handle_twilio_sip_status(
            parent_call_sid=parent_call_sid,
            CallSid="CA_child_sip_456",
            CallStatus="answered",
            session_factory=maker,
        )

        assert result["status"] == "recorded"
        assert mock_call.call_status == "in_progress"
        assert mock_call.connected_at is not None
        mock_db.commit.assert_awaited_once()

    asyncio.run(_runner())


def test_dial_status_completed_and_missed():
    async def _runner():
        parent_call_sid = "CA_dial_terminal_789"
        canonical_id = uuid.uuid5(uuid.NAMESPACE_OID, parent_call_sid)

        mock_call = CallLog(
            id=canonical_id,
            org_id=uuid.uuid4(),
            caller_phone="+1234567890",
            call_status="in_progress",
            duration_seconds=0,
            end_time=None,
        )

        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(
            scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_call)))
        )
        mock_db.commit = AsyncMock()

        maker = MagicMock()
        maker.return_value.__aenter__.return_value = mock_db
        maker.return_value.__aexit__.return_value = None

        resp = await handle_twilio_dial_status(
            CallSid=parent_call_sid,
            DialCallSid="CA_child_leg_789",
            DialCallStatus="completed",
            DialCallDuration="42",
            session_factory=maker,
        )

        assert resp.status_code == 200
        assert "<Hangup/>" in resp.body.decode("utf-8")
        assert mock_call.call_status == "completed"
        assert mock_call.duration_seconds == 42
        assert mock_call.end_time is not None

        completed_at = mock_call.end_time
        resp_missed = await handle_twilio_dial_status(
            CallSid=parent_call_sid,
            DialCallSid="CA_child_leg_789",
            DialCallStatus="busy",
            DialCallDuration="0",
            session_factory=maker,
        )
        # A late contradictory webhook cannot downgrade a completed call.
        assert mock_call.call_status == "completed"
        assert mock_call.end_time == completed_at
        assert mock_call.duration_seconds == 42

    asyncio.run(_runner())


def test_parent_status_reconciliation_preserves_emergency():
    async def _runner():
        parent_call_sid = "CA_parent_status_emergency_111"
        canonical_id = uuid.uuid5(uuid.NAMESPACE_OID, parent_call_sid)

        mock_call = CallLog(
            id=canonical_id,
            org_id=uuid.uuid4(),
            caller_phone="+1234567890",
            room_name=f"call_{canonical_id.hex}_{parent_call_sid}",
            call_status="in_progress",
            triage_status="EMERGENCY",
            call_outcome="escalated_to_emergency",
            duration_seconds=10,
            end_time=None,
        )

        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(
            scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_call)))
        )
        mock_db.commit = AsyncMock()

        maker = MagicMock()
        maker.return_value.__aenter__.return_value = mock_db
        maker.return_value.__aexit__.return_value = None

        resp = await handle_twilio_status(
            CallSid=parent_call_sid,
            CallStatus="completed",
            CallDuration="95",
            session_factory=maker,
        )

        assert resp["status"] == "recorded"
        assert mock_call.call_status == "completed"
        assert mock_call.duration_seconds == 95
        assert mock_call.triage_status == "EMERGENCY"
        assert mock_call.call_outcome == "escalated_to_emergency"

    asyncio.run(_runner())


def test_session_scoped_turn_flush_and_failure_resilience():
    async def _runner():
        while not _TURN_QUEUE.empty():
            _TURN_QUEUE.get_nowait()

        session_a = uuid.uuid4()
        session_b = uuid.uuid4()
        org_id = uuid.uuid4()

        queue_voice_turn(session_id=session_a, org_id=org_id, turn_number=1, user_transcript="Turn 1 A")
        queue_voice_turn(session_id=session_b, org_id=org_id, turn_number=1, user_transcript="Turn 1 B")
        queue_voice_turn(session_id=session_a, org_id=org_id, turn_number=2, user_transcript="Turn 2 A")

        assert _TURN_QUEUE.qsize() == 3

        mock_db = AsyncMock()
        mock_db.add_all = MagicMock()
        mock_db.commit = AsyncMock()

        await flush_pending_turns(db=mock_db, session_id=session_a)

        assert _TURN_QUEUE.qsize() == 1
        remaining = _TURN_QUEUE.get_nowait()
        assert remaining.session_id == session_b

        queue_voice_turn(session_id=session_a, org_id=org_id, turn_number=3, user_transcript="Turn 3 A")
        failing_db = AsyncMock()
        failing_db.add_all = MagicMock()
        failing_db.commit.side_effect = RuntimeError("Database transient failure")

        with pytest.raises(RuntimeError):
            await flush_pending_turns(db=failing_db, session_id=session_a)

        assert _TURN_QUEUE.qsize() == 1
        retained = _TURN_QUEUE.get_nowait()
        assert retained.session_id == session_a
        assert retained.user_transcript == "Turn 3 A"

    asyncio.run(_runner())


@pytest.mark.live
def test_call_control_route_authorization_enforcement():
    async def _runner():
        from sqlalchemy.future import select

        from app.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            res = await db.execute(select(Organization).limit(1))
            real_org = res.scalars().first()
            tenant_org_a = real_org.id if real_org else uuid.uuid4()
            test_room = f"room_active_{uuid.uuid4().hex}"
            active_call = CallLog(
                id=uuid.uuid4(),
                org_id=tenant_org_a,
                room_name=test_room,
                call_status="in_progress",
                caller_phone="+15551234567",
            )
            db.add(active_call)
            await db.commit()

        tenant_org_b = uuid.uuid4()
        user_receptionist = User(
            id=uuid.uuid4(),
            org_id=tenant_org_a,
            email="receptionist@clinic.com",
            full_name="Sarah Connor",
            role="receptionist",
            is_active=True,
        )
        user_unauthorized = User(
            id=uuid.uuid4(),
            org_id=tenant_org_a,
            email="dispatcher@clinic.com",
            full_name="John Doe",
            role="dispatcher",
            is_active=True,
        )

        app.dependency_overrides[get_current_user] = lambda: user_receptionist
        app.dependency_overrides[get_current_tenant_org] = lambda: tenant_org_a

        try:
            with (
                patch("app.services.telephony.token_service.LIVEKIT_SDK_AVAILABLE", True),
                patch("app.services.telephony.token_service.AccessToken") as mock_token_cls,
                patch("app.services.telephony.token_service.enforce_voice_demo_allowance", AsyncMock(return_value=120)),
                patch(
                    "app.services.infra.redis_cache.presence_service.get_first_available_staff",
                    MagicMock(return_value=None),
                ),
                patch("app.services.telephony.token_service.ws_manager.broadcast_to_org", AsyncMock()),
            ):
                mock_builder = MagicMock()
                mock_builder.to_jwt.return_value = "mock_jwt_token"
                mock_token_cls.return_value = mock_builder

                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res_spoof = await client.post(
                        "/api/v1/calls/token",
                        json={"org_id": str(tenant_org_b), "participant_name": "attacker"},
                    )
                    assert res_spoof.status_code == 403

                    res_staff_spoof = await client.post(
                        "/api/v1/calls/token",
                        json={"participant_name": "staff_superadmin"},
                    )
                    assert res_staff_spoof.status_code == 200
                    data = res_staff_spoof.json()
                    assert not data["participant_name"].startswith("staff_")
                    assert data["participant_name"].startswith("caller_")

                    res_missing = await client.post(
                        "/api/v1/calls/room_nonexistent_123/accept",
                        json={"staff_id": "fake", "staff_name": "fake", "org_id": str(tenant_org_a)},
                    )
                    assert res_missing.status_code == 404

                    res_join_ok = await client.post(
                        "/api/v1/calls/token",
                        json={"room_name": test_room},
                    )
                    assert res_join_ok.status_code == 200
                    data_join = res_join_ok.json()
                    assert data_join["participant_name"] == f"staff_{user_receptionist.id}"

                    app.dependency_overrides[get_current_user] = lambda: user_unauthorized
                    res_unauthorized = await client.post(
                        "/api/v1/calls/token",
                        json={"room_name": test_room},
                    )
                    assert res_unauthorized.status_code == 403
                    assert "Unauthorized staff role" in res_unauthorized.json()["detail"]

                    res_accept_unauth = await client.post(
                        f"/api/v1/calls/{test_room}/accept",
                        json={
                            "staff_id": str(user_unauthorized.id),
                            "staff_name": "John Doe",
                            "org_id": str(tenant_org_a),
                        },
                    )
                    assert res_accept_unauth.status_code == 403
                    assert "Unauthorized staff role to accept call" in res_accept_unauth.json()["detail"]

                    res_hangup_unauth = await client.post(
                        f"/api/v1/calls/{test_room}/hangup",
                        json={"staff_id": str(user_unauthorized.id), "org_id": str(tenant_org_a)},
                    )
                    assert res_hangup_unauth.status_code == 403
                    assert "Unauthorized staff role to hang up call" in res_hangup_unauth.json()["detail"]

                    user_receptionist_b = User(
                        id=uuid.uuid4(),
                        org_id=tenant_org_a,
                        email="receptionist2@clinic.com",
                        full_name="Other Receptionist",
                        role="receptionist",
                        is_active=True,
                    )
                    user_admin = User(
                        id=uuid.uuid4(),
                        org_id=tenant_org_a,
                        email="admin@clinic.com",
                        full_name="Admin Boss",
                        role="admin",
                        is_active=True,
                    )

                    with (
                        patch(
                            "app.api.v1.calls.redis_service.get_call_owner",
                            AsyncMock(return_value=str(user_receptionist.id)),
                        ),
                        patch("app.api.v1.calls.hangup_telephony_call", AsyncMock(return_value={"status": "hung_up"})),
                    ):
                        app.dependency_overrides[get_current_user] = lambda: user_receptionist_b
                        res_hangup_other = await client.post(
                            f"/api/v1/calls/{test_room}/hangup",
                            json={"staff_id": str(user_receptionist_b.id), "org_id": str(tenant_org_a)},
                        )
                        assert res_hangup_other.status_code == 403
                        assert (
                            "Only the call owner or an admin can hang up this call" in res_hangup_other.json()["detail"]
                        )

                        app.dependency_overrides[get_current_user] = lambda: user_admin
                        res_hangup_admin = await client.post(
                            f"/api/v1/calls/{test_room}/hangup",
                            json={"staff_id": str(user_admin.id), "org_id": str(tenant_org_a)},
                        )
                        assert res_hangup_admin.status_code == 200
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_current_tenant_org, None)
            async with AsyncSessionLocal() as cleanup_db:
                call_to_del = await cleanup_db.get(CallLog, active_call.id)
                if call_to_del:
                    await cleanup_db.delete(call_to_del)
                    await cleanup_db.commit()

    asyncio.run(_runner())


def test_parent_completed_first_dial_no_answer_second_reconciliation():
    async def _runner():
        parent_call_sid = "CA_reconciliation_order_test_123"
        canonical_id = uuid.uuid5(uuid.NAMESPACE_OID, parent_call_sid)

        mock_call = CallLog(
            id=canonical_id,
            org_id=uuid.uuid4(),
            caller_phone="+1234567890",
            call_status="ringing",
            triage_status="ringing",
            connected_at=None,
            duration_seconds=0,
            end_time=None,
        )

        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(
            scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_call)))
        )
        mock_db.commit = AsyncMock()

        maker = MagicMock()
        maker.return_value.__aenter__.return_value = mock_db
        maker.return_value.__aexit__.return_value = None

        with patch("app.services.telephony.twilio_service.ws_manager.broadcast_to_org", AsyncMock()):
            resp_parent = await handle_twilio_status(
                CallSid=parent_call_sid,
                CallStatus="completed",
                CallDuration="0",
                session_factory=maker,
            )
            assert resp_parent["status"] == "recorded"
            assert mock_call.call_status == "missed"
            assert mock_call.call_outcome == "caller_abandoned"

            resp_dial = await handle_twilio_dial_status(
                CallSid=parent_call_sid,
                DialCallSid="CA_child_leg_no_answer",
                DialCallStatus="no-answer",
                DialCallDuration="0",
                session_factory=maker,
            )
            assert resp_dial.status_code == 200
            assert mock_call.call_status == "missed"
            assert mock_call.call_outcome == "no_answer"
            assert mock_call.attended_by == "Unattended / Missed"
            assert mock_call.triage_status == "missed"

    asyncio.run(_runner())


def test_monotonic_callback_order_invariance():
    async def _runner():
        parent_call_sid = "CA_monotonic_terminal_test"
        canonical_id = uuid.uuid5(uuid.NAMESPACE_OID, parent_call_sid)
        initial_connected_at = datetime(2026, 10, 8, 12, 0, 0, tzinfo=timezone.utc)

        mock_call = CallLog(
            id=canonical_id,
            org_id=uuid.uuid4(),
            caller_phone="+1234567890",
            call_status="completed",
            duration_seconds=120,
            connected_at=initial_connected_at,
            end_time=datetime(2026, 10, 8, 12, 2, 0, tzinfo=timezone.utc),
        )

        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(
            scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_call)))
        )
        mock_db.commit = AsyncMock()

        maker = MagicMock()
        maker.return_value.__aenter__.return_value = mock_db
        maker.return_value.__aexit__.return_value = None

        await handle_twilio_dial_status(
            CallSid=parent_call_sid,
            DialCallSid="CA_child_leg_late",
            DialCallStatus="busy",
            DialCallDuration="0",
            session_factory=maker,
        )
        assert mock_call.call_status == "completed"
        assert mock_call.duration_seconds == 120

        await handle_twilio_sip_status(
            parent_call_sid=parent_call_sid,
            CallSid="CA_child_sip_late",
            CallStatus="answered",
            session_factory=maker,
        )
        assert mock_call.connected_at == initial_connected_at

    asyncio.run(_runner())


def test_hotline_write_boundary_validation():
    async def _runner():
        from fastapi import HTTPException

        from app.api.v1.organization import OrgConfigUpdate
        from app.services.clinic.organization_service import update_organization_settings

        org_id = uuid.uuid4()
        other_org_id = uuid.uuid4()
        mock_org = Organization(id=org_id, name="Main Practice", phone="+15551112222", country_code="US")

        mock_db = AsyncMock()

        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_org)),
        ]
        with pytest.raises(HTTPException) as exc_invalid:
            await update_organization_settings(
                db=mock_db,
                org_id=org_id,
                update=OrgConfigUpdate(phone="invalid-phone-string"),
            )
        assert exc_invalid.value.status_code == 422

        mock_org_no_country = Organization(id=org_id, name="No Country Org", phone="+15551112222", country_code=None)
        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_org_no_country)),
        ]
        with pytest.raises(HTTPException) as exc_no_country:
            await update_organization_settings(
                db=mock_db,
                org_id=org_id,
                update=OrgConfigUpdate(phone="5550199"),
            )
        assert exc_no_country.value.status_code == 422

        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_org)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=other_org_id)),
        ]
        with pytest.raises(HTTPException) as exc_dup:
            await update_organization_settings(
                db=mock_db,
                org_id=org_id,
                update=OrgConfigUpdate(phone="+12125550199"),
            )
        assert exc_dup.value.status_code == 409

        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_org)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]
        with (
            patch("app.services.clinic.organization_service.invalidate_org_tenant_cache", AsyncMock()),
            patch("app.services.clinic.organization_service.redis_service.invalidate_clinic_config", AsyncMock()),
        ):
            updated = await update_organization_settings(
                db=mock_db,
                org_id=org_id,
                update=OrgConfigUpdate(phone="(212) 555-0199"),
            )
            assert updated.phone == "+12125550199"
            assert updated.hotline == "+12125550199"

    asyncio.run(_runner())


def test_call_sid_uuid5_canonical_isolation():
    sid_a = "CA_test_isolation_root"
    sid_b = "CA_test_isolation_root_extended"
    id_a = uuid.uuid5(uuid.NAMESPACE_OID, sid_a)
    id_b = uuid.uuid5(uuid.NAMESPACE_OID, sid_b)
    assert id_a != id_b
    assert id_a == uuid.uuid5(uuid.NAMESPACE_OID, sid_a)


def test_concurrent_turn_flushing_serialized_by_lock():
    async def _runner():
        while not _TURN_QUEUE.empty():
            _TURN_QUEUE.get_nowait()

        session_1 = uuid.uuid4()
        session_2 = uuid.uuid4()
        org_id = uuid.uuid4()

        queue_voice_turn(session_id=session_1, org_id=org_id, turn_number=1, user_transcript="Concurrent Turn 1")
        queue_voice_turn(session_id=session_2, org_id=org_id, turn_number=1, user_transcript="Concurrent Turn 2")

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        await asyncio.gather(
            flush_pending_turns(db=mock_db, session_id=session_1),
            flush_pending_turns(db=mock_db, session_id=session_2),
        )

        assert _TURN_QUEUE.empty()

    asyncio.run(_runner())


def test_real_twilio_hmac_signature_validation():
    async def _runner():
        from fastapi import HTTPException
        from starlette.requests import Request
        from twilio.request_validator import RequestValidator

        from app.core.config import settings

        auth_token = "mock_secret_twilio_token_12345"
        validator = RequestValidator(auth_token)
        url = "https://dispatch-demo.ngrok-free.app/api/v1/telephony/twilio/inbound"
        form_params = {"From": "+15551234567", "To": "+15559876543", "CallSid": "CA_signature_test"}

        valid_signature = validator.compute_signature(url, form_params)

        with (
            patch.object(settings, "TWILIO_AUTH_TOKEN", auth_token),
            patch.object(settings, "NGROK_DOMAIN", "dispatch-demo.ngrok-free.app"),
        ):
            scope = {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/telephony/twilio/inbound",
                "headers": [
                    (b"x-twilio-signature", valid_signature.encode("utf-8")),
                    (b"host", b"dispatch-demo.ngrok-free.app"),
                    (b"x-forwarded-proto", b"https"),
                    (b"x-forwarded-host", b"dispatch-demo.ngrok-free.app"),
                    (b"content-type", b"application/x-www-form-urlencoded"),
                ],
                "query_string": b"",
            }

            body_bytes = b"From=%2B15551234567&To=%2B15559876543&CallSid=CA_signature_test"

            async def receive():
                return {"type": "http.request", "body": body_bytes}

            req = Request(scope, receive)
            is_valid = await validate_twilio_request(req)
            assert is_valid is True

            scope_tampered = {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/telephony/twilio/inbound",
                "headers": [
                    (b"x-twilio-signature", b"forged_invalid_signature_here"),
                    (b"host", b"dispatch-demo.ngrok-free.app"),
                    (b"content-type", b"application/x-www-form-urlencoded"),
                ],
                "query_string": b"",
            }
            req_tampered = Request(scope_tampered, receive)
            with pytest.raises(HTTPException) as exc_tampered:
                await validate_twilio_request(req_tampered)
            assert exc_tampered.value.status_code == 403

            scope_spoofed_host = {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/telephony/twilio/inbound",
                "headers": [
                    (b"x-twilio-signature", valid_signature.encode("utf-8")),
                    (b"host", b"dispatch-demo.ngrok-free.app"),
                    (b"x-forwarded-proto", b"https"),
                    (b"x-forwarded-host", b"attacker.com"),
                    (b"content-type", b"application/x-www-form-urlencoded"),
                ],
                "query_string": b"",
            }
            req_spoofed = Request(scope_spoofed_host, receive)
            is_valid_fallback = await validate_twilio_request(req_spoofed)
            assert is_valid_fallback is True

    asyncio.run(_runner())
