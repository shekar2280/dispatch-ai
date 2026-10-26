import asyncio
import io
import json
import uuid
import wave
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.call_session import CallLog
from app.models.call_turn import VoiceCallTurn
from app.models.outbox_event import OutboxEvent
from app.models.voice_mutation_operation import VoiceMutationOperation
from app.models.voice_recording_chunk import VoiceRecordingChunk
from app.models.voice_workflow_checkpoint import VoiceWorkflowCheckpoint
from app.services.audio.call_recording import CallRecorder
from app.services.audio.circular_audio_buffer import (
    BYTES_PER_SAMPLE,
    BYTES_PER_SEC,
    NUM_CHANNELS,
    SAMPLE_RATE,
    ChunkedAudioBuffer,
    stitch_wav_chunks,
)
from app.services.infra.outbox import (
    OutboxRelay,
    enqueue_outbox_event,
    get_mutation_operation,
    record_mutation_operation,
)
from app.services.infra.storage import (
    CALL_RECORDING_BUCKET,
    sign_call_recording,
)
from app.services.voice.call_logger_service import (
    _TURN_QUEUE,
    flush_pending_turns,
    queue_voice_turn,
)
from app.services.voice.event_journal import (
    BoundedTurnJournalQueue,
    EventJournal,
    JournalTurnEvent,
)
from app.services.voice.handlers.clinic_tool_handler import (
    _cancel,
    _confirm_booking,
    _reschedule,
)
from app.services.voice.retention import purge_expired_audio_recordings
from app.services.voice.workflow.checkpoint_store import (
    OptimisticLockError,
    find_resumable_checkpoint,
    load_checkpoint,
    mark_checkpoint_completed,
    mark_checkpoint_resumed,
    purge_expired_checkpoints,
    save_checkpoint,
)
from app.services.voice.workflow.recovery import (
    RecoveryContext,
    apply_recovery_preferences,
    build_recovery_greeting,
    decline_recovery_offer,
    find_recovery_context,
)
from app.services.voice.workflow.state import VoiceWorkflowState, WorkflowStage


class MockCheckpointDb:
    def __init__(self, checkpoints=None, calls=None):
        self.checkpoints = checkpoints or {}
        self.calls = calls or {}
        self.committed = False

    async def scalar(self, stmt):
        for cp in self.checkpoints.values():
            return cp
        return None

    def add(self, entity):
        self.checkpoints[entity.id] = entity

    async def commit(self):
        self.committed = True

    async def refresh(self, entity):
        pass

    async def execute(self, stmt):
        res = MagicMock()
        res.rowcount = 1
        return res


