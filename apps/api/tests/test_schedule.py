"""Regression tests for schedule."""

import asyncio
import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from app.models.organization import Organization
from app.models.schedule_override import ScheduleOverride
from app.schemas.schedule_override import ScheduleOverrideCreate
from app.services.appointments.schedule_service import get_effective_weekly_schedule
from app.services.clinic.organization_service import create_org_closure_service


def test_schedule_override_uses_current_table():
    assert ScheduleOverride.__tablename__ == "schedule_overrides"


def test_special_hours_override_storage():
    org_id = uuid.uuid4()
    body = ScheduleOverrideCreate(
        title="Sunday Morning Extra Shift",
        override_type="special_hours",
        start_date=date(2026, 10, 11),
        end_date=date(2026, 10, 11),
        custom_hours=[{"name": "Morning Shift", "start": "09:00", "end": "12:00"}],
        reason="Overtime clinic OPD",
    )

    fake_db = AsyncMock()
    fake_org = Organization(id=org_id, name="Test Clinic")
    fake_db.get.return_value = fake_org

    saved_obj = None

    def fake_add(instance):
        nonlocal saved_obj
        saved_obj = instance

    fake_db.add = MagicMock(side_effect=fake_add)

    asyncio.run(create_org_closure_service(fake_db, org_id, body))

    assert saved_obj is not None
    assert saved_obj.override_type == "special_hours"
    assert saved_obj.is_available is True
    assert saved_obj.custom_hours == [{"name": "Morning Shift", "start": "09:00", "end": "12:00"}]
    assert saved_obj.title == "Sunday Morning Extra Shift"
    assert saved_obj.doctor_id is None


def test_doctor_leave_storage():
    org_id = uuid.uuid4()
    doctor_id = uuid.uuid4()
    body = ScheduleOverrideCreate(
        doctor_id=doctor_id,
        title="Dr. Sharma Vacation",
        override_type="vacation",
        start_date=date(2026, 10, 15),
        end_date=date(2026, 10, 18),
        reason="Annual Leave",
        emergency_phone="+919876543210",
    )

    fake_db = AsyncMock()
    fake_org = Organization(id=org_id, name="Test Clinic")
    fake_db.get.return_value = fake_org

    saved_obj = None

    def fake_add(instance):
        nonlocal saved_obj
        saved_obj = instance

    fake_db.add = MagicMock(side_effect=fake_add)

    asyncio.run(create_org_closure_service(fake_db, org_id, body))

    assert saved_obj is not None
    assert saved_obj.override_type == "vacation"
    assert saved_obj.is_available is False
    assert saved_obj.doctor_id == doctor_id
    assert saved_obj.emergency_phone == "+919876543210"


def test_emergency_closure_storage():
    org_id = uuid.uuid4()
    body = ScheduleOverrideCreate(
        title="Emergency Power Outage",
        override_type="emergency_closure",
        start_date=date(2026, 10, 20),
        end_date=date(2026, 10, 20),
        reason="Grid failure",
        emergency_phone="108",
    )

    fake_db = AsyncMock()
    fake_org = Organization(id=org_id, name="Test Clinic")
    fake_db.get.return_value = fake_org

    saved_obj = None

    def fake_add(instance):
        nonlocal saved_obj
        saved_obj = instance

    fake_db.add = MagicMock(side_effect=fake_add)

    asyncio.run(create_org_closure_service(fake_db, org_id, body))

    assert saved_obj is not None
    assert saved_obj.override_type == "emergency_closure"
    assert saved_obj.is_available is False
    assert saved_obj.emergency_phone == "108"
    assert saved_obj.reason == "Grid failure"


def test_effective_schedule_closed_sunday_does_not_close_week():
    raw = {
        "monday": [{"start": "09:00", "end": "13:00"}],
        "sunday": [],
    }
    effective = get_effective_weekly_schedule(raw)
    assert effective["monday"]["isOpen"] is True
    assert effective["sunday"]["isOpen"] is False
