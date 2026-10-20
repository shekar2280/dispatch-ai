"""Regression tests for booking."""

import asyncio
import zoneinfo
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

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
from app.services.appointments.encounter_service import (
    call_appointment_patient,
    complete_consultation,
    mark_appointment_arrived,
    start_consultation,
)
from app.services.appointments.schedule_service import count_leave_collisions, lookup_patients
from app.services.clinic.dashboard_service import get_clinic_patients_service
from app.services.voice.tool_execution_service import execute_tool_call


def test_two_fifteen_minute_times_share_one_capacity_window():
    tz = ZoneInfo("Asia/Kolkata")
    ten = datetime(2026, 10, 6, 10, 0, tzinfo=tz)
    ten_fifteen = datetime(2026, 10, 6, 10, 15, tzinfo=tz)
    ten_thirty = datetime(2026, 10, 6, 10, 30, tzinfo=tz)

    first = capacity_window(ten, 30)
    second = capacity_window(ten_fifteen, 30)
    next_window = capacity_window(ten_thirty, 30)

    assert first == second
    assert first[1] == next_window[0]


def test_collision_count_uses_tenant_and_clinic_day_boundaries():
    db = AsyncMock()
    org_id = uuid4()
    db.get.return_value = SimpleNamespace(timezone="Asia/Kolkata")
    db.scalar.return_value = 8
    result = asyncio.run(count_leave_collisions(db, org_id, date(2026, 10, 4), date(2026, 10, 5)))
    query = db.scalar.call_args.args[0].compile(dialect=postgresql.dialect())
    assert query.params["org_id_1"] == org_id
    assert query.params["start_time_1"].utcoffset() == timedelta(hours=5, minutes=30)
    assert query.params["start_time_2"].date() == date(2026, 10, 6)
    assert "completed" not in query.params["status_1"]
    assert result == {"count": 8}


@pytest.mark.parametrize("start,end", [(date(2026, 10, 5), date(2026, 10, 4)), (date(2025, 1, 1), date(2026, 1, 3))])
def test_collision_range_rejected_before_database_access(start, end):
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(count_leave_collisions(db, uuid4(), start, end))
    assert exc.value.status_code == 422
    db.get.assert_not_awaited()


def test_patient_lookup_validates_country_and_bounds_results():
    db = AsyncMock()
    org_id, patient_id = uuid4(), uuid4()
    db.get.return_value = SimpleNamespace(country_code="GB")
    patient = SimpleNamespace(id=patient_id, first_name="Alex", last_name="Smith", phone_number="+442079460018")
    visit = SimpleNamespace(patient_id=patient_id, status="skipped", display_token="R-1", chief_complaint="")
    db.execute.side_effect = [
        MagicMock(all=MagicMock(return_value=[patient])),
        MagicMock(all=MagicMock(return_value=[visit])),
    ]
    result = asyncio.run(lookup_patients(db, org_id, "020 7946 0018", "Alex"))
    params = db.execute.call_args_list[0].args[0].compile(dialect=postgresql.dialect()).params
    assert org_id in params.values()
    assert 10 in params.values()
    assert any(isinstance(value, list) and "442079460018" in value for value in params.values())
    assert result[0]["priority_reason"] == "Stepped Out for Tests"


def test_incomplete_phone_skips_patient_query():
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(country_code="IN")
    assert asyncio.run(lookup_patients(db, uuid4(), "12345", "Alex")) == []
    db.execute.assert_not_awaited()


def test_empty_patient_page_does_not_load_appointment_history():
    db = AsyncMock()
    db.execute.return_value = MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
    org_id = uuid4()
    assert asyncio.run(get_clinic_patients_service(db, org_id, limit=50, offset=100, search="Alex")) == []
    db.execute.assert_awaited_once()
    params = db.execute.call_args.args[0].compile(dialect=postgresql.dialect()).params
    assert params["org_id_1"] == org_id
    assert params["param_1"] == 50
    assert params["param_2"] == 100


