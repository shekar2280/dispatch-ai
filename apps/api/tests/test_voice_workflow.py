from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from livekit.agents import llm

from app.agent.clinic.tools import ClinicVoiceAgent
from app.services.voice.workflow.router import (
    match_emergency,
    match_farewell,
    match_offered_slot,
    match_transfer,
    match_yes_no,
)
from app.services.voice.workflow.state import VoiceWorkflowState, WorkflowStage


def test_router_affirmative_and_negative_matching():
    assert match_yes_no("yes") is True
    assert match_yes_no("Yes, book it") is True
    assert match_yes_no("sure that works") is True
    assert match_yes_no("sounds good") is True
    assert match_yes_no("okay") is True

    assert match_yes_no("no") is False
    assert match_yes_no("No, cancel that") is False
    assert match_yes_no("neither") is False
    assert match_yes_no("wrong") is False
    assert match_yes_no("never mind") is False

    assert match_yes_no("Dr. Sharma tomorrow") is None


def test_router_offered_slot_ordinal_and_time_matching():
    offers = [
        {"label": "2:00 PM", "key": "key-1"},
        {"label": "2:30 PM", "key": "key-2"},
    ]
    assert match_offered_slot("the first one", offers) == offers[0]
    assert match_offered_slot("first", offers) == offers[0]
    assert match_offered_slot("the second one", offers) == offers[1]
    assert match_offered_slot("second", offers) == offers[1]

    assert match_offered_slot("two thirty", offers) == offers[1]
    assert match_offered_slot("2:30", offers) == offers[1]
    assert match_offered_slot("2 pm", offers) == offers[0]
    assert match_offered_slot("5:00 PM", offers) is None


def test_router_emergency_transfer_and_farewell():
    assert match_emergency("I'm having severe chest pain") is True
    assert match_emergency("I need an appointment") is False

    assert match_transfer("Can I speak to reception?") is True
    assert match_transfer("I want to talk to a real person") is True
    assert match_transfer("What are your hours?") is False

    assert match_farewell("Thank you, that's all, goodbye") is True
    assert match_farewell("bye") is True
    assert match_farewell("I want tomorrow") is False


def test_workflow_state_transitions():
    state = VoiceWorkflowState()
    assert state.stage == WorkflowStage.INTAKE
    assert state.candidate_slots == []

    state.candidate_slots = [{"label": "10 AM"}]
    state.selected_slot = state.candidate_slots[0]
    state.confirmation_pending = True
    assert state.selected_slot["label"] == "10 AM"

    state.clear_selection()
    assert state.selected_slot is None
    assert state.confirmation_pending is False


@pytest.mark.asyncio
async def test_llm_node_deterministic_slot_selection_uses_zero_tokens():
    agent = ClinicVoiceAgent("Clinic Receptionist")
    agent.workflow_stage = "slot_selection"
    agent.state["last_slot_search"] = {
        "status": "available",
        "doctor": "Dr. Smith",
        "date": "2026-10-24",
        "offers": [{"label": "2:00 PM"}, {"label": "2:30 PM"}],
    }
    agent.state["caller_name"] = "Alice Walker"

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
    assert "Alice Walker" in chunks[0]
    assert "2:30 PM" in chunks[0]
    mock_reserve.assert_not_awaited()


@pytest.mark.asyncio
async def test_llm_node_deterministic_emergency_deflection_uses_zero_tokens():
    agent = ClinicVoiceAgent("Clinic Receptionist")
    chat_ctx = llm.ChatContext()
    chat_ctx.items.append(SimpleNamespace(role="user", text_content="I have severe chest pain"))

    with patch("app.services.voice.provider_budget.reserve_llm", AsyncMock()) as mock_reserve:
        chunks = [chunk async for chunk in agent.llm_node(chat_ctx, [], SimpleNamespace(tool_choice="auto"))]

    assert len(chunks) == 1
    assert "urgent medical situation" in chunks[0]
    assert agent.outcome_tracker["call_outcome"] == "emergency_deflected"
    mock_reserve.assert_not_awaited()


@pytest.mark.asyncio
async def test_llm_node_deterministic_farewell_uses_zero_tokens():
    agent = ClinicVoiceAgent("Clinic Receptionist")
    chat_ctx = llm.ChatContext()
    chat_ctx.items.append(SimpleNamespace(role="user", text_content="That's all, goodbye"))

    with patch("app.services.voice.provider_budget.reserve_llm", AsyncMock()) as mock_reserve:
        chunks = [chunk async for chunk in agent.llm_node(chat_ctx, [], SimpleNamespace(tool_choice="auto"))]

    assert len(chunks) == 1
    assert "Goodbye" in chunks[0]
    assert agent.workflow.call_completed is True
    mock_reserve.assert_not_awaited()


