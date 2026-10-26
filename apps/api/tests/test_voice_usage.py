"""Regression tests for voice usage."""

import asyncio
import math
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from livekit.agents import llm
from livekit.agents.voice import Agent

from app.agent.clinic.tools import ClinicVoiceAgent
from app.agent.confirmation import ConfirmationGate
from app.core.voice_admission import client_window
from app.main import app
from app.models.call_session import VoiceCallSession
from app.models.organization import Organization
from app.services.infra.websocket_manager import DispatchWebSocketManager
from app.services.voice.call_logger_service import (
    _TURN_QUEUE,
    finalize_voice_session,
    queue_voice_turn,
    start_voice_session,
)
from app.services.voice.provider_budget import BudgetReservation, settle_llm
from app.services.voice.telemetry import VoiceTelemetry, benchmark_summary, milliseconds


@pytest.mark.asyncio
async def test_stream_reconciles_provider_usage_before_next_request():
    agent = ClinicVoiceAgent("Clinic receptionist")
    reservation = BudgetReservation("key", datetime.now(timezone.utc), 35000)
    usage_chunk = SimpleNamespace(usage=SimpleNamespace(total_tokens=4800))

    async def stream(*args):
        yield "How can I help?"
        yield usage_chunk

    with (
        patch("app.services.voice.provider_budget.reserve_llm", AsyncMock(return_value=reservation)),
        patch("app.services.voice.provider_budget.settle_llm", AsyncMock()) as settle,
        patch.object(Agent.default, "llm_node", stream),
    ):
        assert len([chunk async for chunk in agent.llm_node(llm.ChatContext(), [], None)]) == 2
        settle.assert_awaited_once_with(reservation, 4800)


@pytest.mark.asyncio
async def test_settlement_preserves_request_count_and_is_not_repeated():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=db)
    context.__aexit__ = AsyncMock(return_value=False)
    reservation = BudgetReservation("key", datetime.now(timezone.utc), 35000)
    with patch("app.services.voice.provider_budget.AsyncSessionLocal", return_value=context):
        await settle_llm(reservation, 4800)
        await settle_llm(reservation, 4800)
    assert db.execute.await_count == 2
    statement, values = db.execute.await_args_list[1].args
    assert values["delta"] == -30200
    assert "attempts=" not in str(statement)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_budget_refusal_notice_is_spoken_only_once():
    agent = ClinicVoiceAgent("Clinic receptionist")
    with patch("app.services.voice.provider_budget.reserve_llm", AsyncMock(side_effect=HTTPException(429))) as reserve:
        assert len([c async for c in agent.llm_node(llm.ChatContext(), [], None)]) == 1
        assert [c async for c in agent.llm_node(llm.ChatContext(), [], None)] == []
        reserve.assert_awaited_once()


def test_okay_requires_a_completed_readback_and_unchanged_details():
    gate = ConfirmationGate()
    details = {"name": "Test Patient", "time": "04:45 PM"}
    gate.observe("first", "okay")
    gate.propose(details)
    gate.observe("next", "Okay.")
    assert not gate.permits(details)
    gate.readback("readback")
    assert gate.permits(details)
    gate.observe("correction", "Okay, but at five")
    assert not gate.permits(details)


def test_start_voice_session_lifecycle():
    async def _runner():
        org_id = uuid4()
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=Organization(id=org_id, name="Test Clinic"))
        )

        session = await start_voice_session(
            db=mock_db,
            org_id=org_id,
            caller_phone="+919876543210",
            caller_name="Test Caller",
            session_type="voice_simulator",
            room_name="test_room_1",
        )

        assert session is not None
        assert session.caller_phone == "+919876543210"
        assert session.caller_name == "Test Caller"
        assert session.session_type == "voice_simulator"
        assert session.room_name == "test_room_1"
        assert session.triage_status == "admin"
        assert session.call_outcome == "inquiry"
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()

    asyncio.run(_runner())


