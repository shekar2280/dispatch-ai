"""Regression tests for encounters."""

import zoneinfo
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.appointments import _visible_appointment
from app.api.v1.clinic_dashboard import _redact_clinical
from app.models.appointment import Appointment
from app.models.clinic_membership import ClinicMembership
from app.models.organization import Organization
from app.models.patient import Patient
from app.models.user import User
from app.schemas.appointment import AppointmentResponse, AppointmentStatusUpdate
from app.services.appointments.booking_service import get_effective_consultation_duration
from app.services.appointments.encounter_service import (
    ClinicCheckInRequest,
    call_appointment_patient,
    complete_consultation,
    get_appointment_visit_events,
    mark_appointment_arrived,
    start_consultation,
    update_appointment_status,
)


@pytest.mark.anyio
async def test_appointment_lifecycle_timestamps():
    org_id = uuid4()
    appt_id = uuid4()

    mock_org = MagicMock(spec=Organization)
    mock_org.timezone = "Asia/Kolkata"
    mock_org.lead_doctor_name = "Dr. Test"
    mock_org.clinic_specialty = "General"

    tz = timezone(timedelta(hours=5, minutes=30))
    today_date = datetime.now(tz).date()
    mock_appt = MagicMock(spec=Appointment)
    mock_appt.id = appt_id
    mock_appt.org_id = org_id
    mock_appt.patient_id = uuid4()
    mock_appt.doctor_id = uuid4()
    mock_appt.appointment_date = today_date
    mock_appt.appointment_time = "10:00 AM"
    mock_appt.start_time = datetime.now(timezone.utc)
    mock_appt.end_time = mock_appt.start_time + timedelta(minutes=15)
    mock_appt.status = "scheduled"
    mock_appt.token_number = 1
    mock_appt.token_prefix = None
    mock_appt.display_token = None
    mock_appt.shift_type = None
    mock_appt.payment_status = "pending"
    mock_appt.payment_method = None
    mock_appt.fee = 500
    mock_appt.chief_complaint = "Fever"
    mock_appt.doctor_notes = None
    mock_appt.source = "ai_voice"
    mock_appt.created_at = datetime.now(timezone.utc)
    mock_appt.checked_in_at = None
    mock_appt.called_at = None
    mock_appt.call_count = 0
    mock_appt.consultation_started_at = None
    mock_appt.consultation_ended_at = None
    mock_appt.actual_duration_seconds = None

    mock_patient = MagicMock(spec=Patient)
    mock_patient.org_id = org_id
    mock_patient.first_name = "Test"
    mock_patient.last_name = "Patient"
    mock_patient.phone_number = "+919876543210"
    mock_patient.dob = None
    mock_patient.date_of_birth = None
    mock_patient.reported_age = 30
    mock_patient.gender = None
    mock_patient.blood_group = None
    mock_patient.medical_history = {}

    def _get_side_effect(model_class, pk):
        if model_class is Organization:
            return mock_org
        if model_class is Patient:
            return mock_patient
        return None

    async def _scalar_side_effect(stmt, *args, **kwargs):
        stmt_str = str(stmt).replace("\n", " ")
        if "appointments.id !=" in stmt_str:
            return None
        if "func.max" in stmt_str.lower() or "MAX" in stmt_str:
            return None
        return mock_appt

    mock_execute_result = MagicMock()
    mock_execute_result.scalars.return_value.all.return_value = [mock_appt]

    db = AsyncMock()
    db.scalar.side_effect = _scalar_side_effect
    db.get.side_effect = _get_side_effect
    db.execute.return_value = mock_execute_result
    db.add = MagicMock()

    with patch("app.services.appointments.encounter_service.build_single_appointment_response") as mock_build:
        mock_build.return_value = MagicMock(status="arrived")
        await mark_appointment_arrived(
            appointment_id=appt_id,
            req=ClinicCheckInRequest(reported_age=30),
            org_id=org_id,
            db=db,
        )
        assert mock_appt.status == "arrived"
        assert mock_appt.checked_in_at is not None
        assert isinstance(mock_appt.checked_in_at, datetime)

    with patch("app.services.appointments.encounter_service.build_single_appointment_response") as mock_build:
        mock_build.return_value = MagicMock(status="in_progress")
        await call_appointment_patient(
            appointment_id=appt_id,
            org_id=org_id,
            db=db,
        )
        assert mock_appt.status == "arrived"
        assert mock_appt.called_at is not None
        assert mock_appt.consultation_started_at is None

        await start_consultation(appointment_id=appt_id, org_id=org_id, db=db)
        assert mock_appt.status == "in_progress"
        assert mock_appt.consultation_started_at is not None
        assert isinstance(mock_appt.consultation_started_at, datetime)

    with (
        patch("app.services.appointments.encounter_service.build_single_appointment_response") as mock_build,
        patch(
            "app.services.appointments.encounter_service.record_consultation_completion_metrics", new_callable=AsyncMock
        ),
    ):
        mock_build.return_value = MagicMock(status="completed")
        await complete_consultation(
            appointment_id=appt_id,
            org_id=org_id,
            db=db,
        )
        assert mock_appt.status == "completed"
        assert mock_appt.consultation_ended_at is not None
        assert mock_appt.actual_duration_seconds is not None
        assert mock_appt.actual_duration_seconds >= 0