def test_transition_matrix_valid_and_invalid_transitions():
    from app.services.voice.workflow.state import VALID_TRANSITIONS, InvalidWorkflowTransitionError
    state = VoiceWorkflowState()
    assert state.stage == WorkflowStage.INTAKE
    initial_version = state.state_version

    assert state.can_transition_to(WorkflowStage.AVAILABILITY) is True
    assert state.can_transition_to(WorkflowStage.SLOT_SELECTION) is True
    assert state.can_transition_to(WorkflowStage.IDENTITY_LOOKUP) is True
    assert state.can_transition_to(WorkflowStage.CANCEL_CONFIRMATION) is False

    assert state.transition_to(WorkflowStage.CANCEL_CONFIRMATION) is False
    assert state.stage == WorkflowStage.INTAKE
    assert state.state_version == initial_version

    with pytest.raises(InvalidWorkflowTransitionError):
        state.transition_to(WorkflowStage.CANCEL_CONFIRMATION, strict=True)

    assert state.transition_to(WorkflowStage.SLOT_SELECTION) is True
    assert state.stage == WorkflowStage.SLOT_SELECTION
    assert state.state_version == initial_version + 1

    for stage, allowed_targets in VALID_TRANSITIONS.items():
        st = VoiceWorkflowState(stage=stage)
        for target in WorkflowStage:
            if target in allowed_targets:
                assert st.can_transition_to(target) is True
            else:
                assert st.can_transition_to(target) is False
                assert st.transition_to(target) is False


def test_single_stage_authority_and_property_synchronization():
    agent = ClinicVoiceAgent("Clinic Receptionist")
    assert agent.workflow_stage == "intake"
    assert agent.workflow.stage == WorkflowStage.INTAKE
    assert agent.state["stage"] == "intake"

    agent.workflow_stage = "slot_selection"
    assert agent.workflow.stage == WorkflowStage.SLOT_SELECTION
    assert agent.workflow_stage == "slot_selection"
    assert agent.state["stage"] == "slot_selection"

    agent.state["stage"] = "booking_details"
    assert agent.workflow.stage == WorkflowStage.BOOKING_DETAILS
    assert agent.workflow_stage == "booking_details"


def test_confirmation_gate_readback_interruption_blocks_confirmation():
    from app.agent.confirmation import ConfirmationGate
    gate = ConfirmationGate()
    gate.observe("turn-1", "I would like tomorrow at 2 PM")
    proposal = {
        "doctor_name": "Dr. Sharma",
        "first_name": "Rahul",
        "last_name": "Verma",
        "slot_date": "2026-10-24",
        "slot_time": "2:00 PM",
    }
    gate.propose(proposal)
    assert gate.proposal == proposal

    gate.readback("turn-2", spoken_text="Rahul Verma tomorrow at 2:00 PM with Dr. Sharma", interrupted=True)
    assert gate.readback_turn is None
    gate.observe("turn-3", "yes please book it")
    assert gate.permits(proposal) is False

    gate.readback("turn-4", spoken_text="Rahul Verma tomorrow at 2:00 PM with Dr. Sharma", interrupted=False)
    assert gate.readback_turn == "turn-4"
    gate.observe("turn-5", "yes that is correct")
    assert gate.permits(proposal) is True


def test_workflow_state_serialization_and_redaction():
    state = VoiceWorkflowState(
        stage=WorkflowStage.SLOT_SELECTION,
        intent="book_appointment",
        caller_name="Secret Patient",
        verified_name="Secret Patient",
        patient_id="patient-secret-123",
        caller_phone="+919876543210",
        preferred_doctor="Dr. Sharma",
        target_date="2026-10-25",
        target_time="10:00 AM",
        candidate_slots=[{"label": "10:00 AM"}, {"label": "10:30 AM"}],
    )
    safe = state.to_safe_dict()
    assert safe["stage"] == "slot_selection"
    assert safe["intent"] == "book_appointment"
    assert safe["preferred_doctor"] == "Dr. Sharma"
    assert safe["candidate_count"] == 2
    assert "caller_name" not in safe
    assert "verified_name" not in safe
    assert "patient_id" not in safe
    assert "caller_phone" not in safe

    full = state.to_dict()
    assert full["caller_name"] == "Secret Patient"
    assert full["caller_phone"] == "+919876543210"
    assert full["candidate_slots"] == state.candidate_slots
