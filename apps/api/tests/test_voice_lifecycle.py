"""Regression tests for voice lifecycle."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.worker import prewarm
from app.services.voice.lifecycle import (
    _cleanup_livekit,
    _cleanup_twilio,
    claim_reconciliation_batch,
    reconcile_claimed_call,
    terminate_call,
)
from app.services.voice.retention import (
    purge_expired_audio_recordings,
    redact_expired_transcripts,
    run_daily_retention_sweep,
)


class MockCall:
    def __init__(self, call_id, org_id, **kwargs):
        self.id = call_id
        self.org_id = org_id
        self.room_name = kwargs.get("room_name", f"room_{call_id}")
        self.provider_call_sid = kwargs.get("provider_call_sid", f"sid_{call_id}")
        self.media_terminated_at = kwargs.get("media_terminated_at")
        self.end_time = kwargs.get("end_time")
        self.end_reason = kwargs.get("end_reason")
        self.provider_started_at = kwargs.get("provider_started_at")
        self.admission_expires_at = kwargs.get("admission_expires_at")
        self.deadline_at = kwargs.get("deadline_at")
        self.call_status = kwargs.get("call_status", "ringing")
        self.call_outcome = kwargs.get("call_outcome", "in_progress")
        self.recording_status = kwargs.get("recording_status", "disabled")
        self.recording_storage_path = kwargs.get("recording_storage_path")
        self.duration_seconds = kwargs.get("duration_seconds", 0)
        self.telemetry_summary = kwargs.get("telemetry_summary", {})


class MockScalarResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class MockAsyncDbSession:
    def __init__(self, calls_map=None):
        self.calls_map = calls_map or {}
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def scalars(self, query):
        return MockScalarResult(list(self.calls_map.values()))

    async def scalar(self, query):
        for call in self.calls_map.values():
            return call
        return None

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_claim_reconciliation_batch_sets_lease():
    now = datetime.now(UTC)
    c1_id = uuid.uuid4()
    org_id = uuid.uuid4()
    c1 = MockCall(
        c1_id,
        org_id,
        deadline_at=now - timedelta(seconds=10),
        telemetry_summary={},
    )
    mock_db = MockAsyncDbSession({c1_id: c1})

    with patch("app.services.voice.lifecycle.AsyncSessionLocal", return_value=mock_db):
        claimed = await claim_reconciliation_batch("worker_alpha", batch_size=10, lease_duration_seconds=30)

    assert len(claimed) == 1
    assert claimed[0]["call_id"] == c1_id
    assert claimed[0]["attempts"] == 1
    assert mock_db.committed is True
    assert c1.telemetry_summary["reconcile_lease"]["owner"] == "worker_alpha"


@pytest.mark.asyncio
async def test_claim_skips_active_unexpired_lease():
    now = datetime.now(UTC)
    c1_id = uuid.uuid4()
    org_id = uuid.uuid4()
    c1 = MockCall(
        c1_id,
        org_id,
        deadline_at=now - timedelta(seconds=10),
        telemetry_summary={
            "reconcile_lease": {
                "owner": "worker_alpha",
                "lease_until": (now + timedelta(seconds=20)).isoformat(),
                "attempts": 1,
            }
        },
    )
    mock_db = MockAsyncDbSession({c1_id: c1})

    with patch("app.services.voice.lifecycle.AsyncSessionLocal", return_value=mock_db):
        claimed = await claim_reconciliation_batch("worker_beta", batch_size=10)

    assert len(claimed) == 0


@pytest.mark.asyncio
async def test_claim_reclaims_expired_crashed_lease():
    now = datetime.now(UTC)
    c1_id = uuid.uuid4()
    org_id = uuid.uuid4()
    c1 = MockCall(
        c1_id,
        org_id,
        deadline_at=now - timedelta(seconds=10),
        telemetry_summary={
            "reconcile_lease": {
                "owner": "crashed_worker",
                "lease_until": (now - timedelta(seconds=5)).isoformat(),
                "attempts": 1,
            }
        },
    )
    mock_db = MockAsyncDbSession({c1_id: c1})

    with patch("app.services.voice.lifecycle.AsyncSessionLocal", return_value=mock_db):
        claimed = await claim_reconciliation_batch("worker_healer", batch_size=10)

    assert len(claimed) == 1
    assert claimed[0]["attempts"] == 2
    assert c1.telemetry_summary["reconcile_lease"]["owner"] == "worker_healer"


@pytest.mark.asyncio
async def test_claim_respects_exponential_backoff():
    now = datetime.now(UTC)
    c1_id = uuid.uuid4()
    org_id = uuid.uuid4()
    c1 = MockCall(
        c1_id,
        org_id,
        deadline_at=now - timedelta(seconds=10),
        telemetry_summary={
            "reconcile_lease": {
                "next_retry_at": (now + timedelta(seconds=45)).isoformat(),
                "attempts": 2,
            }
        },
    )
    mock_db = MockAsyncDbSession({c1_id: c1})

    with patch("app.services.voice.lifecycle.AsyncSessionLocal", return_value=mock_db):
        claimed = await claim_reconciliation_batch("worker_any", batch_size=10)

    assert len(claimed) == 0


@pytest.mark.asyncio
async def test_reconcile_claimed_call_success():
    now = datetime.now(UTC)
    c1_id = uuid.uuid4()
    org_id = uuid.uuid4()
    c1 = MockCall(
        c1_id,
        org_id,
        provider_started_at=now - timedelta(seconds=60),
        telemetry_summary={"reconcile_lease": {"owner": "worker_1"}},
    )
    mock_db = MockAsyncDbSession({c1_id: c1})

    item = {
        "call_id": c1_id,
        "org_id": org_id,
        "room_name": "room-123",
        "provider_call_sid": "CA123",
        "livekit_cleaned": False,
        "twilio_cleaned": False,
    }

    with (
        patch("app.services.voice.lifecycle.AsyncSessionLocal", return_value=mock_db),
        patch("app.services.voice.lifecycle._cleanup_livekit", new_callable=AsyncMock, return_value=True),
        patch("app.services.voice.lifecycle._cleanup_twilio", new_callable=AsyncMock, return_value=True),
    ):
        ok = await reconcile_claimed_call(item, "worker_1", "time_limit")

    assert ok is True
    assert c1.media_terminated_at is not None
    assert c1.end_reason == "time_limit"
    assert c1.call_status == "completed"
    assert "owner" not in c1.telemetry_summary["reconcile_lease"]
    assert c1.telemetry_summary["reconcile_lease"]["livekit_cleaned"] is True
    assert c1.telemetry_summary["reconcile_lease"]["twilio_cleaned"] is True


@pytest.mark.asyncio
async def test_reconcile_claimed_call_partial_transport_failure():
    now = datetime.now(UTC)
    c1_id = uuid.uuid4()
    org_id = uuid.uuid4()
    c1 = MockCall(
        c1_id,
        org_id,
        provider_started_at=now - timedelta(seconds=60),
        telemetry_summary={"reconcile_lease": {"owner": "worker_1", "attempts": 1}},
    )
    mock_db = MockAsyncDbSession({c1_id: c1})

    item = {
        "call_id": c1_id,
        "org_id": org_id,
        "room_name": "room-123",
        "provider_call_sid": "CA123",
        "livekit_cleaned": False,
        "twilio_cleaned": False,
    }

    with (
        patch("app.services.voice.lifecycle.AsyncSessionLocal", return_value=mock_db),
        patch("app.services.voice.lifecycle._cleanup_livekit", new_callable=AsyncMock, return_value=False),
        patch("app.services.voice.lifecycle._cleanup_twilio", new_callable=AsyncMock, return_value=True),
    ):
        ok = await reconcile_claimed_call(item, "worker_1", "time_limit")

    assert ok is False
    assert c1.media_terminated_at is None
    assert c1.telemetry_summary["reconcile_lease"]["livekit_cleaned"] is False
    assert c1.telemetry_summary["reconcile_lease"]["twilio_cleaned"] is True
    assert "next_retry_at" in c1.telemetry_summary["reconcile_lease"]


@pytest.mark.asyncio
async def test_reconcile_claimed_call_rejects_stale_owner():
    c1_id = uuid.uuid4()
    org_id = uuid.uuid4()
    c1 = MockCall(
        c1_id,
        org_id,
        telemetry_summary={"reconcile_lease": {"owner": "worker_new"}},
    )
    mock_db = MockAsyncDbSession({c1_id: c1})

    item = {
        "call_id": c1_id,
        "org_id": org_id,
        "room_name": "room-123",
        "provider_call_sid": "CA123",
        "livekit_cleaned": False,
        "twilio_cleaned": False,
    }

    with (
        patch("app.services.voice.lifecycle.AsyncSessionLocal", return_value=mock_db),
        patch("app.services.voice.lifecycle._cleanup_livekit", new_callable=AsyncMock, return_value=True),
        patch("app.services.voice.lifecycle._cleanup_twilio", new_callable=AsyncMock, return_value=True),
    ):
        ok = await reconcile_claimed_call(item, "worker_stale", "time_limit")

    assert ok is False
    assert c1.media_terminated_at is None


@pytest.mark.asyncio
async def test_direct_terminate_call_coexists_with_lease():
    now = datetime.now(UTC)
    c1_id = uuid.uuid4()
    org_id = uuid.uuid4()
    c1 = MockCall(
        c1_id,
        org_id,
        provider_started_at=now - timedelta(seconds=30),
        telemetry_summary={},
    )
    mock_db = MockAsyncDbSession({c1_id: c1})

    with (
        patch("app.services.voice.lifecycle.AsyncSessionLocal", return_value=mock_db),
        patch("app.services.voice.lifecycle._cleanup_livekit", new_callable=AsyncMock, return_value=True),
        patch("app.services.voice.lifecycle._cleanup_twilio", new_callable=AsyncMock, return_value=True),
    ):
        await terminate_call(c1_id, org_id, "staff_hangup")

    assert c1.media_terminated_at is not None
    assert c1.end_reason == "staff_hangup"


@pytest.mark.asyncio
async def test_cleanup_livekit_handles_exceptions_gracefully():
    with patch("livekit.api.LiveKitAPI") as mock_lk:
        mock_lk.side_effect = RuntimeError("LiveKit cluster unreachable")
        success = await _cleanup_livekit("test-room-123")
        assert success is False


@pytest.mark.asyncio
async def test_cleanup_twilio_handles_exceptions_gracefully():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = RuntimeError("Twilio network error")
        with (
            patch("app.core.config.settings.TWILIO_ACCOUNT_SID", "ACtest"),
            patch("app.core.config.settings.TWILIO_AUTH_TOKEN", "token"),
        ):
            success = await _cleanup_twilio("CA123456789")
            assert success is False


@pytest.mark.asyncio
async def test_cleanup_skips_when_identifiers_empty():
    assert await _cleanup_livekit(None) is True
    assert await _cleanup_twilio(None) is True


class RetentionCall:
    def __init__(self, call_id, org_id, **kwargs):
        self.id = call_id
        self.org_id = org_id
        self.end_time = kwargs.get("end_time")
        self.recording_status = kwargs.get("recording_status", "ready")
        self.recording_storage_path = kwargs.get("recording_storage_path", f"call-recordings/{org_id}/{call_id}.wav")
        self.quota_charged_at = kwargs.get("quota_charged_at")
        self.caller_phone = kwargs.get("caller_phone", "+1234567890")
        self.caller_name = kwargs.get("caller_name", "Test Patient")
        self.full_transcript = kwargs.get("full_transcript", "Hello doctor")
        self.turns = kwargs.get("turns", [{"role": "user", "text": "Hello"}])
        self.booking_proposal = kwargs.get("booking_proposal", {"slot": "10:00"})
        self.booking_result = kwargs.get("booking_result", {"status": "confirmed"})
        self.telemetry_summary = kwargs.get("telemetry_summary", {})


class RetentionRows:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class RetentionSession:
    def __init__(self, calls=None):
        self.calls = calls or []
        self.committed = False
        self.executed_queries = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def scalars(self, query):
        return RetentionRows(self.calls)

    async def execute(self, statement, params=None):
        self.executed_queries.append((statement, params))
        return RetentionRows([])

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_purge_expired_audio_recordings():
    now = datetime.now(UTC)
    old_call_id = uuid.uuid4()
    org_id = uuid.uuid4()
    old_call = RetentionCall(
        old_call_id,
        org_id,
        end_time=now - timedelta(days=10),
        recording_status="ready",
        recording_storage_path=f"call-recordings/{org_id}/{old_call_id}.wav",
    )
    mock_db = RetentionSession([old_call])

    mock_storage = MagicMock()
    mock_storage.storage.from_.return_value.remove.return_value = None

    with (
        patch("app.services.voice.retention.AsyncSessionLocal", return_value=mock_db),
        patch("app.services.voice.retention._call_storage_client", return_value=mock_storage),
    ):
        count = await purge_expired_audio_recordings(batch_size=10)

    assert count == 1
    assert old_call.recording_storage_path is None
    assert old_call.recording_status == "disabled"
    assert "audio_purged_at" in old_call.telemetry_summary
    assert mock_db.committed is True


@pytest.mark.asyncio
async def test_redact_expired_transcripts():
    now = datetime.now(UTC)
    call_id = uuid.uuid4()
    org_id = uuid.uuid4()
    call = RetentionCall(
        call_id,
        org_id,
        end_time=now - timedelta(days=45),
        quota_charged_at=now - timedelta(days=45),
        caller_phone="+1987654321",
    )
    mock_db = RetentionSession([call])

    with patch("app.services.voice.retention.AsyncSessionLocal", return_value=mock_db):
        count = await redact_expired_transcripts(batch_size=10)

    assert count == 1
    assert call.caller_phone == "Redacted"
    assert call.caller_name is None
    assert call.full_transcript is None
    assert call.turns == []
    assert call.booking_proposal is None
    assert call.booking_result is None
    assert "transcript_redacted_at" in call.telemetry_summary
    assert mock_db.committed is True


@pytest.mark.asyncio
async def test_run_daily_retention_sweep_orchestration():
    with (
        patch("app.services.voice.retention.purge_expired_audio_recordings", new_callable=AsyncMock, return_value=3),
        patch("app.services.voice.retention.redact_expired_transcripts", new_callable=AsyncMock, return_value=1),
        patch("app.services.voice.retention.prune_limit_windows", new_callable=AsyncMock),
    ):
        res = await run_daily_retention_sweep()

    assert res["purged_audio"] == 3
    assert res["redacted_transcripts"] == 1


class DummyProcess:
    def __init__(self):
        self.userdata = {}


def test_prewarm_populates_userdata_vad():
    proc = DummyProcess()
    prewarm(proc)
    assert "vad" in proc.userdata
    vad = proc.userdata["vad"]
    assert vad is not None
    assert hasattr(vad, "stream")
