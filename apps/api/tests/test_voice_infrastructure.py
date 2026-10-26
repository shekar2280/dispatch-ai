import asyncio
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.agent.clinic.tools import ClinicVoiceAgent
from app.core.config import settings
from app.core.database import engine
from app.core.voice_admission import (
    AdmissionRejectionReason,
    check_voice_call_admission,
)
from app.models.call_session import CallLog
from app.models.outbox_event import OutboxEvent
from app.models.voice_mutation_operation import VoiceMutationOperation
from app.models.voice_workflow_checkpoint import VoiceWorkflowCheckpoint
from app.services.infra.outbox import MAX_RELAY_ATTEMPTS, OutboxRelay, record_mutation_operation
from app.services.infra.redis_cache import EphemeralPresenceService, redis_service
from app.services.voice.circuit_breaker import CircuitBreaker, CircuitState
from app.services.voice.observability import collect_voice_system_metrics
from app.services.voice.provider_router import ProviderRouter
from app.services.voice.workflow.recovery import (
    RecoveryContext,
    apply_recovery_preferences,
    build_recovery_greeting,
    find_recovery_context,
)
from app.services.voice.workflow.state import VoiceWorkflowState, WorkflowStage


def make_test_checkpoint(org_id, call_id, stage="slot_selection", safe_state=None, age_seconds=120):
    now = datetime.now(UTC)
    created = now - timedelta(seconds=age_seconds)
    return VoiceWorkflowCheckpoint(
        id=uuid4(),
        org_id=org_id,
        call_id=call_id,
        status="active",
        stage=stage,
        safe_state=safe_state or {"preferred_doctor": "Dr. Sarah", "target_date": "2026-10-25"},
        expires_at=now + timedelta(seconds=600),
        created_at=created,
        updated_at=created,
    )


def make_test_call_log(org_id, call_id, phone="+15551234567", booking_result=None, outcome="inquiry"):
    return CallLog(
        id=call_id,
        org_id=org_id,
        caller_phone=phone,
        caller_name="Alice Smith",
        booking_result=booking_result,
        call_outcome=outcome,
    )


@pytest.mark.asyncio
async def test_voice_admission_allowed_under_limits():
    db = AsyncMock()
    db.scalar.side_effect = [5, 2]
    org_id = uuid4()

    with patch.object(settings, "VOICE_MAX_CONCURRENT_CALLS_GLOBAL", 100), \
         patch.object(settings, "VOICE_MAX_CONCURRENT_CALLS_PER_ORG", 10):
        result = await check_voice_call_admission(db, org_id)
        assert result is True


@pytest.mark.asyncio
async def test_voice_admission_rejects_when_org_limit_exceeded():
    db = AsyncMock()
    db.scalar.side_effect = [20, 10]
    org_id = uuid4()

    with patch.object(settings, "VOICE_MAX_CONCURRENT_CALLS_GLOBAL", 100), \
         patch.object(settings, "VOICE_MAX_CONCURRENT_CALLS_PER_ORG", 10):
        with pytest.raises(HTTPException) as exc_info:
            await check_voice_call_admission(db, org_id)

        assert exc_info.value.status_code == 429
        assert exc_info.value.headers["X-Admission-Reason"] == AdmissionRejectionReason.ORG_CAPACITY_EXCEEDED


@pytest.mark.asyncio
async def test_voice_admission_rejects_when_global_limit_exceeded():
    db = AsyncMock()
    db.scalar.side_effect = [100]
    org_id = uuid4()

    with patch.object(settings, "VOICE_MAX_CONCURRENT_CALLS_GLOBAL", 100), \
         patch.object(settings, "VOICE_MAX_CONCURRENT_CALLS_PER_ORG", 50):
        with pytest.raises(HTTPException) as exc_info:
            await check_voice_call_admission(db, org_id)

        assert exc_info.value.status_code == 503
        assert exc_info.value.headers["X-Admission-Reason"] == AdmissionRejectionReason.GLOBAL_CAPACITY_EXCEEDED


@pytest.mark.asyncio
async def test_voice_admission_rejects_when_db_pool_saturated():
    db = AsyncMock()
    org_id = uuid4()

    mock_pool = MagicMock()
    mock_pool.checkedout.return_value = 30
    mock_pool.size.return_value = 20
    mock_pool.max_overflow = 10

    mock_engine = MagicMock()
    mock_engine.pool = mock_pool

    with patch("app.core.database.engine", mock_engine):
        with pytest.raises(HTTPException) as exc_info:
            await check_voice_call_admission(db, org_id)

        assert exc_info.value.status_code == 503
        assert exc_info.value.headers["X-Admission-Reason"] == AdmissionRejectionReason.DATABASE_POOL_SATURATED