def test_voice_execution_forwards_trusted_session_id():
    session_id = uuid4()
    with patch("app.services.voice.tool_execution_service.dispatch_tool_execution", new_callable=AsyncMock) as dispatch:
        asyncio.run(
            execute_tool_call("confirm_appointment_booking", {}, AsyncMock(), uuid4(), "+919876543210", session_id)
        )
        assert dispatch.call_args.kwargs["call_session_id"] == session_id


def test_lookup_routes_enforce_tenant_and_request_bounds():
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.testclient import TestClient

    from app.api.v1.appointments import router
    from app.core.database import get_db
    from app.core.security import get_current_tenant_org, get_current_user

    app = FastAPI()
    app.include_router(router)
    org_id = uuid4()
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(timezone="Asia/Kolkata", country_code="IN")
    db.scalar.return_value = 2
    mock_exec = MagicMock()
    mock_exec.all.return_value = []
    db.execute.return_value = mock_exec

    async def current_user():
        return SimpleNamespace(id=uuid4(), org_id=org_id)

    async def current_tenant(tenant_org_query: str | None = Query(None, alias="org_id")):
        if tenant_org_query and str(tenant_org_query) != str(org_id):
            raise HTTPException(403, "Access forbidden")
        return org_id

    async def database():
        yield db

    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_current_tenant_org] = current_tenant
    app.dependency_overrides[get_db] = database
    client = TestClient(app)
    assert client.get("/leave-collisions?start_date=2026-10-04&end_date=2026-10-05").json() == {"count": 2}
    assert client.get("/leave-collisions?start_date=2026-10-05&end_date=2026-10-04").status_code == 422
    assert client.get("/patient-lookup?phone=1").status_code == 422
    assert client.get(f"/patient-lookup?phone=9876543210&org_id={uuid4()}").status_code == 403
    assert client.get("/patients?limit=1000").status_code == 422


def test_same_day_voice_booking_preserves_session_uuid():
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from app.services.voice.handlers.clinic_tool_handler import _confirm_booking

    session_id = uuid4()
    org = SimpleNamespace(timezone="Asia/Kolkata")
    now = datetime.now(ZoneInfo(org.timezone))
    future = now + timedelta(minutes=2)
    if future.date() != now.date():
        pytest.skip("No future same-day time remains")
    arguments = {
        "first_name": "Alex",
        "last_name": "Smith",
        "slot_date": now.date().isoformat(),
        "slot_time": future.strftime("%I:%M %p"),
        "booking_mode": "queue",
    }
    db = AsyncMock()
    db.get.return_value = None
    db.execute.return_value = MagicMock()
    with (
        patch(
            "app.services.voice.booking_consent.authorize_booking",
            new_callable=AsyncMock,
            return_value=(SimpleNamespace(booking_result=None), None),
        ),
        patch(
            "app.services.voice.handlers.clinic_tool_handler._select_doctor",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(id=uuid4()),
        ),
        patch(
            "app.services.voice.handlers.clinic_tool_handler.get_future_capacity",
            new_callable=AsyncMock,
            return_value={"reason": "QUEUE_OVERLAP"},
        ),
        patch(
            "app.services.voice.handlers.clinic_tool_handler._create_same_day_token", new_callable=AsyncMock
        ) as create,
    ):
        asyncio.run(_confirm_booking(arguments, db, uuid4(), org, "+919876543210", session_id))
        assert create.call_args.kwargs["call_session_id"] == session_id


def _make_test_org(org_id, quota=2, slot_duration=15):
    org = MagicMock(spec=Organization)
    org.id = org_id
    org.timezone = "Asia/Kolkata"
    org.default_slot_duration_minutes = slot_duration
    org.default_consultation_fee = 500
    org.booking_settings = {
        "booking_quota_per_window": quota,
        "window_duration_minutes": 30,
        "booking_lead_minutes": 15,
    }
    org.weekly_schedule = {
        "tuesday": {"morningStart": "09:00 AM", "morningEnd": "08:00 PM"},
    }
    return org