def test_finalize_voice_session_duration():
    async def _runner():
        session_id = uuid4()
        org_id = uuid4()
        start_time = datetime.now(timezone.utc) - timedelta(seconds=45)
        existing_session = VoiceCallSession(
            id=session_id,
            org_id=org_id,
            caller_phone="+919876543210",
            start_time=start_time,
            triage_status="admin",
            call_outcome="inquiry",
        )

        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=existing_session))

        finalized = await finalize_voice_session(
            db=mock_db,
            session_id=session_id,
            call_outcome="appointment_booked",
            full_transcript="Caller asked for appointment and confirmed slot.",
            triage_status="completed",
        )

        assert finalized is not None
        assert finalized.call_outcome == "appointment_booked"
        assert finalized.triage_status == "completed"
        assert finalized.duration_seconds >= 44
        assert finalized.full_transcript == "Caller asked for appointment and confirmed slot."
        assert finalized.end_time is not None
        mock_db.commit.assert_awaited_once()

    asyncio.run(_runner())


def test_queue_voice_turn_push():
    while not _TURN_QUEUE.empty():
        _TURN_QUEUE.get_nowait()

    session_id = uuid4()
    org_id = uuid4()

    queue_voice_turn(
        session_id=session_id,
        org_id=org_id,
        turn_number=1,
        user_transcript="Hello, I need an appointment",
        stt_latency_ms=120,
        total_latency_ms=350,
    )

    assert not _TURN_QUEUE.empty()
    queued_item = _TURN_QUEUE.get_nowait()
    assert queued_item.session_id == session_id
    assert queued_item.turn_number == 1
    assert queued_item.user_transcript == "Hello, I need an appointment"
    assert queued_item.stt_latency_ms == 120


def test_get_daily_call_logs_unauthenticated():
    client = TestClient(app)
    response = client.get("/api/v1/voice/daily-call-logs")
    assert response.status_code == 401


@patch("app.api.v1.calls.AsyncSessionLocal")
def test_get_daily_call_logs_tenant_isolation(mock_session_local):
    from app.core.security import get_current_tenant_org

    org_target = uuid4()

    target_session = VoiceCallSession(
        id=uuid4(),
        org_id=org_target,
        caller_phone="+919876543210",
        caller_name="Target Patient",
        start_time=datetime.now(timezone.utc),
        duration_seconds=60,
        triage_status="ADMIN",
        call_outcome="completed",
        attended_by="AI",
        chief_complaint="Fever",
    )

    mock_db = AsyncMock()
    mock_db.get.return_value = MagicMock(timezone="Asia/Kolkata")
    mock_counts_res = MagicMock()
    mock_counts_res.mappings.return_value.one.return_value = {
        "historical": 1,
        "today": 1,
        "missed_today": 0,
        "emergency_today": 0,
        "human_today": 0,
        "ai_today": 1,
        "scope_all": 1,
        "scope_missed": 0,
        "scope_emergency": 0,
        "scope_ai": 1,
    }
    mock_sessions_res = MagicMock()
    mock_sessions_res.scalars.return_value.all.return_value = [target_session]
    mock_booked_res = MagicMock()
    mock_booked_res.scalars.return_value.all.return_value = []
    mock_db.execute.side_effect = [mock_counts_res, mock_sessions_res, mock_booked_res]
    mock_session_local.return_value.__aenter__.return_value = mock_db

    app.dependency_overrides[get_current_tenant_org] = lambda: org_target
    try:
        client = TestClient(app)
        response = client.get("/api/v1/voice/daily-call-logs")

        assert response.status_code == 200
        body = response.json()
        assert "metrics" in body
        assert "logs" in body
        assert len(body["logs"]) == 1
        assert body["logs"][0]["caller_name"] == "Target Patient"
        assert body["metrics"]["total_calls_today"] == 1
    finally:
        app.dependency_overrides.pop(get_current_tenant_org, None)


@patch("app.api.v1.telephony_webhook.AsyncSessionLocal")
def test_telephony_webhook_hotline_attribute(mock_session_local, monkeypatch):
    from twilio.request_validator import RequestValidator

    from app.core.config import settings

    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "test-only-twilio-signature-key")
    org_id = uuid4()
    matched_org = Organization(
        id=org_id,
        name="Metro Clinic",
        phone="+12694042034",
        hotline="+12694042034",
    )
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.execute.side_effect = [
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[matched_org])))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))),
    ]
    mock_session_local.return_value.__aenter__.return_value = mock_db

    client = TestClient(app)
    data = {"To": "+12694042034", "From": "+919876543210", "CallSid": "test_call_sid_123"}
    signature = RequestValidator(settings.TWILIO_AUTH_TOKEN).compute_signature(
        "http://testserver/api/v1/telephony/twilio/inbound", data
    )
    with (
        patch("app.services.telephony.twilio_service.enforce_voice_demo_allowance", AsyncMock(return_value=120)),
        patch("app.services.telephony.twilio_service.ws_manager.broadcast_to_org", AsyncMock()),
    ):
        response = client.post("/api/v1/telephony/twilio/inbound", data=data, headers={"X-Twilio-Signature": signature})

    assert response.status_code == 200
    assert "xml" in response.headers["content-type"]
    assert "<Dial" in response.text