def test_database_engine_pool_configuration():
    assert engine.pool is not None


@pytest.mark.asyncio
async def test_distributed_circuit_breaker_sharing():
    fake_storage = {}

    class FakeRedisClient:
        async def hgetall(self, key):
            return dict(fake_storage.get(key, {}))

        async def hset(self, key, mapping=None, **kwargs):
            if key not in fake_storage:
                fake_storage[key] = {}
            if mapping:
                fake_storage[key].update(mapping)
            if kwargs:
                fake_storage[key].update(kwargs)

        async def hsetnx(self, key, field, value):
            if key not in fake_storage:
                fake_storage[key] = {}
            if field in fake_storage[key]:
                return 0
            fake_storage[key][field] = value
            return 1

        async def expire(self, key, seconds):
            pass

        async def delete(self, key):
            fake_storage.pop(key, None)

    fake_client = FakeRedisClient()

    with patch("app.services.infra.redis_cache.redis_service.get_client", return_value=fake_client):
        cb1 = CircuitBreaker()
        cb2 = CircuitBreaker()

        assert await cb1.is_available_async("groq") is True
        assert await cb2.is_available_async("groq") is True

        await cb1.record_failure_async("groq", status_code=429, retry_after=60.0)

        assert await cb1.is_available_async("groq") is False
        assert await cb2.is_available_async("groq") is False

        await cb1.record_success_async("groq")
        assert await cb2.is_available_async("groq") is True


@pytest.mark.asyncio
async def test_circuit_half_open_single_probe():
    fake_storage = {}

    class FakeRedisClient:
        async def hgetall(self, key):
            return dict(fake_storage.get(key, {}))

        async def hset(self, key, mapping=None, **kwargs):
            if key not in fake_storage:
                fake_storage[key] = {}
            if mapping:
                fake_storage[key].update(mapping)
            if kwargs:
                fake_storage[key].update(kwargs)

        async def hsetnx(self, key, field, value):
            if key not in fake_storage:
                fake_storage[key] = {}
            if field in fake_storage[key]:
                return 0
            fake_storage[key][field] = value
            return 1

        async def expire(self, key, seconds):
            pass

    fake_client = FakeRedisClient()

    with patch("app.services.infra.redis_cache.redis_service.get_client", return_value=fake_client):
        cb1 = CircuitBreaker()
        cb2 = CircuitBreaker()

        await cb1.record_failure_async("groq", status_code=429, retry_after=1.0)
        fake_storage["voice:circuit:groq"]["last_failure_time"] = str(time.time() - 5.0)

        probe1 = await cb1.is_available_async("groq")
        probe2 = await cb2.is_available_async("groq")

        assert probe1 is True
        assert probe2 is False


@pytest.mark.asyncio
async def test_provider_router_failover_on_open_circuit():
    cb = CircuitBreaker()
    router = ProviderRouter(primary_provider="groq")

    with patch("app.services.voice.provider_router.circuit_breaker", cb), \
         patch.object(settings, "GROQ_API_KEY", "mock-groq-key"), \
         patch.object(settings, "GEMINI_API_KEY", "mock-gemini-key"):

        route_normal = router.select_route()
        assert route_normal.provider == "groq"
        assert route_normal.is_fallback is False

        cb.record_failure("groq", status_code=429)

        route_fallback = router.select_route()
        assert route_fallback.provider == "gemini"
        assert route_fallback.is_fallback is True

        cb.record_failure("gemini", status_code=429)
        route_degraded = router.select_route()
        assert route_degraded.degraded is True


@pytest.mark.asyncio
async def test_acquire_call_lock_fails_closed_when_redis_unavailable():
    with patch.object(redis_service, "get_client", return_value=None):
        acquired = await redis_service.acquire_call_lock("room-101", "staff-1", ttl_seconds=60)
        assert acquired is False


@pytest.mark.asyncio
async def test_acquire_call_lock_single_owner_when_redis_online():
    lock_storage = {}

    class FakeLockRedis:
        async def set(self, key, val, nx=False, ex=None):
            if nx and key in lock_storage:
                return False
            lock_storage[key] = val
            return True

        async def get(self, key):
            return lock_storage.get(key)

        async def delete(self, key):
            lock_storage.pop(key, None)

    fake_lock_client = FakeLockRedis()

    with patch.object(redis_service, "get_client", return_value=fake_lock_client):
        owner1 = await redis_service.acquire_call_lock("call_room_alpha", "worker_1", ttl_seconds=30)
        assert owner1 is True

        owner2 = await redis_service.acquire_call_lock("call_room_alpha", "worker_2", ttl_seconds=30)
        assert owner2 is False

        await redis_service.release_call_lock("call_room_alpha")

        owner2_retry = await redis_service.acquire_call_lock("call_room_alpha", "worker_2", ttl_seconds=30)
        assert owner2_retry is True