@pytest.mark.anyio
async def test_appointment_recall_guard():
    org_id = uuid4()
    appt_id = uuid4()

    mock_appt = MagicMock(spec=Appointment)
    mock_appt.id = appt_id
    mock_appt.org_id = org_id
    mock_appt.status = "arrived"
    mock_appt.consultation_started_at = None
    mock_appt.call_count = 0

    async def _mock_recall_scalar(statement, *args, **kwargs):
        stmt = str(statement).replace("\n", " ")
        if "SELECT appointments.id FROM" in stmt or "appointments.id !=" in stmt:
            return None
        return mock_appt

    mock_recall_exec = MagicMock()
    mock_recall_exec.scalars.return_value.all.return_value = [mock_appt]

    db = AsyncMock()
    db.scalar.side_effect = _mock_recall_scalar
    db.execute.return_value = mock_recall_exec
    db.get.return_value = MagicMock(timezone="Asia/Kolkata")
    db.add = MagicMock()

    with patch("app.services.appointments.encounter_service.build_single_appointment_response") as mock_build:
        mock_build.return_value = MagicMock(status="in_progress")
        await call_appointment_patient(
            appointment_id=appt_id,
            org_id=org_id,
            db=db,
        )
        assert mock_appt.status == "arrived"
        first_called_at = mock_appt.called_at
        assert first_called_at is not None
        assert mock_appt.consultation_started_at is None
        assert mock_appt.call_count == 1

        await call_appointment_patient(
            appointment_id=appt_id,
            org_id=org_id,
            db=db,
        )
        assert mock_appt.called_at >= first_called_at
        assert mock_appt.consultation_started_at is None
        assert mock_appt.call_count == 2


@pytest.mark.anyio
async def test_visit_event_recording_and_retrieval():
    from app.models.visit_event import VisitEvent
    from app.services.appointments.encounter_service import write_visit_event

    org_id = uuid4()
    appt_id = uuid4()

    db = AsyncMock()
    created_event = VisitEvent(
        id=uuid4(),
        visit_id=appt_id,
        org_id=org_id,
        event_type="CALLED_IN",
        notes="Called patient",
        occurred_at=datetime.now(timezone.utc),
        actor_type="staff",
        event_metadata={},
    )
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.get.return_value = MagicMock(org_id=org_id)

    event = await write_visit_event(
        db=db,
        visit_id=appt_id,
        org_id=org_id,
        event_type="CALLED_IN",
        notes="Called patient",
    )
    assert event.event_type == "CALLED_IN"
    assert event.visit_id == appt_id
    assert db.add.called

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [created_event]
    db.execute.return_value = mock_result

    events = await get_appointment_visit_events(
        appointment_id=appt_id,
        org_id=org_id,
        db=db,
    )
    assert len(events) == 1
    assert events[0].event_type == "CALLED_IN"


