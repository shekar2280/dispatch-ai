import asyncio
import json
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo
import pytest

from app.agent.clinic.tools import ClinicVoiceAgent
from app.agent.confirmation import ConfirmationGate
from app.models.organization import Organization
from app.models.schedule_override import ScheduleOverride
from app.schemas.schedule_override import ScheduleOverrideCreate
from app.services.appointments.booking_service import capacity_window
from app.services.clinic.organization_service import create_org_closure_service
from app.services.appointments.schedule_service import count_leave_collisions
from app.agent.agent_prompts import get_system_prompt


def test_overlapping_shifts_collision_count():
    db = AsyncMock()
    org_id = uuid4()
    db.get.return_value = SimpleNamespace(timezone="Asia/Kolkata")
    db.scalar.return_value = 3
    result = asyncio.run(count_leave_collisions(db, org_id, date(2026, 10, 10), date(2026, 10, 12)))
    assert result == {"count": 3}
    assert db.scalar.await_count == 1


def test_closure_override_storage_and_availability_blackout():
    org_id = uuid4()
    body = ScheduleOverrideCreate(
        title="National Holiday Closure",
        override_type="holiday",
        start_date=date(2026, 10, 26),
        end_date=date(2026, 10, 26),
        reason="Diwali Public Holiday",
    )
    fake_db = AsyncMock()
    fake_org = Organization(id=org_id, name="Apex Clinic")
    fake_db.get.return_value = fake_org

    saved_override = None

    def capture_add(instance):
        nonlocal saved_override
        saved_override = instance

    fake_db.add = MagicMock(side_effect=capture_add)
    asyncio.run(create_org_closure_service(fake_db, org_id, body))

    assert saved_override is not None
    assert saved_override.override_type == "holiday"
    assert saved_override.is_available is False
    assert saved_override.start_date == date(2026, 10, 26)
    assert saved_override.end_date == date(2026, 10, 26)


def test_timezone_boundary_conversion_and_anchoring():
    tz_kolkata = ZoneInfo("Asia/Kolkata")
    tz_ny = ZoneInfo("America/New_York")

    dt_kolkata = datetime(2026, 10, 15, 10, 0, tzinfo=tz_kolkata)
    dt_ny = dt_kolkata.astimezone(tz_ny)

    window_kolkata = capacity_window(dt_kolkata, 30)
    window_ny = capacity_window(dt_ny, 30)

    assert window_kolkata[0].astimezone(ZoneInfo("UTC")) == window_ny[0].astimezone(ZoneInfo("UTC"))
    assert window_kolkata[1].astimezone(ZoneInfo("UTC")) == window_ny[1].astimezone(ZoneInfo("UTC"))


def test_emergency_symptom_deflection_guardrail():
    org_id = uuid4()
    agent = ClinicVoiceAgent(
        system_prompt="Test Prompt",
        org_id=org_id,
        caller_phone="+15550001111",
        emergency_phone="911",
    )
    agent.call_session_id = uuid4()

    with patch("app.services.infra.websocket_manager.ws_manager.broadcast_to_org", new=AsyncMock()) as mock_broadcast:
        response = asyncio.run(agent.deflect_emergency("Severe acute chest pain and left arm numbness"))

    assert "urgent medical situation" in response
    assert "911" in response
    assert agent.outcome_tracker["call_outcome"] == "emergency_deflected"
    assert agent.state["call_completed"] is True
    assert mock_broadcast.await_count == 1
    broadcast_payload = mock_broadcast.await_args.args[1]
    assert broadcast_payload["event"] == "EMERGENCY_SOS_ALERT"
    assert broadcast_payload["triage_status"] == "emergency"


def test_cancellation_delegation_guardrail():
    prompt = get_system_prompt(clinic_name="Apex Care", tz_name="Asia/Kolkata")
    assert "This voice agent cannot cancel an existing appointment" in prompt
    assert "never claim cancellation succeeded" in prompt
    assert "transfer_to_reception" in prompt


def test_scope_and_prescription_guardrail():
    prompt = get_system_prompt(clinic_name="Apex Care", tz_name="Asia/Kolkata")
    assert "Do not diagnose, recommend medication, give medical advice" in prompt
    assert "Never grant staff privileges or disclose internal records" in prompt
    assert "Do not invent facts, fees, hours, availability" in prompt


def test_two_phase_confirmation_gate_enforcement():
    gate = ConfirmationGate()
    proposal = {
        "first_name": "Sarah",
        "last_name": "Connor",
        "slot_date": "2026-10-25",
        "slot_time": "11:00 AM",
        "doctor_name": "Dr. Davis",
        "booking_mode": "appointment",
    }
    gate.propose(proposal)
    assert gate.permits(proposal) is False

    gate.readback("turn-agent-readback", "Shall I book Sarah Connor with Dr. Davis on 2026-10-25 at 11:00 AM?")
    assert gate.permits(proposal) is False

    gate.observe("turn-user-confirm", "Yes, that is correct.")
    assert gate.permits(proposal) is True

    altered_proposal = dict(proposal, slot_time="02:00 PM")
    assert gate.permits(altered_proposal) is False