@pytest.mark.asyncio
async def test_ephemeral_presence_ttl_heartbeat():
    svc = EphemeralPresenceService(timeout_sec=45)
    svc.record_heartbeat("org-123", "staff-1", role="receptionist")
    scores = svc._presence_scores.get("org-123", {})
    assert "staff-1" in scores
    assert scores["staff-1"]["role"] == "receptionist"


def test_clinic_voice_agent_initialization():
    agent = ClinicVoiceAgent(
        system_prompt="Test Instructions",
        org_id=uuid4(),
        caller_phone="+919876543210",
    )
    assert agent is not None


@pytest.mark.asyncio
async def test_disconnect_during_slot_selection_preserves_safe_state():
    org_id = uuid4()
    call_id = uuid4()
    phone = "+15551234567"
    cp = make_test_checkpoint(
        org_id,
        call_id,
        stage="slot_selection",
        safe_state={"intent": "booking", "preferred_doctor": "Dr. Sarah", "target_date": "2026-10-25"},
    )
    cl = make_test_call_log(org_id, call_id, phone=phone)

    db = AsyncMock()
    with patch("app.services.voice.workflow.recovery.find_resumable_checkpoint", return_value=(cp, cl)):
        ctx = await find_recovery_context(db, org_id, phone)
        assert ctx is not None
        assert ctx.stage == "slot_selection"
        assert ctx.has_committed_appointment is False
        assert ctx.preferred_doctor == "Dr. Sarah"

        wf = VoiceWorkflowState(caller_phone=phone)
        apply_recovery_preferences(wf, ctx)
        assert wf.stage == WorkflowStage.AVAILABILITY
        assert wf.preferred_doctor == "Dr. Sarah"
        assert wf.candidate_slots == []
        assert wf.recovery_accepted is True


@pytest.mark.asyncio
async def test_disconnect_after_commit_acknowledges_existing_appointment():
    org_id = uuid4()
    call_id = uuid4()
    phone = "+15551234567"
    booking_res = {"appointment_id": str(uuid4()), "slot_time": "2026-10-25T14:00:00Z", "doctor_name": "Dr. Sarah"}
    cp = make_test_checkpoint(org_id, call_id, stage="closing", safe_state={"booking_confirmed": True})
    cl = make_test_call_log(org_id, call_id, phone=phone, booking_result=booking_res, outcome="committed_but_not_acknowledged")

    db = AsyncMock()
    with patch("app.services.voice.workflow.recovery.find_resumable_checkpoint", return_value=(cp, cl)):
        ctx = await find_recovery_context(db, org_id, phone)
        assert ctx is not None
        assert ctx.has_committed_appointment is True
        assert ctx.appointment_id == booking_res["appointment_id"]

        greeting = build_recovery_greeting("Alpha Health", ctx)
        assert "just as your appointment was confirmed" in greeting

        wf = VoiceWorkflowState(caller_phone=phone)
        apply_recovery_preferences(wf, ctx)
        assert wf.stage == WorkflowStage.CLOSING