@pytest.mark.anyio
async def test_ordered_active_queue_selector():
    from app.services.appointments.queue_service import get_ordered_active_queue

    org_id = uuid4()
    mock_org = MagicMock(spec=Organization)
    mock_org.timezone = "Asia/Kolkata"
    mock_org.appointment_priority_window_minutes = 15
    mock_org.booking_settings = {}
    mock_org.weekly_schedule = {}

    tz = timezone(timedelta(hours=5, minutes=30))
    now_clinic = datetime.now(tz)
    now_str = now_clinic.strftime("%I:%M %p")

    appt_priority = MagicMock(spec=Appointment)
    appt_priority.id = uuid4()
    appt_priority.org_id = org_id
    appt_priority.status = "arrived"
    appt_priority.queue_state = "called"
    appt_priority.source = "ai_voice"
    appt_priority.appointment_time = now_str
    appt_priority.start_time = now_clinic
    appt_priority.checked_in_at = datetime.now(timezone.utc)
    appt_priority.token_number = 5
    appt_priority.booking_metadata = {}
    appt_priority.created_at = datetime.now(timezone.utc)

    appt_walkin = MagicMock(spec=Appointment)
    appt_walkin.id = uuid4()
    appt_walkin.org_id = org_id
    appt_walkin.status = "arrived"
    appt_walkin.queue_state = "waiting"
    appt_walkin.source = "walk_in"
    appt_walkin.appointment_time = None
    appt_walkin.start_time = now_clinic
    appt_walkin.checked_in_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    appt_walkin.token_number = 1
    appt_walkin.booking_metadata = {}
    appt_walkin.created_at = datetime.now(timezone.utc) - timedelta(minutes=30)

    appt_skipped = MagicMock(spec=Appointment)
    appt_skipped.id = uuid4()
    appt_skipped.org_id = org_id
    appt_skipped.status = "skipped"
    appt_skipped.queue_state = "stepped_out"
    appt_skipped.source = "walk_in"
    appt_skipped.appointment_time = None
    appt_skipped.start_time = now_clinic
    appt_skipped.checked_in_at = datetime.now(timezone.utc) - timedelta(minutes=45)
    appt_skipped.token_number = 2
    appt_skipped.booking_metadata = {}
    appt_skipped.created_at = datetime.now(timezone.utc) - timedelta(minutes=45)

    db = AsyncMock()
    db.get.return_value = mock_org

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [
        appt_skipped,
        appt_walkin,
        appt_priority,
    ]
    db.execute.return_value = mock_result

    ordered = await get_ordered_active_queue(db=db, org_id=org_id)
    assert len(ordered) == 3
    assert ordered[0].id == appt_priority.id
    assert ordered[1].id == appt_walkin.id
    assert ordered[2].id == appt_skipped.id


def _build_test_appointment(org_id, status="scheduled"):
    appt = MagicMock(spec=Appointment)
    appt.id = uuid4()
    appt.org_id = org_id
    appt.patient_id = uuid4()
    appt.doctor_id = uuid4()
    appt.appointment_date = datetime.now(timezone.utc).date()
    appt.appointment_time = "10:00 AM"
    appt.start_time = datetime.now(timezone.utc)
    appt.end_time = appt.start_time + timedelta(minutes=15)
    appt.status = status
    appt.queue_state = "waiting" if status == "arrived" else "not_checked_in"
    appt.encounter_state = "not_started"
    appt.token_number = 1
    appt.token_prefix = "T"
    appt.display_token = "T-1"
    appt.payment_status = "pending"
    appt.payment_method = None
    appt.fee = 500
    appt.chief_complaint = "Persistent dry cough"
    appt.doctor_notes = "Suspected bronchitis, advised inhaler."
    appt.source = "walk_in"
    appt.created_at = datetime.now(timezone.utc)
    appt.checked_in_at = datetime.now(timezone.utc) if status == "arrived" else None
    appt.called_at = None
    appt.call_count = 0
    appt.consultation_started_at = None
    appt.consultation_ended_at = None
    appt.actual_duration_seconds = None
    return appt