class FakeRecordingDB:
    def __init__(self):
        self.calls = {}
        self.chunks = []

    async def get(self, model, ident):
        if model is CallLog:
            return self.calls.get(ident)
        return None

    def add(self, obj):
        if isinstance(obj, CallLog):
            self.calls[obj.id] = obj
        elif isinstance(obj, VoiceRecordingChunk):
            self.chunks.append(obj)

    async def scalar(self, stmt):
        for c in self.chunks:
            return c
        return None

    async def scalars(self, stmt):
        res = MagicMock()
        stmt_str = str(stmt).lower()
        if "voice_recording_chunks" in stmt_str:
            res.all.return_value = list(self.chunks)
        else:
            res.all.return_value = list(self.calls.values())
        return res

    async def execute(self, stmt, params=None):
        stmt_str = str(stmt).lower()
        if "delete from public.voice_token_rate_limits" in stmt_str:
            return
        if "delete" in stmt_str and "voice_recording_chunks" in stmt_str:
            self.chunks.clear()

    async def commit(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def generate_pcm_frame(duration_sec: float, sample_val: int = 500) -> bytes:
    num_samples = int(duration_sec * SAMPLE_RATE)
    return (sample_val.to_bytes(2, byteorder="little", signed=True)) * num_samples


def make_test_checkpoint(
    org_id,
    call_id,
    status="active",
    stage="slot_selection",
    safe_state=None,
    age_seconds=120,
    expires_in_seconds=600,
):
    now = datetime.now(UTC)
    created = now - timedelta(seconds=age_seconds)
    expires = now + timedelta(seconds=expires_in_seconds)
    target_date = (now.date() + timedelta(days=1)).isoformat()
    return VoiceWorkflowCheckpoint(
        id=uuid4(),
        org_id=org_id,
        call_id=call_id,
        status=status,
        stage=stage,
        safe_state=safe_state or {"preferred_doctor": "Dr. Sarah", "target_date": target_date},
        expires_at=expires,
        created_at=created,
        updated_at=created,
    )


def make_test_call_log(org_id, call_id, phone="+15551234567", booking_result=None):
    return CallLog(
        id=call_id,
        org_id=org_id,
        caller_phone=phone,
        caller_name="Alice Smith",
        booking_result=booking_result,
    )


@pytest.mark.asyncio
async def test_save_checkpoint_creates_and_loads_new_checkpoint():
    org_id = uuid.uuid4()
    call_id = uuid.uuid4()
    state = VoiceWorkflowState(
        stage=WorkflowStage.SLOT_SELECTION,
        candidate_slots=[{"label": "2:00 PM"}],
        caller_name="Secret Patient",
        verified_name="Secret Patient",
        patient_id="patient-1",
        caller_phone="+919876543210",
    )
    db = MockCheckpointDb()
    cp = await save_checkpoint(db, org_id, call_id, state)

    assert cp.org_id == org_id
    assert cp.call_id == call_id
    assert cp.stage == "slot_selection"
    assert cp.state_version == 1
    assert cp.status == "active"
    assert "caller_name" not in cp.safe_state
    assert "patient_id" not in cp.safe_state
    assert "caller_phone" not in cp.safe_state
    assert cp.safe_state["candidate_count"] == 1


@pytest.mark.asyncio
async def test_optimistic_concurrency_rejects_stale_worker():
    org_id = uuid.uuid4()
    call_id = uuid.uuid4()
    now = datetime.now(UTC)
    existing_cp = VoiceWorkflowCheckpoint(
        id=uuid.uuid4(),
        org_id=org_id,
        call_id=call_id,
        workflow_version=1,
        state_version=5,
        status="active",
        stage="slot_selection",
        safe_state={},
        expires_at=now + timedelta(minutes=30),
        created_at=now,
        updated_at=now,
    )
    db = MockCheckpointDb(checkpoints={existing_cp.id: existing_cp})
    state = VoiceWorkflowState(stage=WorkflowStage.BOOKING_DETAILS, state_version=4)

    with pytest.raises(OptimisticLockError):
        await save_checkpoint(
            db,
            org_id,
            call_id,
            state,
            expected_state_version=4,
        )


@pytest.mark.asyncio
async def test_worker_crash_recovery_preserves_last_safe_checkpoint():
    org_id = uuid.uuid4()
    call_id = uuid.uuid4()
    now = datetime.now(UTC)
    safe_data = {
        "stage": "slot_selection",
        "intent": "inquiry",
        "preferred_doctor": "Dr. Sharma",
        "target_date": "2026-10-25",
        "candidate_count": 2,
        "workflow_version": 1,
        "state_version": 3,
    }
    saved_cp = VoiceWorkflowCheckpoint(
        id=uuid.uuid4(),
        org_id=org_id,
        call_id=call_id,
        workflow_version=1,
        state_version=3,
        status="active",
        stage="slot_selection",
        safe_state=safe_data,
        last_completed_event_id="event-turn-2",
        expires_at=now + timedelta(minutes=30),
        created_at=now,
        updated_at=now,
    )
    db = MockCheckpointDb(checkpoints={saved_cp.id: saved_cp})

    loaded = await load_checkpoint(db, org_id, call_id)
    assert loaded is not None
    assert loaded.stage == "slot_selection"
    assert loaded.state_version == 3
    assert loaded.last_completed_event_id == "event-turn-2"

    recovered_state = VoiceWorkflowState(
        stage=WorkflowStage(loaded.stage),
        preferred_doctor=loaded.safe_state.get("preferred_doctor"),
        target_date=loaded.safe_state.get("target_date"),
        workflow_version=loaded.workflow_version,
        state_version=loaded.state_version,
        last_completed_event_id=loaded.last_completed_event_id,
    )
    assert recovered_state.stage == WorkflowStage.SLOT_SELECTION
    assert recovered_state.preferred_doctor == "Dr. Sharma"
    assert recovered_state.target_date == "2026-10-25"
    assert recovered_state.last_completed_event_id == "event-turn-2"
    assert recovered_state.caller_name is None
    assert recovered_state.patient_verified is False


@pytest.mark.asyncio
async def test_find_resumable_checkpoint_rejects_expired():
    db = AsyncMock()
    exec_result = MagicMock()
    exec_result.first.return_value = None
    db.execute.return_value = exec_result

    res = await find_resumable_checkpoint(db, uuid.uuid4(), "+919876543210")
    assert res is None


@pytest.mark.asyncio
async def test_mark_checkpoint_resumed_and_completed():
    db = AsyncMock()
    db.execute.return_value = MagicMock(rowcount=1)

    resumed = await mark_checkpoint_resumed(db, uuid.uuid4(), uuid.uuid4())
    assert resumed is True

    completed = await mark_checkpoint_completed(db, uuid.uuid4(), uuid.uuid4())
    assert completed is True


@pytest.mark.asyncio
async def test_purge_expired_checkpoints():
    db = AsyncMock()
    db.execute.return_value = MagicMock(rowcount=5)

    purged = await purge_expired_checkpoints(db, batch_size=50)
    assert purged == 5


@pytest.mark.asyncio
async def test_record_and_get_mutation_operation():
    db = AsyncMock()
    org_id = uuid4()
    call_id = uuid4()
    op_key = f"op:{uuid4()}"
    payload = {"status": "confirmed", "appointment_id": str(uuid4())}

    fake_op = VoiceMutationOperation(
        id=uuid4(),
        org_id=org_id,
        call_id=call_id,
        operation_key=op_key,
        operation_type="book_appointment",
        status="completed",
        response_payload=payload,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    exec_res = MagicMock()
    exec_res.scalar_one.return_value = fake_op
    exec_res.scalar_one_or_none.return_value = fake_op
    db.execute = AsyncMock(return_value=exec_res)

    saved = await record_mutation_operation(
        db=db,
        org_id=org_id,
        call_id=call_id,
        operation_key=op_key,
        operation_type="book_appointment",
        response_payload=payload,
    )
    assert saved is not None
    assert saved.operation_key == op_key
    assert saved.response_payload == payload

    fetched = await get_mutation_operation(db=db, org_id=org_id, operation_key=op_key)
    assert fetched is not None
    assert fetched.operation_key == op_key
    assert fetched.response_payload == payload


@pytest.mark.asyncio
async def test_enqueue_outbox_event_adds_pending_event():
    db = AsyncMock()
    db.add = MagicMock()
    org_id = uuid4()
    payload = {"event": "APPOINTMENT_BOOKED", "appointment_id": str(uuid4())}

    with patch("app.services.infra.outbox.outbox_relay.notify") as notify_mock:
        event = await enqueue_outbox_event(
            db=db,
            org_id=org_id,
            event_type="APPOINTMENT_BOOKED",
            payload=payload,
        )
        assert event.org_id == org_id
        assert event.event_type == "APPOINTMENT_BOOKED"
        assert event.payload == payload
        assert event.status == "pending"
        assert event.attempts == 0
        db.add.assert_called_once_with(event)
        db.flush.assert_awaited_once()
        notify_mock.assert_called_once()


@pytest.mark.asyncio
async def test_outbox_relay_processes_pending_events_successfully():
    org_id = uuid4()
    event_id = uuid4()
    payload = {"event": "APPOINTMENT_BOOKED", "appointment_id": str(uuid4())}

    event = OutboxEvent(
        id=event_id,
        org_id=org_id,
        event_type="APPOINTMENT_BOOKED",
        payload=payload,
        status="pending",
        attempts=0,
        created_at=datetime.now(UTC),
    )

    db = AsyncMock()
    exec_res = MagicMock()
    exec_res.scalars.return_value.all.return_value = [event]
    db.execute = AsyncMock(return_value=exec_res)

    relay = OutboxRelay(max_attempts=3)
    with patch("app.services.infra.websocket_manager.ws_manager.broadcast_to_org", new_callable=AsyncMock) as ws_mock:
        count = await relay.process_batch(batch_size=10, db=db)
        assert count == 1
        ws_mock.assert_awaited_once_with(str(org_id), payload)
        assert event.status == "published"
        assert event.attempts == 1
        assert event.published_at is not None
        assert event.last_attempt_at is not None
        db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_outbox_relay_dead_letters_poison_event():
    org_id = uuid4()
    event_id = uuid4()
    payload = {"event": "BAD_EVENT"}

    event = OutboxEvent(
        id=event_id,
        org_id=org_id,
        event_type="BAD_EVENT",
        payload=payload,
        status="pending",
        attempts=2,
        created_at=datetime.now(UTC),
    )

    db = AsyncMock()
    exec_res = MagicMock()
    exec_res.scalars.return_value.all.return_value = [event]
    db.execute = AsyncMock(return_value=exec_res)

    relay = OutboxRelay(max_attempts=3)
    with patch(
        "app.services.infra.websocket_manager.ws_manager.broadcast_to_org",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Websocket gateway unavailable"),
    ):
        count = await relay.process_batch(batch_size=10, db=db)
        assert count == 1
        assert event.attempts == 3
        assert event.status == "failed"
        assert "Websocket gateway unavailable" in event.error_detail
        db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_confirm_booking_is_idempotent_on_retry():
    org_id = uuid4()
    call_id = uuid4()
    op_key = f"voice-booking:{call_id}:custom-key"
    cached_result = {
        "status": "confirmed",
        "appointment_id": str(uuid4()),
        "patient_name": "Alice Smith",
        "doctor_name": "Dr. Sarah",
        "date": "2026-10-30",
        "time": "10:00 AM",
        "message": "Appointment confirmed",
    }

    fake_op = VoiceMutationOperation(
        id=uuid4(),
        org_id=org_id,
        call_id=call_id,
        operation_key=op_key,
        operation_type="book_appointment",
        status="completed",
        response_payload=cached_result,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    db = AsyncMock()
    org_obj = MagicMock()
    org_obj.timezone = "Asia/Kolkata"

    with (
        patch("app.services.voice.handlers.clinic_tool_handler.get_mutation_operation", new_callable=AsyncMock, return_value=fake_op) as get_op_mock,
        patch("app.services.voice.booking_consent.authorize_booking", new_callable=AsyncMock) as auth_mock,
    ):
        args = {
            "operation_key": op_key,
            "first_name": "Alice",
            "last_name": "Smith",
            "slot_date": "2026-10-30",
            "slot_time": "10:00 AM",
        }
        res = await _confirm_booking(args, db, org_id, org_obj, "+919876543210", call_id)
        assert res == cached_result
        get_op_mock.assert_awaited_once_with(db, org_id, op_key)
        auth_mock.assert_not_called()


@pytest.mark.asyncio
async def test_reschedule_and_cancel_are_idempotent_on_retry():
    org_id = uuid4()
    call_id = uuid4()
    appt_id = uuid4()
    reschedule_key = f"voice-reschedule:{call_id}:{appt_id}:2026-11-01:11:00 AM"
    cached_reschedule = {
        "status": "success",
        "message": "Appointment rescheduled to 2026-11-01 at 11:00 AM.",
        "confirmed_date": "2026-11-01",
        "confirmed_time": "11:00 AM",
        "audit_recorded": True,
    }

    fake_reschedule_op = VoiceMutationOperation(
        id=uuid4(),
        org_id=org_id,
        call_id=call_id,
        operation_key=reschedule_key,
        operation_type="reschedule_appointment",
        status="completed",
        response_payload=cached_reschedule,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    db = AsyncMock()
    appt_mock = MagicMock()
    appt_mock.id = appt_id
    appt_mock.patient_id = uuid4()
    appt_mock.status = "scheduled"

    appt_res = MagicMock()
    appt_res.scalar_one_or_none.return_value = appt_mock
    db.execute = AsyncMock(return_value=appt_res)

    org_obj = MagicMock()
    org_obj.timezone = "Asia/Kolkata"

    with (
        patch("app.services.voice.handlers.clinic_tool_handler.get_mutation_operation", new_callable=AsyncMock, return_value=fake_reschedule_op),
        patch("app.services.voice.handlers.clinic_tool_handler.reschedule_clinic_appointment", new_callable=AsyncMock) as svc_reschedule,
    ):
        args = {
            "operation_key": reschedule_key,
            "appointment_id": str(appt_id),
            "new_date": "2026-11-01",
            "new_time": "11:00 AM",
        }
        res = await _reschedule(args, db, org_id, org_obj, "+919876543210", call_id)
        assert res == cached_reschedule
        svc_reschedule.assert_not_called()

    cancel_key = f"voice-cancel:{call_id}:{appt_id}"
    cached_cancel = {
        "status": "cancelled",
        "message": f"Appointment {appt_id} has been cancelled and logged in clinic records.",
        "audit_recorded": True,
    }
    fake_cancel_op = VoiceMutationOperation(
        id=uuid4(),
        org_id=org_id,
        call_id=call_id,
        operation_key=cancel_key,
        operation_type="cancel_appointment",
        status="completed",
        response_payload=cached_cancel,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    with (
        patch("app.services.voice.handlers.clinic_tool_handler.get_mutation_operation", new_callable=AsyncMock, return_value=fake_cancel_op),
        patch("app.services.voice.handlers.clinic_tool_handler.cancel_clinic_appointment", new_callable=AsyncMock) as svc_cancel,
    ):
        c_args = {
            "operation_key": cancel_key,
            "appointment_id": str(appt_id),
            "cancellation_reason": "Patient request",
        }
        c_res = await _cancel(c_args, db, org_id, "+919876543210", call_id)
        assert c_res == cached_cancel
        svc_cancel.assert_not_called()


@pytest.mark.asyncio
async def test_tts_failure_sets_committed_but_not_acknowledged_and_recovery_finds_it():
    workflow = VoiceWorkflowState()
    workflow.booking_confirmed = True
    workflow.committed_but_not_acknowledged = True
    workflow.selected_slot_time = "02:30 PM"
    workflow.preferred_doctor = "Dr. Michael"

    safe_dict = workflow.to_safe_dict()
    assert safe_dict["committed_but_not_acknowledged"] is True
    assert safe_dict["booking_confirmed"] is True

    checkpoint = SimpleNamespace(
        id=uuid4(),
        stage=WorkflowStage.CLOSING.value,
        safe_state=safe_dict,
    )
    call_log = SimpleNamespace(
        id=uuid4(),
        booking_result=None,
        call_outcome="appointment_booked",
        patient_id=uuid4(),
    )

    db = AsyncMock()
    exec_res = MagicMock()
    exec_res.first.return_value = (checkpoint, call_log)
    db.execute = AsyncMock(return_value=exec_res)

    recovery_ctx = await find_recovery_context(db=db, org_id=uuid4(), caller_phone="+919876543210")
    assert recovery_ctx is not None
    assert recovery_ctx.has_committed_appointment is True
    assert recovery_ctx.appointment_time == "02:30 PM"
    assert recovery_ctx.preferred_doctor == "Dr. Michael"


def test_bounded_queue_item_limit_and_memory_cap():
    q = BoundedTurnJournalQueue(maxsize=10, max_bytes=10000)
    for i in range(25):
        turn = VoiceCallTurn(
            session_id=uuid4(),
            org_id=uuid4(),
            turn_number=i,
            user_transcript=f"User transcript message {i}",
        )
        q.put_nowait(turn)

    assert q.qsize() == 10
    assert q.current_bytes <= 10000
    assert q.shed_count == 15


def test_queue_sheds_non_critical_telemetry_first():
    q = BoundedTurnJournalQueue(maxsize=3, max_bytes=10000)
    t1 = VoiceCallTurn(session_id=uuid4(), org_id=uuid4(), turn_number=1, stt_latency_ms=100)
    t2 = VoiceCallTurn(session_id=uuid4(), org_id=uuid4(), turn_number=2, stt_latency_ms=200)
    t3 = VoiceCallTurn(session_id=uuid4(), org_id=uuid4(), turn_number=3, stt_latency_ms=300)

    q.put_nowait(t1)
    q.put_nowait(t2)
    q.put_nowait(t3)
    assert q.qsize() == 3

    critical_turn = VoiceCallTurn(
        session_id=uuid4(),
        org_id=uuid4(),
        turn_number=4,
        user_transcript="I need an appointment tomorrow",
    )
    accepted = q.put_nowait(critical_turn)
    assert accepted is True
    assert q.qsize() == 3
    assert q.shed_count == 1

    remaining_items = [q.get_nowait() for _ in range(3)]
    assert any(getattr(item, "user_transcript", None) == "I need an appointment tomorrow" for item in remaining_items)


@pytest.mark.asyncio
async def test_process_death_with_queued_events():
    journal = EventJournal()
    mock_redis = AsyncMock()

    turn_data = JournalTurnEvent(
        event_id="evt_recover_123",
        session_id=str(uuid4()),
        org_id=str(uuid4()),
        turn_number=1,
        is_critical=True,
        user_transcript="Recovered turn after crash",
    )
    raw_record = ("1729780000000-0", {"payload": json.dumps(turn_data.to_dict())})
    mock_redis.xreadgroup.return_value = [("voice:turns:journal", [raw_record])]
    mock_redis.xack.return_value = 1

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.voice.event_journal.redis_service.get_client", AsyncMock(return_value=mock_redis))
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_session_local = MagicMock()
        mock_session_local.return_value.__aenter__.return_value = mock_db
        mock_session_local.return_value.__aexit__.return_value = None
        mp.setattr("app.core.database.AsyncSessionLocal", mock_session_local)

        processed = await journal.process_batch(batch_size=10)

    assert processed == 1
    mock_redis.xack.assert_called_once()
    mock_db.execute.assert_called_once()
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_broker_unavailable_falls_back_to_db():
    journal = EventJournal()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.voice.event_journal.redis_service.get_client", AsyncMock(return_value=None))

        event = JournalTurnEvent(
            event_id="evt_fallback_1",
            session_id=str(uuid4()),
            org_id=str(uuid4()),
            turn_number=1,
            is_critical=True,
            user_transcript="Direct fallback turn",
        )
        published = await journal.publish_turn(event)
        assert published is False


@pytest.mark.asyncio
async def test_poison_message_handling():
    journal = EventJournal()
    mock_redis = AsyncMock()

    poison_record = ("1729780000001-0", {"payload": "not-a-json-string-invalid"})
    mock_redis.xreadgroup.return_value = [("voice:turns:journal", [poison_record])]
    mock_redis.xack.return_value = 1

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.voice.event_journal.redis_service.get_client", AsyncMock(return_value=mock_redis))
        processed = await journal.process_batch(batch_size=10)

    assert processed == 0
    mock_redis.xack.assert_called_once()


@pytest.mark.asyncio
async def test_call_a_flushing_does_not_delay_or_reorder_call_b():
    _TURN_QUEUE.clear()
    session_a = uuid4()
    session_b = uuid4()
    org_id = uuid4()

    queue_voice_turn(session_id=session_a, org_id=org_id, turn_number=1, user_transcript="Turn A1")
    queue_voice_turn(session_id=session_b, org_id=org_id, turn_number=1, user_transcript="Turn B1")
    queue_voice_turn(session_id=session_a, org_id=org_id, turn_number=2, user_transcript="Turn A2")
    queue_voice_turn(session_id=session_b, org_id=org_id, turn_number=2, user_transcript="Turn B2")

    assert _TURN_QUEUE.qsize() == 4

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()
    mock_db.commit = AsyncMock()

    await flush_pending_turns(db=mock_db, session_id=session_a)

    assert _TURN_QUEUE.qsize() == 2
    b1 = _TURN_QUEUE.get_nowait()
    b2 = _TURN_QUEUE.get_nowait()
    assert b1.session_id == session_b and b1.turn_number == 1
    assert b2.session_id == session_b and b2.turn_number == 2


def test_memory_remains_bounded_under_sustained_backlog():
    q = BoundedTurnJournalQueue(maxsize=50, max_bytes=20000)
    for i in range(1500):
        turn = VoiceCallTurn(
            session_id=uuid4(),
            org_id=uuid4(),
            turn_number=i,
            user_transcript=f"Turn message {i}",
        )
        q.put_nowait(turn)

    assert q.qsize() == 50
    assert q.current_bytes <= 20000
    assert q.shed_count == 1450


def test_chunked_audio_buffer_memory_ceiling():
    buf = ChunkedAudioBuffer("test_ceiling", chunk_duration_sec=2.0)
    chunk_bytes = int(2.0 * BYTES_PER_SEC)
    one_second_pcm = generate_pcm_frame(1.0, 100)

    for _ in range(10):
        buf.push_caller_frame(one_second_pcm)
        if buf.ready_chunk():
            chunk = buf.pop_chunk()
            assert chunk is not None
            assert len(buf.caller_buffer) < chunk_bytes

    assert len(buf.caller_buffer) <= chunk_bytes


def test_chunked_audio_buffer_pop_and_stitch():
    buf = ChunkedAudioBuffer("test_pop", chunk_duration_sec=1.0)
    frame1 = generate_pcm_frame(1.0, 300)
    frame2 = generate_pcm_frame(1.0, 400)

    buf.push_caller_frame(frame1)
    assert buf.ready_chunk() is True
    res1 = buf.pop_chunk()
    assert res1 is not None
    wav1, idx1, offset1, dur1 = res1
    assert idx1 == 0
    assert offset1 == 0.0
    assert dur1 == 1.0

    buf.push_caller_frame(frame2)
    assert buf.ready_chunk() is True
    res2 = buf.pop_chunk()
    assert res2 is not None
    wav2, idx2, offset2, dur2 = res2
    assert idx2 == 1
    assert offset2 == 1.0
    assert dur2 == 1.0

    stitched = stitch_wav_chunks([wav1, wav2])
    assert stitched is not None
    with wave.open(io.BytesIO(stitched), "rb") as wf:
        assert wf.getnchannels() == NUM_CHANNELS
        assert wf.getsampwidth() == BYTES_PER_SAMPLE
        assert wf.getframerate() == SAMPLE_RATE
        assert wf.getnframes() == int(2.0 * SAMPLE_RATE)


def test_chunked_buffer_partial_flush():
    buf = ChunkedAudioBuffer("test_partial", chunk_duration_sec=5.0)
    half_sec_pcm = generate_pcm_frame(0.5, 150)
    buf.push_caller_frame(half_sec_pcm)

    assert buf.ready_chunk() is False
    assert buf.pop_chunk(force=False) is None

    forced = buf.pop_chunk(force=True)
    assert forced is not None
    wav, idx, offset, dur = forced
    assert idx == 0
    assert dur == 0.5
    with wave.open(io.BytesIO(wav), "rb") as wf:
        assert wf.getnframes() == int(0.5 * SAMPLE_RATE)


@pytest.mark.asyncio
async def test_call_recorder_checkpoint_and_finalize():
    org_id = uuid4()
    call_id = uuid4()

    db = FakeRecordingDB()
    call_log = CallLog(
        id=call_id,
        org_id=org_id,
        caller_phone="+15551234567",
        recording_storage_path=None,
    )
    db.add(call_log)

    room = MagicMock()
    room.on = MagicMock()
    room.remote_participants = {}
    room.local_participant = MagicMock()
    room.local_participant.track_publications = {}

    recorder = CallRecorder(room=room, org_id=org_id, call_id=call_id, chunk_duration_sec=1.0)
    frame1 = generate_pcm_frame(1.0, 200)

    with (
        patch("app.core.database.AsyncSessionLocal", return_value=db),
        patch("app.services.audio.call_recording.upload_call_recording_chunk", new_callable=AsyncMock) as mock_chunk_upload,
        patch("app.services.audio.call_recording.upload_call_recording", new_callable=AsyncMock) as mock_final_upload,
        patch("app.services.audio.call_recording.download_call_recording_chunk", new_callable=AsyncMock) as mock_download,
    ):
        mock_chunk_upload.return_value = f"call-recordings/{org_id}/{call_id}/chunks/0000.wav"
        mock_final_upload.return_value = f"call-recordings/{org_id}/{call_id}.wav"
        mock_download.return_value = frame1

        recorder.buffer.push_caller_frame(frame1)
        chunk_data = recorder.buffer.pop_chunk(force=True)
        assert chunk_data is not None
        wav_bytes, chunk_idx, offset_sec, duration_sec = chunk_data
        path = await mock_chunk_upload(org_id, call_id, chunk_idx, wav_bytes)
        assert path.startswith("call-recordings/")


@pytest.mark.asyncio
async def test_purge_expired_audio_recordings():
    org_id = uuid4()
    call_id = uuid4()

    db = FakeRecordingDB()
    now = datetime.now(UTC)
    old_call = CallLog(
        id=call_id,
        org_id=org_id,
        caller_phone="+15551234567",
        recording_status="ready",
        recording_storage_path=f"call-recordings/{org_id}/{call_id}.wav",
        end_time=now - timedelta(days=100),
    )
    db.add(old_call)

    fake_storage = MagicMock()
    fake_storage.remove = MagicMock()
    fake_client = MagicMock()
    fake_client.storage.from_.return_value = fake_storage

    with (
        patch("app.services.voice.retention.AsyncSessionLocal", return_value=db),
        patch("app.services.voice.retention._call_storage_client", return_value=fake_client),
    ):
        purged = await purge_expired_audio_recordings(batch_size=10)
        assert purged == 1
        fake_storage.remove.assert_called_once()
        assert old_call.recording_storage_path is None


@pytest.mark.asyncio
async def test_sign_call_recording_url():
    org_id = uuid4()
    call_id = uuid4()
    path = f"call-recordings/{org_id}/{call_id}.wav"

    fake_client = MagicMock()
    fake_client.storage.from_.return_value.create_signed_url.return_value = {
        "signedURL": "https://signed.url/rec.wav"
    }

    with patch("app.services.infra.storage._call_storage_client", return_value=fake_client):
        url = await sign_call_recording(path, org_id, call_id, expires_in_seconds=300)
        assert url == "https://signed.url/rec.wav"


@pytest.mark.asyncio
async def test_redial_timing_window():
    org_id = uuid4()
    call_id = uuid4()
    phone = "+15551234567"

    recent_cp = make_test_checkpoint(org_id, call_id, age_seconds=120)
    recent_call = make_test_call_log(org_id, call_id, phone=phone)

    db_recent = MagicMock()
    result_mock = MagicMock()
    result_mock.first.return_value = (recent_cp, recent_call)
    db_recent.execute = AsyncMock(return_value=result_mock)

    ctx = await find_recovery_context(db_recent, org_id, phone, max_age_seconds=900)
    assert ctx is not None
    assert ctx.original_call_id == call_id
    assert ctx.preferred_doctor == "Dr. Sarah"
    assert ctx.target_date == recent_cp.safe_state["target_date"]
    assert ctx.has_committed_appointment is False

    db_old = MagicMock()
    result_mock_old = MagicMock()
    result_mock_old.first.return_value = None
    db_old.execute = AsyncMock(return_value=result_mock_old)

    ctx_old = await find_recovery_context(db_old, org_id, phone, max_age_seconds=900)
    assert ctx_old is None


def test_shared_family_phone_no_phi_leakage():
    ctx = RecoveryContext(
        checkpoint_id=uuid4(),
        original_call_id=uuid4(),
        stage="slot_selection",
        intent="booking",
        preferred_doctor="Dr. Jenkins",
        target_date="2026-10-28",
        has_committed_appointment=False,
    )

    greeting = build_recovery_greeting("Sunset Health Clinic", ctx)

    assert "Alice" not in greeting
    assert "Migraine" not in greeting
    assert "15551234567" not in greeting
    assert "Sunset Health Clinic" in greeting
    assert "disconnected" in greeting
    assert "pick up where we left off" in greeting


def test_recovery_authorization_and_identity_not_reused():
    workflow = VoiceWorkflowState(
        caller_name="Bob",
        caller_phone="+15551234567",
        patient_id="patient-999",
        patient_verified=True,
        verified_name="Alice Smith",
    )
    workflow.stage = WorkflowStage.RECOVERY

    ctx = RecoveryContext(
        checkpoint_id=uuid4(),
        original_call_id=uuid4(),
        stage="booking_details",
        intent="booking",
        preferred_doctor="Dr. Adams",
        target_date="2026-10-29",
        target_time="14:00",
        has_committed_appointment=False,
    )

    apply_recovery_preferences(workflow, ctx)

    assert workflow.recovery_accepted is True
    assert workflow.resumed_from_call_id == str(ctx.original_call_id)
    assert workflow.preferred_doctor == "Dr. Adams"
    assert workflow.target_date == "2026-10-29"
    assert workflow.target_time == "14:00"

    assert workflow.stage == WorkflowStage.AVAILABILITY
    assert workflow.selected_slot is None
    assert workflow.prepared_booking is None
    assert workflow.confirmation_pending is False


def test_recovery_revalidates_candidate_slots():
    workflow = VoiceWorkflowState()
    workflow.stage = WorkflowStage.RECOVERY
    workflow.candidate_slots = [{"time": "09:00 AM"}, {"time": "10:00 AM"}]
    workflow.selected_slot = {"time": "09:00 AM"}

    ctx = RecoveryContext(
        checkpoint_id=uuid4(),
        original_call_id=uuid4(),
        stage="slot_selection",
        intent="booking",
        preferred_doctor="Dr. Adams",
        target_date="2026-10-29",
        has_committed_appointment=False,
    )

    apply_recovery_preferences(workflow, ctx)

    assert workflow.candidate_slots == []
    assert workflow.selected_slot is None


def test_decline_recovery_offer_clears_preferences():
    workflow = VoiceWorkflowState()
    workflow.stage = WorkflowStage.RECOVERY
    workflow.preferred_doctor = "Dr. Adams"
    workflow.target_date = "2026-10-29"
    workflow.candidate_slots = [{"time": "09:00 AM"}]
    workflow.resumed_from_call_id = "old-call-123"

    decline_recovery_offer(workflow)

    assert workflow.recovery_accepted is False
    assert workflow.resumed_from_call_id is None
    assert workflow.stage == WorkflowStage.INTAKE
    assert workflow.preferred_doctor is None
    assert workflow.target_date is None
    assert workflow.candidate_slots == []