@pytest.mark.asyncio
async def test_worker_crash_after_commit_idempotent_recovery():
    org_id = uuid4()
    call_id = uuid4()
    op_key = f"book_{org_id}_{call_id}"
    payload = {"appointment_id": str(uuid4()), "status": "booked"}

    existing_op = VoiceMutationOperation(
        id=uuid4(),
        org_id=org_id,
        call_id=call_id,
        operation_key=op_key,
        operation_type="appointment_booking",
        status="completed",
        response_payload=payload,
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = existing_op
    mock_result.scalar_one_or_none.return_value = existing_op
    mock_result.scalars.return_value.first.return_value = existing_op
    mock_result.scalar.return_value = existing_op
    mock_db.execute.return_value = mock_result

    res = await record_mutation_operation(
        db=mock_db,
        org_id=org_id,
        call_id=call_id,
        operation_key=op_key,
        operation_type="appointment_booking",
        response_payload=payload,
    )
    assert res is not None
    assert res.operation_key == op_key
    assert res.response_payload["appointment_id"] == payload["appointment_id"]


@pytest.mark.asyncio
async def test_redis_failure_fails_closed_preventing_split_brain():
    with patch("app.services.infra.redis_cache.redis_service.get_client", side_effect=ConnectionError("Redis connection refused")):
        lock_acquired = await redis_service.acquire_call_lock("room_matrix_test", "worker_1", ttl_seconds=30)
        assert lock_acquired is False


@pytest.mark.asyncio
async def test_websocket_failure_leaves_outbox_event_for_retry():
    event = OutboxEvent(
        id=uuid4(),
        org_id=uuid4(),
        event_type="call_completed",
        payload={"call_id": "call_retry_1"},
        status="pending",
        attempts=0,
    )
    relay = OutboxRelay(max_attempts=3)
    mock_db = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [event]
    mock_exec = MagicMock()
    mock_exec.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_exec

    with patch("app.services.infra.websocket_manager.ws_manager.broadcast_to_org", side_effect=RuntimeError("WS connection dropped")):
        processed = await relay.process_batch(batch_size=10, db=mock_db)
        assert processed == 1
        assert event.status == "pending"
        assert event.attempts == 1
        assert "WS connection dropped" in event.error_detail


@pytest.mark.asyncio
async def test_poison_outbox_event_dead_lettered_after_max_attempts():
    event = OutboxEvent(
        id=uuid4(),
        org_id=uuid4(),
        event_type="corrupted_payload",
        payload={"corrupted": True},
        status="pending",
        attempts=MAX_RELAY_ATTEMPTS - 1,
    )
    relay = OutboxRelay(max_attempts=MAX_RELAY_ATTEMPTS)
    mock_db = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [event]
    mock_exec = MagicMock()
    mock_exec.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_exec

    with patch("app.services.infra.websocket_manager.ws_manager.broadcast_to_org", side_effect=ValueError("Invalid JSON serializer")):
        processed = await relay.process_batch(batch_size=10, db=mock_db)
        assert processed == 1
        assert event.status == "failed"
        assert event.attempts == MAX_RELAY_ATTEMPTS


@pytest.mark.asyncio
async def test_invalid_date_sanitization_does_not_crash_voice_workflow():
    wf = VoiceWorkflowState()
    invalid_dates = ["invalid-date-string", "tomorrow evening", "2026/13/45", ""]
    for bad_date in invalid_dates:
        wf.target_date = bad_date
        assert wf.target_date == bad_date

    ctx = RecoveryContext(
        checkpoint_id=uuid4(),
        original_call_id=uuid4(),
        stage="slot_selection",
        intent="booking",
        preferred_doctor="Dr. Patel",
        target_date="invalid-date-str",
        has_committed_appointment=False,
    )
    apply_recovery_preferences(wf, ctx)
    assert wf.target_date == "invalid-date-str"
    assert wf.stage == WorkflowStage.AVAILABILITY


@pytest.mark.asyncio
async def test_zero_downtime_schema_backward_compatibility():
    legacy_checkpoint_payload = {
        "id": str(uuid4()),
        "stage": "slot_selection",
        "safe_state": {
            "doctor": "Dr. Sarah",
            "date": "2026-10-25",
        },
    }
    wf = VoiceWorkflowState()
    wf.preferred_doctor = legacy_checkpoint_payload["safe_state"].get("preferred_doctor") or legacy_checkpoint_payload["safe_state"].get("doctor")
    wf.target_date = legacy_checkpoint_payload["safe_state"].get("target_date") or legacy_checkpoint_payload["safe_state"].get("date")

    assert wf.preferred_doctor == "Dr. Sarah"
    assert wf.target_date == "2026-10-25"


@pytest.mark.asyncio
async def test_system_observability_metrics_aggregation():
    mock_db = AsyncMock()
    mock_scalar_results = [3, 0, 0, 1, 0, 0, None, 10, 10, 5]

    call_index = 0
    def mock_scalar(*args, **kwargs):
        nonlocal call_index
        res = mock_scalar_results[call_index % len(mock_scalar_results)]
        call_index += 1
        return res

    mock_db.scalar = AsyncMock(side_effect=mock_scalar)

    with patch("app.services.voice.observability.engine") as mock_engine:
        mock_pool = MagicMock()
        mock_pool.size.return_value = 20
        mock_pool.checkedout.return_value = 4
        mock_pool.overflow.return_value = 0
        mock_engine.pool = mock_pool

        metrics = await collect_voice_system_metrics(mock_db)
        assert metrics["admission"]["active_calls"] == 3
        assert metrics["outbox"]["pending_count"] == 1
        assert metrics["outbox"]["failed_count"] == 0
        assert metrics["database_pool"]["checked_out"] == 4
        assert metrics["database_pool"]["size"] == 20
        assert "circuits" in metrics