@pytest.mark.anyio
async def test_walkin_booking_and_chamber_queue_lifecycle():
    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    org_id = uuid4()
    org = _make_test_org(org_id)
    today = datetime.now(tz).date()

    patient = Patient(
        id=uuid4(),
        org_id=org_id,
        first_name="Ananya",
        last_name="Rao",
        phone_number="+919876511111",
        dob=date(1996, 4, 15),
        medical_history={},
    )
    doctor = User(
        id=uuid4(),
        org_id=org_id,
        role="doctor",
        full_name="Dr. Ramesh Roy",
        is_active=True,
    )

    db = AsyncMock()
    db.get.return_value = org

    req = ClinicWalkinBookingRequest(
        patient_name="Ananya Rao",
        patient_phone="+919876511111",
        appointment_date=today,
        chief_complaint="Severe sore throat",
        fee=500.0,
        dob=date(1996, 4, 15),
    )

    with (
        patch("app.services.appointments.booking_service._resolve_patient", new_callable=AsyncMock) as mock_resolve,
        patch("app.services.appointments.booking_service.has_active_visit", new_callable=AsyncMock) as mock_has_active,
    ):
        mock_resolve.return_value = patient
        mock_has_active.return_value = False

        req.doctor_id = doctor.id
        doc_res = MagicMock()
        doc_res.scalars.return_value.all.return_value = [doctor]
        doc_res.scalars.return_value.first.return_value = doctor
        lock_res = MagicMock()
        token_res = MagicMock()
        token_res.scalar.return_value = 0
        db.execute.side_effect = [doc_res, lock_res, token_res]

        def _mock_add(model_instance):
            if hasattr(model_instance, "id") and model_instance.id is None:
                model_instance.id = uuid4()

        db.add = MagicMock(side_effect=_mock_add)
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        resp = await book_clinic_walkin_appointment(db, req, org_id)

        assert resp.display_token == "W-1"
        assert resp.patient_name == "Ananya Rao"
        assert db.add.called
        added_appointments = [c[0][0] for c in db.add.call_args_list if isinstance(c[0][0], Appointment)]
        assert len(added_appointments) == 1
        created_appt = added_appointments[0]
        assert created_appt.source == "walk_in"
        assert created_appt.display_token == "W-1"
        assert created_appt.token_number == 1
        assert created_appt.fee == 500

    appt = created_appt
    mock_lifecycle_exec = MagicMock()
    mock_lifecycle_exec.scalars.return_value.all.return_value = [appt]

    async def _mock_lifecycle_scalar(statement, *args, **kwargs):
        stmt = str(statement).replace("\n", " ")
        if "SELECT appointments.id FROM" in stmt or "appointments.id !=" in stmt:
            return None
        return appt

    db_lifecycle = AsyncMock()
    db_lifecycle.scalar.side_effect = _mock_lifecycle_scalar
    db_lifecycle.execute.return_value = mock_lifecycle_exec
    db_lifecycle.get.return_value = org
    db_lifecycle.add = MagicMock()

    with patch(
        "app.services.appointments.encounter_service.build_single_appointment_response", new_callable=AsyncMock
    ) as mock_build_call:
        mock_build_call.return_value = MagicMock(status="arrived", queue_state="called")
        await call_appointment_patient(db_lifecycle, appt.id, org_id)
        assert appt.queue_state == "called"
        assert appt.called_at is not None
        assert appt.call_count == 1

    with patch(
        "app.services.appointments.encounter_service.build_single_appointment_response", new_callable=AsyncMock
    ) as mock_build_start:
        mock_build_start.return_value = MagicMock(status="in_progress", encounter_state="in_progress")
        await start_consultation(db_lifecycle, appt.id, org_id)
        assert appt.status == "in_progress"
        assert appt.encounter_state == "in_progress"
        assert appt.queue_state == "served"
        assert appt.consultation_started_at is not None

    with (
        patch(
            "app.services.appointments.encounter_service.build_single_appointment_response", new_callable=AsyncMock
        ) as mock_build_comp,
        patch(
            "app.services.appointments.encounter_service.record_consultation_completion_metrics", new_callable=AsyncMock
        ),
    ):
        mock_build_comp.return_value = MagicMock(status="completed", encounter_state="completed")
        await complete_consultation(db_lifecycle, appt.id, org_id)
        assert appt.status == "completed"
        assert appt.encounter_state == "completed"
        assert appt.consultation_ended_at is not None
        assert appt.actual_duration_seconds is not None


