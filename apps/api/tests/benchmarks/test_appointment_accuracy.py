import asyncio
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo
import pytest
from fastapi import HTTPException

from app.models.appointment import Appointment
from app.models.organization import Organization
from app.models.patient import Patient
from app.models.user import User
from app.schemas.appointment import ClinicScheduledBookingRequest, ClinicWalkinBookingRequest
from app.services.appointments.booking_service import (
    book_clinic_scheduled_appointment,
    book_clinic_walkin_appointment,
    capacity_window,
)


def _build_org(org_id, quota=1, slot_duration=15):
    org = MagicMock(spec=Organization)
    org.id = org_id
    org.timezone = "Asia/Kolkata"
    org.default_slot_duration_minutes = slot_duration
    org.default_consultation_fee = 500.0
    org.max_daily_patients = 50
    org.booking_settings = {
        "booking_quota_per_window": quota,
        "window_duration_minutes": 30,
        "booking_lead_minutes": 15,
    }
    org.weekly_schedule = {
        "monday": {"morningStart": "09:00 AM", "morningEnd": "05:00 PM"},
    }
    return org


@pytest.mark.asyncio
async def test_walkin_token_and_queue_accuracy():
    tz = ZoneInfo("Asia/Kolkata")
    org_id = uuid4()
    org = _build_org(org_id)
    today = datetime.now(tz).date()

    patient = Patient(
        id=uuid4(),
        org_id=org_id,
        first_name="Ravi",
        last_name="Teja",
        phone_number="+919876500001",
        dob=date(1990, 5, 20),
    )
    doctor = User(
        id=uuid4(),
        org_id=org_id,
        role="doctor",
        full_name="Dr. Sunita Rao",
        is_active=True,
    )

    db = AsyncMock()
    db.get.return_value = org

    req = ClinicWalkinBookingRequest(
        patient_name="Ravi Teja",
        patient_phone="+919876500001",
        appointment_date=today,
        chief_complaint="Severe migraine",
        fee=500.0,
        doctor_id=doctor.id,
    )

    with (
        patch("app.services.appointments.booking_service._resolve_patient", new_callable=AsyncMock) as mock_resolve,
        patch("app.services.appointments.booking_service.has_active_visit", new_callable=AsyncMock) as mock_active,
    ):
        mock_resolve.return_value = patient
        mock_active.return_value = False

        doc_res = MagicMock()
        doc_res.scalars.return_value.all.return_value = [doctor]
        doc_res.scalars.return_value.first.return_value = doctor
        lock_res = MagicMock()
        token_res = MagicMock()
        token_res.scalar.return_value = 4
        count_res = MagicMock()
        count_res.scalar.return_value = 0

        db.execute.side_effect = [doc_res, lock_res, token_res, lock_res, count_res]

        def _mock_add(instance):
            if hasattr(instance, "id") and instance.id is None:
                instance.id = uuid4()

        db.add = MagicMock(side_effect=_mock_add)
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        resp = await book_clinic_walkin_appointment(db, req, org_id)

        assert resp.display_token == "W-5"
        assert resp.patient_name == "Ravi Teja"
        assert db.add.called
        created = [c[0][0] for c in db.add.call_args_list if isinstance(c[0][0], Appointment)][0]
        assert created.token_number == 5
        assert created.source == "walk_in"


@pytest.mark.asyncio
async def test_slot_collision_lock_rejects_second_concurrent_caller():
    tz = ZoneInfo("Asia/Kolkata")
    org_id = uuid4()
    org = _build_org(org_id, quota=1)
    target_dt = datetime.now(tz) + timedelta(days=2)
    target_dt = target_dt.replace(hour=10, minute=0, second=0, microsecond=0)

    patient1 = Patient(id=uuid4(), org_id=org_id, first_name="A", last_name="One", phone_number="+919876500011")
    patient2 = Patient(id=uuid4(), org_id=org_id, first_name="B", last_name="Two", phone_number="+919876500022")
    doctor = User(id=uuid4(), org_id=org_id, role="doctor", full_name="Dr. Sunita Rao", is_active=True)

    db = AsyncMock()
    db.get.return_value = org

    req1 = ClinicScheduledBookingRequest(
        patient_name="A One",
        patient_phone="+919876500011",
        doctor_id=doctor.id,
        appointment_date=target_dt.date(),
        appointment_time="10:00 AM",
        chief_complaint="Checkup",
        fee=500.0,
    )
    req2 = ClinicScheduledBookingRequest(
        patient_name="B Two",
        patient_phone="+919876500022",
        doctor_id=doctor.id,
        appointment_date=target_dt.date(),
        appointment_time="10:00 AM",
        chief_complaint="Follow-up",
        fee=500.0,
    )

    with (
        patch("app.services.appointments.booking_service.get_future_capacity", new_callable=AsyncMock) as mock_capacity,
        patch("app.services.appointments.booking_service.has_active_visit", new_callable=AsyncMock) as mock_active,
        patch("app.services.appointments.booking_service._resolve_patient", new_callable=AsyncMock) as mock_resolve,
    ):
        mock_active.return_value = False
        mock_resolve.return_value = patient1
        mock_capacity.side_effect = [
            {"availability": "AVAILABLE"},
            {"availability": "UNAVAILABLE", "reason": "SLOT_EXHAUSTED", "next_available": "11:00 AM"},
        ]

        doc_res = MagicMock()
        doc_res.scalars.return_value.all.return_value = [doctor]
        doc_res.scalars.return_value.first.return_value = doctor
        db.execute.return_value = doc_res
        def _mock_add_appt(instance):
            if hasattr(instance, "id") and instance.id is None:
                instance.id = uuid4()
            if hasattr(instance, "created_at") and instance.created_at is None:
                instance.created_at = datetime.now(timezone.utc)

        db.add = MagicMock(side_effect=_mock_add_appt)
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.commit = AsyncMock()

        resp1 = await book_clinic_scheduled_appointment(db, req1, org_id)
        assert resp1.status == "scheduled"

        mock_resolve.return_value = patient2

        with pytest.raises(HTTPException) as exc:
            await book_clinic_scheduled_appointment(db, req2, org_id)
        assert exc.value.status_code == 409
        assert exc.value.detail["reason"] == "SLOT_EXHAUSTED"



@pytest.mark.asyncio
async def test_duplicate_booking_rejection_for_active_patient():
    org_id = uuid4()
    org = _build_org(org_id)
    db = AsyncMock()
    db.get.return_value = org

    req = ClinicWalkinBookingRequest(
        patient_name="Existing Patient",
        patient_phone="+919876599999",
        appointment_date=datetime.now(ZoneInfo(org.timezone)).date(),
        chief_complaint="Fever",
        fee=500.0,
    )

    with (
        patch("app.services.appointments.booking_service._resolve_patient", new_callable=AsyncMock) as mock_resolve,
        patch("app.services.appointments.booking_service.has_active_visit", new_callable=AsyncMock) as mock_active,
    ):
        mock_resolve.return_value = Patient(id=uuid4(), org_id=org_id, first_name="Existing", last_name="Patient")
        mock_active.return_value = True

        with pytest.raises(HTTPException) as exc:
            await book_clinic_walkin_appointment(db, req, org_id)
        assert exc.value.status_code == 409
        assert "active clinic visit" in exc.value.detail.lower()