@pytest.mark.anyio
async def test_full_encounter_lifecycle_telemetry():
    org_id = uuid4()
    appt = _build_test_appointment(org_id, status="scheduled")
    org = MagicMock(spec=Organization)
    org.timezone = "Asia/Kolkata"

    patient = Patient(
        id=appt.patient_id,
        org_id=org_id,
        first_name="Anita",
        last_name="Rao",
        phone_number="+919876543210",
        dob=date(1990, 1, 1),
        medical_history={},
    )

    async def _mock_get(model, obj_id):
        if model is Organization:
            return org
        if model is Patient:
            return patient
        return None

    async def _mock_scalar(statement, *args, **kwargs):
        stmt = str(statement).replace("\n", " ")
        if "SELECT appointments.id FROM" in stmt or "appointments.id !=" in stmt:
            return None
        return appt

    mock_exec_res = MagicMock()
    mock_exec_res.scalars.return_value.all.return_value = [appt]

    db = AsyncMock()
    db.scalar.side_effect = _mock_scalar
    db.get.side_effect = _mock_get
    db.execute.return_value = mock_exec_res
    db.add = MagicMock()

    with patch("app.services.appointments.encounter_service.build_single_appointment_response") as mock_build:
        mock_build.return_value = MagicMock(status="arrived")
        await mark_appointment_arrived(appointment_id=appt.id, req=None, org_id=org_id, db=db)
        assert appt.status == "arrived"
        assert appt.checked_in_at is not None
        assert appt.queue_state == "waiting"

    with patch("app.services.appointments.encounter_service.build_single_appointment_response") as mock_build:
        mock_build.return_value = MagicMock(status="arrived")
        await call_appointment_patient(appointment_id=appt.id, org_id=org_id, db=db)
        assert appt.queue_state == "called"
        assert appt.called_at is not None
        assert appt.call_count == 1

    with patch("app.services.appointments.encounter_service.build_single_appointment_response") as mock_build:
        mock_build.return_value = MagicMock(status="in_progress")
        await start_consultation(appointment_id=appt.id, org_id=org_id, db=db)
        assert appt.status == "in_progress"
        assert appt.encounter_state == "in_progress"
        assert appt.queue_state == "served"
        assert appt.consultation_started_at is not None

    with (
        patch("app.services.appointments.encounter_service.build_single_appointment_response") as mock_build,
        patch(
            "app.services.appointments.encounter_service.record_consultation_completion_metrics", new_callable=AsyncMock
        ),
    ):
        mock_build.return_value = MagicMock(status="completed")
        await complete_consultation(appointment_id=appt.id, org_id=org_id, db=db)
        assert appt.status == "completed"
        assert appt.encounter_state == "completed"
        assert appt.consultation_ended_at is not None
        assert appt.actual_duration_seconds is not None
        assert appt.actual_duration_seconds >= 0


def test_receptionist_clinical_isolation_contract():
    receptionist = SimpleNamespace(role="receptionist")
    doctor = SimpleNamespace(role="doctor")

    item = AppointmentResponse(
        id=uuid4(),
        org_id=uuid4(),
        patient_id=uuid4(),
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc) + timedelta(minutes=15),
        status="completed",
        chief_complaint="Chest pain and breathing difficulty",
        doctor_notes="ECG normal, prescribed antianginal medication",
        booked_by_type="walk_in",
        booked_by_name="Desk",
        verification_status="verified",
        created_at=datetime.now(timezone.utc),
        patient_name="Amit Patel",
        patient_phone="+919876500000",
        doctor_name="Dr. Roy",
        specialization="Cardiology",
    )

    receptionist_view = _visible_appointment(item, receptionist)
    assert receptionist_view.doctor_notes is None
    assert receptionist_view.chief_complaint == "Chest pain and breathing difficulty"

    doctor_view = _visible_appointment(item, doctor)
    assert doctor_view.doctor_notes == "ECG normal, prescribed antianginal medication"
    assert doctor_view.chief_complaint == "Chest pain and breathing difficulty"


def test_dashboard_clinical_redaction_filters_confidential_records():
    payload = {
        "doctor_notes": "Sensitive psychiatric evaluation notes",
        "recent_diagnosis": "Generalized anxiety disorder",
        "chief_complaint": "Insomnia and stress",
        "patient_name": "Ramesh Kumar",
        "medical_history": {"chronic_conditions": ["Hypertension"]},
    }

    redacted = _redact_clinical(payload)
    assert "doctor_notes" not in redacted
    assert "recent_diagnosis" not in redacted
    assert "medical_history" not in redacted
    assert redacted["chief_complaint"] == "Insomnia and stress"
    assert redacted["patient_name"] == "Ramesh Kumar"