@pytest.mark.anyio
async def test_walkin_booking_rejects_future_date_with_400():
    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    org_id = uuid4()
    org = _make_test_org(org_id)
    tomorrow = datetime.now(tz).date() + timedelta(days=1)

    db = AsyncMock()
    db.get.return_value = org

    req = ClinicWalkinBookingRequest(
        patient_name="Ananya Rao",
        patient_phone="+919876511111",
        appointment_date=tomorrow,
        chief_complaint="Checkup",
    )

    with pytest.raises(HTTPException) as exc:
        await book_clinic_walkin_appointment(db, req, org_id)

    assert exc.value.status_code == 400
    assert "available for today only" in exc.value.detail


@pytest.mark.anyio
async def test_walkin_booking_rejects_duplicate_active_visit_with_409():
    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    org_id = uuid4()
    org = _make_test_org(org_id)
    today = datetime.now(tz).date()

    patient = Patient(
        id=uuid4(),
        org_id=org_id,
        first_name="Ananya",
        last_name="Rao",
        phone_number="+919876511111",
    )

    db = AsyncMock()
    db.get.return_value = org

    req = ClinicWalkinBookingRequest(
        patient_name="Ananya Rao",
        patient_phone="+919876511111",
        appointment_date=today,
    )

    with (
        patch("app.services.appointments.booking_service._resolve_patient", new_callable=AsyncMock) as mock_resolve,
        patch("app.services.appointments.booking_service.has_active_visit", new_callable=AsyncMock) as mock_has_active,
    ):
        mock_resolve.return_value = patient
        mock_has_active.return_value = True

        with pytest.raises(HTTPException) as exc:
            await book_clinic_walkin_appointment(db, req, org_id)

        assert exc.value.status_code == 409
        assert "already has an active clinic visit" in exc.value.detail


@pytest.mark.anyio
async def test_scheduled_booking_full_capacity_conflict_lock_returns_409():
    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    org_id = uuid4()
    org = _make_test_org(org_id, quota=2)
    target_date = datetime.now(tz).date() + timedelta(days=2)

    db = AsyncMock()
    db.get.return_value = org

    patient = Patient(
        id=uuid4(),
        org_id=org_id,
        first_name="Ananya",
        last_name="Rao",
        phone_number="+919876511111",
    )
    doctor = User(
        id=uuid4(),
        org_id=org_id,
        role="doctor",
        full_name="Dr. Ramesh Roy",
        is_active=True,
    )

    doc_res = MagicMock()
    doc_res.scalars.return_value.first.return_value = doctor
    db.execute.return_value = doc_res

    req = ClinicScheduledBookingRequest(
        patient_name="Ananya Rao",
        patient_phone="+919876511111",
        appointment_date=target_date,
        appointment_time="10:00 AM",
    )

    with (
        patch("app.services.appointments.booking_service.get_future_capacity", new_callable=AsyncMock) as mock_capacity,
        patch("app.services.appointments.booking_service.lock_capacity_window", new_callable=AsyncMock) as mock_lock,
        patch("app.services.appointments.booking_service.count_window_bookings", new_callable=AsyncMock) as mock_count,
        patch("app.services.appointments.booking_service.has_active_visit", new_callable=AsyncMock) as mock_active,
        patch("app.services.appointments.booking_service._resolve_patient", new_callable=AsyncMock) as mock_resolve,
    ):
        mock_active.return_value = False
        mock_resolve.return_value = patient
        mock_capacity.return_value = {"availability": "AVAILABLE"}
        mock_lock.return_value = (datetime.now(tz), datetime.now(tz) + timedelta(minutes=30))
        mock_count.return_value = 2

        with pytest.raises(HTTPException) as exc:
            await book_clinic_scheduled_appointment(db, req, org_id)

        assert exc.value.status_code == 409
        assert "fully booked" in exc.value.detail