def test_missing_measurements_are_unknown_and_never_reported_as_fast():
    summary = benchmark_summary([])
    assert all(item["sample_count"] == 0 and item["target_met"] is None for item in summary.values())
    assert milliseconds(-1) is None and milliseconds(math.nan) is None


def test_real_metric_fields_are_correlated_by_speech_id_and_converted_to_ms():
    telemetry = VoiceTelemetry()
    telemetry.record(
        SimpleNamespace(type="tts_metrics", speech_id="turn-1", request_id="tts-1", ttfb=0.2, cancelled=False)
    )
    telemetry.record(
        SimpleNamespace(type="eou_metrics", speech_id="turn-1", transcription_delay=0.15, end_of_utterance_delay=0.25)
    )
    telemetry.record(
        SimpleNamespace(
            type="llm_metrics",
            speech_id="turn-1",
            request_id="llm-1",
            ttft=0.4,
            prompt_tokens=100,
            completion_tokens=30,
        )
    )
    result = telemetry.payload()
    turn = result["turns"][0]
    assert turn["stt_latency_ms"] == 150 and turn["llm_latency_ms"] == 400
    assert turn["tts_latency_ms"] == 200 and turn["total_latency_ms"] == 850
    assert result["prompt_tokens"] == 100 and result["completion_tokens"] == 30


def test_incomplete_or_cancelled_turn_cannot_meet_total_latency_target():
    telemetry = VoiceTelemetry()
    telemetry.record(
        SimpleNamespace(type="tts_metrics", speech_id="turn-1", request_id="tts-1", ttfb=0.1, cancelled=True)
    )
    assert telemetry.payload()["turns"][0]["total_latency_ms"] is None
    assert telemetry.payload()["benchmarks"]["total_latency_ms"]["target_met"] is None


def test_duplicate_requests_do_not_double_count_tokens_and_followups_count_usage():
    telemetry = VoiceTelemetry()
    metric = SimpleNamespace(
        type="llm_metrics", speech_id="turn-1", request_id="one", ttft=0.1, prompt_tokens=10, completion_tokens=5
    )
    telemetry.record(metric)
    telemetry.record(metric)
    telemetry.record(
        SimpleNamespace(
            type="llm_metrics", speech_id="turn-1", request_id="two", ttft=0.8, prompt_tokens=20, completion_tokens=10
        )
    )
    assert telemetry.prompt_tokens == 30 and telemetry.completion_tokens == 15
    assert telemetry.payload()["turns"][0]["llm_latency_ms"] == 100


def test_percentile_and_threshold_fail_on_measured_slow_turns():
    result = benchmark_summary([{"total_latency_ms": 500}, {"total_latency_ms": 1500}])["total_latency_ms"]
    assert result["median_ms"] == 1000 and result["p95_ms"] == 1500
    assert result["target_met"] is False


def test_ip_rate_keys_do_not_store_addresses_and_windows_reset_each_minute():
    now = datetime(2026, 10, 8, 10, 3, 44, tzinfo=timezone.utc)
    digest, window = client_window("192.0.2.1", now)
    assert "192.0.2.1" not in digest and len(digest) == 64
    assert window.second == 0
    assert client_window("192.0.2.1", now.replace(second=59)) == (digest, window)
    assert client_window("192.0.2.1", now.replace(minute=4))[1] != window


def test_only_connected_tenant_never_receives_another_tenants_events():
    class SocketProbe:
        def __init__(self):
            self.messages = []

        async def send_json(self, message):
            self.messages.append(message)

    async def run():
        manager = DispatchWebSocketManager()
        socket = SocketProbe()
        manager.active_connections["clinic-a"] = {socket}
        await manager._broadcast_local("clinic-b", {"event": "INCOMING_CALL_RING"})
        assert socket.messages == []
        await manager._broadcast_local("clinic-a", {"event": "INCOMING_CALL_RING"})
        assert len(socket.messages) == 1

    asyncio.run(run())