@pytest.mark.anyio
async def test_reopen_consultation_within_five_minutes_succeeds():
    org_id = uuid4()
    appt = _build_test_appointment(org_id, status="completed")
    appt.consultation_started_at = datetime.now(timezone.utc) - timedelta(minutes=12)
    appt.consultation_ended_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    appt.actual_duration_seconds = 600

    membership = MagicMock(spec=ClinicMembership)
    membership.total_consultations = 5
    membership.total_minutes_worked = 50

    db = AsyncMock()
    db.scalar.side_effect = [appt, None, membership]
    db.add = MagicMock()

    with patch("app.services.appointments.encounter_service.build_single_appointment_response") as mock_build:
        mock_build.return_value = MagicMock(status="in_progress")
        update = AppointmentStatusUpdate(status="in_progress")
        await update_appointment_status(db, appt.id, update, org_id)

        assert appt.status == "in_progress"
        assert appt.encounter_state == "in_progress"
        assert appt.consultation_ended_at is None
        assert appt.actual_duration_seconds is None


@pytest.mark.anyio
async def test_reopen_consultation_after_five_minutes_raises_409():
    org_id = uuid4()
    appt = _build_test_appointment(org_id, status="completed")
    appt.consultation_started_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    appt.consultation_ended_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    appt.actual_duration_seconds = 600

    db = AsyncMock()
    db.scalar.return_value = appt

    update = AppointmentStatusUpdate(status="in_progress")
    with pytest.raises(HTTPException) as exc:
        await update_appointment_status(db, appt.id, update, org_id)

    assert exc.value.status_code == 409
    assert "five minutes" in exc.value.detail


@pytest.mark.anyio
async def test_empirical_consultation_duration_requires_minimum_three_records():
    org_id = uuid4()
    org = MagicMock(spec=Organization)
    org.default_slot_duration_minutes = 15
    target_date = date(2026, 10, 6)

    db_two = AsyncMock()
    res_two = MagicMock()
    res_two.all.return_value = [(600,), (720,)]
    db_two.execute.return_value = res_two

    duration_two, is_emp_two = await get_effective_consultation_duration(db_two, org, org_id, target_date)
    assert duration_two == 15
    assert not is_emp_two

    db_three = AsyncMock()
    res_three = MagicMock()
    res_three.all.return_value = [(600,), (720,), (840,)]
    db_three.execute.return_value = res_three

    duration_three, is_emp_three = await get_effective_consultation_duration(db_three, org, org_id, target_date)
    assert duration_three == 12
    assert is_emp_three


def test_zombie_consultation_flagging_logic():
    now_utc = datetime.now(timezone.utc)

    active_recent = _build_test_appointment(uuid4(), status="in_progress")
    active_recent.consultation_started_at = now_utc - timedelta(minutes=20)

    active_zombie = _build_test_appointment(uuid4(), status="in_progress")
    active_zombie.consultation_started_at = now_utc - timedelta(minutes=75)

    def is_zombie_consultation(appt: Appointment, threshold_minutes: int = 60) -> bool:
        if appt.status != "in_progress" or not appt.consultation_started_at:
            return False
        elapsed = (now_utc - appt.consultation_started_at).total_seconds() / 60
        return elapsed > threshold_minutes

    assert not is_zombie_consultation(active_recent)
    assert is_zombie_consultation(active_zombie)


@pytest.mark.anyio
async def test_cannot_complete_unstarted_consultation_raises_409():
    org_id = uuid4()
    appt = _build_test_appointment(org_id, status="arrived")
    appt.consultation_started_at = None

    db = AsyncMock()
    db.scalar.return_value = appt

    with pytest.raises(HTTPException) as exc:
        await complete_consultation(appointment_id=appt.id, org_id=org_id, db=db)

    assert exc.value.status_code == 409
    assert "Start consultation before completing it" in exc.value.detail


@pytest.mark.anyio
async def test_cannot_call_unarrived_patient_raises_409():
    org_id = uuid4()
    appt = _build_test_appointment(org_id, status="scheduled")

    db = AsyncMock()
    db.scalar.return_value = appt

    with pytest.raises(HTTPException) as exc:
        await call_appointment_patient(appointment_id=appt.id, org_id=org_id, db=db)

    assert exc.value.status_code == 409
    assert "Check in the patient before calling" in exc.value.detail
