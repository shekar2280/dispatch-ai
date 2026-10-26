from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4
import pytest
from livekit.agents import llm
from app.agent.clinic.tools import ClinicVoiceAgent


@pytest.mark.asyncio
async def test_offered_slot_selection_uses_zero_llm_calls():
    agent = ClinicVoiceAgent("Apex Clinic")
    agent.workflow_stage = "slot_selection"
    agent.state["last_slot_search"] = {
        "status": "available",
        "doctor": "Dr. Davis",
        "date": "2026-10-25",
        "offers": [{"label": "2:00 PM"}, {"label": "2:30 PM"}],
    }
    agent.state["caller_name"] = "Alice Smith"

    chat_ctx = llm.ChatContext()
    chat_ctx.items.append(SimpleNamespace(role="user", text_content="the second one"))

    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=None)
    mock_db.commit = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_db
    mock_ctx.__aexit__.return_value = None

    with (
        patch("app.agent.clinic.tools.AsyncSessionLocal", return_value=mock_ctx),
        patch("app.services.voice.provider_budget.reserve_llm", AsyncMock()) as mock_reserve,
    ):
        chunks = [chunk async for chunk in agent.llm_node(chat_ctx, [], SimpleNamespace(tool_choice="auto"))]

    assert len(chunks) == 1
    assert "Alice Smith" in chunks[0]
    assert "2:30 PM" in chunks[0]
    mock_reserve.assert_not_awaited()


@pytest.mark.asyncio
async def test_booking_confirmation_uses_zero_llm_calls():
    agent = ClinicVoiceAgent("Apex Clinic")
    agent.workflow_stage = "booking_confirmation"
    proposal = {
        "first_name": "Alice",
        "last_name": "Smith",
        "slot_date": "2026-10-25",
        "slot_time": "2:30 PM",
        "doctor_name": "Dr. Davis",
        "booking_mode": "appointment",
    }
    agent.confirmation.propose(proposal)
    agent.confirmation.readback("event-1", "Shall I book Alice Smith on 2026-10-25 at 2:30 PM?")
    agent.confirmation.observe("event-2", "yes, please book it")

    chat_ctx = llm.ChatContext()
    chat_ctx.items.append(SimpleNamespace(role="user", text_content="yes, please book it"))

    with (
        patch.object(agent, "confirm_appointment_booking", AsyncMock(return_value="Confirmed!")) as mock_confirm,
        patch("app.services.voice.provider_budget.reserve_llm", AsyncMock()) as mock_reserve,
    ):
        chunks = [chunk async for chunk in agent.llm_node(chat_ctx, [], SimpleNamespace(tool_choice="auto"))]

    assert len(chunks) == 1
    assert chunks[0] == "Confirmed!"
    mock_confirm.assert_awaited_once()
    mock_reserve.assert_not_awaited()


@pytest.mark.asyncio
async def test_direct_faq_hours_uses_zero_llm_calls():
    agent = ClinicVoiceAgent("Apex Clinic")
    agent.workflow_stage = "intake"

    chat_ctx = llm.ChatContext()
    chat_ctx.items.append(SimpleNamespace(role="user", text_content="What are your hours?"))

    with (
        patch.object(agent, "lookup_clinic_faq", AsyncMock(return_value="We are open Monday to Friday 9 AM to 5 PM.")) as mock_faq,
        patch("app.services.voice.provider_budget.reserve_llm", AsyncMock()) as mock_reserve,
    ):
        chunks = [chunk async for chunk in agent.llm_node(chat_ctx, [], SimpleNamespace(tool_choice="auto"))]

    assert len(chunks) == 1
    assert "9 AM to 5 PM" in chunks[0]
    mock_faq.assert_awaited_once_with(query="hours")
    mock_reserve.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancellation_workflow_uses_zero_llm_calls():
    agent = ClinicVoiceAgent("Apex Clinic")
    agent.workflow_stage = "intake"

    chat_ctx = llm.ChatContext()
    chat_ctx.items.append(SimpleNamespace(role="user", text_content="I want to cancel my appointment"))

    with patch("app.services.voice.provider_budget.reserve_llm", AsyncMock()) as mock_reserve:
        chunks = [chunk async for chunk in agent.llm_node(chat_ctx, [], SimpleNamespace(tool_choice="auto"))]

    assert len(chunks) == 1
    assert "To cancel your appointment" in chunks[0]
    assert agent.workflow_stage == "identity_lookup"
    mock_reserve.assert_not_awaited()

    chat_ctx2 = llm.ChatContext()
    chat_ctx2.items.append(SimpleNamespace(role="user", text_content="Alice Smith"))

    verified_payload = (
        '{"verified": true, "active_appointments": [{"appointment_id": "appt-123", '
        '"appointment_date": "2026-10-25", "appointment_time": "10:00 AM", "doctor_name": "Dr. Davis"}]}'
    )
    with (
        patch.object(agent, "verify_patient_identity", AsyncMock(return_value=verified_payload)),
        patch("app.services.voice.provider_budget.reserve_llm", AsyncMock()) as mock_reserve,
    ):
        chunks2 = [chunk async for chunk in agent.llm_node(chat_ctx2, [], SimpleNamespace(tool_choice="auto"))]

    assert len(chunks2) == 1
    assert "Dr. Davis" in chunks2[0]
    assert agent.workflow_stage == "cancel_confirmation"
    mock_reserve.assert_not_awaited()

    chat_ctx3 = llm.ChatContext()
    chat_ctx3.items.append(SimpleNamespace(role="user", text_content="Yes, cancel it"))

    with (
        patch.object(agent, "cancel_appointment", AsyncMock(return_value='{"status": "cancelled"}')),
        patch("app.services.voice.provider_budget.reserve_llm", AsyncMock()) as mock_reserve,
    ):
        chunks3 = [chunk async for chunk in agent.llm_node(chat_ctx3, [], SimpleNamespace(tool_choice="auto"))]

    assert len(chunks3) == 1
    assert "cancelled" in chunks3[0].lower()
    mock_reserve.assert_not_awaited()