def test_slot_search_two_step_request_level_aggregation_and_deduplication():
    telemetry = VoiceTelemetry(call_session_id="call-123", provider="groq", model="llama-3.3-70b-versatile", workflow_stage="slot_selection")
    telemetry.stage_request_shape(
        workflow_stage="slot_selection",
        tool_names=["search_doctor_slots"],
        instruction_characters=3200,
        serialized_history_characters=650,
        serialized_tool_schema_characters=1850,
        tool_result_characters=0,
    )
    telemetry.record(
        SimpleNamespace(
            type="llm_metrics",
            speech_id="turn-slot-1",
            request_id="req-groq-step-1",
            ttft=0.25,
            duration=0.6,
            prompt_tokens=4200,
            completion_tokens=45,
            cancelled=False,
        )
    )
    telemetry.stage_request_shape(
        workflow_stage="slot_selection",
        tool_names=[],
        instruction_characters=3200,
        serialized_history_characters=980,
        serialized_tool_schema_characters=0,
        tool_result_characters=320,
    )
    telemetry.record(
        SimpleNamespace(
            type="llm_metrics",
            speech_id="turn-slot-1",
            request_id="req-groq-step-2",
            ttft=0.3,
            duration=0.7,
            prompt_tokens=4571,
            completion_tokens=85,
            cancelled=False,
        )
    )
    duplicate_metric = SimpleNamespace(
        type="llm_metrics",
        speech_id="turn-slot-1",
        request_id="req-groq-step-1",
        prompt_tokens=4200,
        completion_tokens=45,
    )
    telemetry.record(duplicate_metric)

    payload = telemetry.payload()
    requests = payload["llm_requests"]
    assert len(requests) == 2
    assert requests[0]["request_id"] == "req-groq-step-1"
    assert requests[0]["tool_names"] == ["search_doctor_slots"]
    assert requests[0]["serialized_tool_schema_characters"] == 1850
    assert requests[0]["prompt_tokens"] == 4200
    assert requests[0]["completion_tokens"] == 45
    assert requests[0]["total_tokens"] == 4245
    assert requests[0]["model"] == "llama-3.3-70b-versatile"
    assert requests[0]["provider"] == "groq"

    assert requests[1]["request_id"] == "req-groq-step-2"
    assert requests[1]["tool_names"] == []
    assert requests[1]["serialized_tool_schema_characters"] == 0
    assert requests[1]["prompt_tokens"] == 4571
    assert requests[1]["completion_tokens"] == 85
    assert requests[1]["total_tokens"] == 4656

    assert payload["prompt_tokens"] == 8771
    assert payload["completion_tokens"] == 130
    assert payload["total_tokens"] == 8901


def test_reasoning_tokens_reported_when_present_and_unknown_when_absent():
    telemetry = VoiceTelemetry()
    telemetry.record(
        SimpleNamespace(
            type="llm_metrics",
            speech_id="turn-1",
            request_id="req-gemini",
            prompt_tokens=500,
            completion_tokens=50,
        )
    )
    telemetry.record(
        SimpleNamespace(
            type="llm_metrics",
            speech_id="turn-2",
            request_id="req-deepseek",
            prompt_tokens=800,
            completion_tokens=120,
            reasoning_tokens=64,
            total_tokens=984,
        )
    )
    requests = telemetry.payload()["llm_requests"]
    assert requests[0]["reasoning_tokens"] == "unknown"
    assert requests[0]["total_tokens"] == 550

    assert requests[1]["reasoning_tokens"] == 64
    assert requests[1]["total_tokens"] == 984


def test_provider_error_diagnostics_preserved_in_telemetry():
    from app.services.voice.diagnostics import ErrorCategory, SanitizedProviderError

    telemetry = VoiceTelemetry()
    error = SanitizedProviderError(
        category=ErrorCategory.RATE_LIMITED,
        recoverable=False,
        wrapper_type="APIStatusError",
        underlying_type="RateLimitError",
        status_code=429,
        request_id="req_rate_limit_001",
        retry_after=60.0,
        sanitized_message="Rate limit reached for model llama-3.3-70b-versatile in organization org-123",
    )
    telemetry.record_error(error)
    payload = telemetry.payload()
    assert len(payload["provider_errors"]) == 1
    err = payload["provider_errors"][0]
    assert err["category"] == "rate_limited"
    assert err["status_code"] == 429
    assert err["request_id"] == "req_rate_limit_001"
    assert err["retry_after"] == 60.0
    assert "llama-3.3-70b-versatile" in err["sanitized_message"]
