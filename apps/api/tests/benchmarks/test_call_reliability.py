import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.agent.clinic.tools import ClinicVoiceAgent
from app.agent.confirmation import ConfirmationGate
from app.services.voice.lifecycle import claim_reconciliation_batch, terminate_call
from app.services.voice.diagnostics import ErrorCategory, classify_provider_error


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
        self.call_status = kwargs.get("call_status", "in_progress")
        self.call_outcome = kwargs.get("call_outcome", "in_progress")
        self.duration_seconds = kwargs.get("duration_seconds", 0)
        self.telemetry_summary = kwargs.get("telemetry_summary", {})
        self.recording_status = kwargs.get("recording_status", "disabled")
        self.recording_storage_path = kwargs.get("recording_storage_path")



class MockAsyncDbSession:
    def __init__(self, calls_map=None):
        self.calls_map = calls_map or {}
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def scalars(self, query):
        items = list(self.calls_map.values())
        res = MagicMock()
        res.all.return_value = items
        return res

    async def scalar(self, query):
        for call in self.calls_map.values():
            return call
        return None

    async def commit(self):
        self.committed = True


def test_interruption_barge_in_cancels_proposal():
    gate = ConfirmationGate()
    proposal = {
        "first_name": "David",
        "last_name": "Miller",
        "slot_date": "2026-10-22",
        "slot_time": "03:00 PM",
        "doctor_name": "Dr. Sunita Rao",
        "booking_mode": "appointment",
    }
    gate.propose(proposal)
    gate.readback("turn-1", "Shall I book David Miller with Dr. Sunita on October 22 at 3 PM?", interrupted=True)
    gate.observe("turn-2", "Yes, please.")
    assert gate.permits(proposal) is False

    gate.readback("turn-3", "Shall I book David Miller with Dr. Sunita on October 22 at 3 PM?", interrupted=False)
    gate.observe("turn-4", "Yes, that is correct.")
    assert gate.permits(proposal) is True


@pytest.mark.asyncio
async def test_graceful_call_termination_and_duration_accounting():
    call_id = uuid.uuid4()
    org_id = uuid.uuid4()
    started_at = datetime.now(UTC) - timedelta(seconds=45)

    call = MockCall(
        call_id=call_id,
        org_id=org_id,
        provider_started_at=started_at,
        call_status="in_progress",
    )
    mock_db = MockAsyncDbSession({call_id: call})

    with (
        patch("app.services.voice.lifecycle.AsyncSessionLocal", return_value=mock_db),
        patch("app.services.voice.lifecycle._cleanup_livekit", new_callable=AsyncMock) as mock_lk,
        patch("app.services.voice.lifecycle._cleanup_twilio", new_callable=AsyncMock) as mock_tw,
        patch("app.services.voice.call_logger_service.flush_pending_turns", new_callable=AsyncMock),
    ):
        mock_lk.return_value = True
        mock_tw.return_value = True
        await terminate_call(call_id, org_id, "caller_hung_up")

        assert call.call_status == "completed"
        assert call.end_reason == "caller_hung_up"
        assert call.end_time is not None
        assert call.duration_seconds >= 44
        assert call.media_terminated_at is not None
        assert mock_db.committed is True
        assert mock_lk.await_count == 1
        assert mock_tw.await_count == 1


@pytest.mark.asyncio
async def test_worker_crash_reconciliation_lease_claim():
    now = datetime.now(UTC)
    c1_id = uuid.uuid4()
    org_id = uuid.uuid4()
    c1 = MockCall(
        c1_id,
        org_id,
        deadline_at=now - timedelta(seconds=10),
        call_status="in_progress",
    )
    mock_db = MockAsyncDbSession({c1_id: c1})

    with patch("app.services.voice.lifecycle.AsyncSessionLocal", return_value=mock_db):
        batch = await claim_reconciliation_batch("worker_alpha", batch_size=5, lease_duration_seconds=30)

    assert len(batch) == 1
    assert batch[0]["call_id"] == c1_id
    assert batch[0]["attempts"] == 1
    assert c1.telemetry_summary["reconcile_lease"]["owner"] == "worker_alpha"
    assert mock_db.committed is True



@pytest.mark.asyncio
async def test_transient_provider_error_recovery():
    agent = ClinicVoiceAgent(system_prompt="Test Prompt")
    chat_ctx = MagicMock()
    chat_ctx.to_dict.return_value = {"messages": []}

    with patch("livekit.agents.voice.Agent.default.llm_node") as mock_node:
        async def failing_node(*args, **kwargs):
            raise ConnectionResetError("Remote cloud provider reset connection")
            yield "chunk"

        mock_node.side_effect = failing_node
        with patch("app.services.voice.provider_budget.reserve_llm", new_callable=AsyncMock):
            chunks = []
            async for chunk in agent.llm_node(chat_ctx, [], None):
                chunks.append(chunk)

            assert len(chunks) == 1
            assert "Pardon me" in chunks[0]
            assert agent.state["service_unavailable"] is True
