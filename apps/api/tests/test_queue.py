"""Regression tests for queue."""

import zoneinfo
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.appointment import Appointment
from app.models.organization import Organization
from app.services.appointments.queue_service import get_ordered_active_queue


def _make_org(tz_name="Asia/Kolkata", priority_window=15, late_grace=15, rollover_minutes=90):
    org = MagicMock(spec=Organization)
    org.timezone = tz_name
    org.appointment_priority_window_minutes = priority_window
    org.booking_settings = {
        "late_grace_minutes": late_grace,
        "rollover_priority_minutes": rollover_minutes,
        "window_duration_minutes": 30,
        "booking_quota_per_window": 2,
    }
    org.weekly_schedule = {
        "tuesday": {"morningStart": "09:00 AM", "morningEnd": "01:00 PM"},
    }
    return org


def _make_appt(
    org_id,
    token_number,
    token_prefix=None,
    source="walk_in",
    status="arrived",
    queue_state="waiting",
    start_time=None,
    checked_in_at=None,
    appointment_time=None,
):
    appt = MagicMock(spec=Appointment)
    appt.id = uuid4()
    appt.org_id = org_id
    appt.token_number = token_number
    appt.token_prefix = token_prefix
    appt.display_token = f"{token_prefix}-{token_number}" if token_prefix else str(token_number)
    appt.source = source
    appt.status = status
    appt.queue_state = queue_state
    appt.start_time = start_time
    appt.checked_in_at = checked_in_at
    appt.created_at = checked_in_at
    appt.appointment_time = appointment_time
    return appt


@pytest.mark.anyio
async def test_simultaneous_arrival_prioritizes_scheduled_over_walkin():
    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    org_id = uuid4()
    org = _make_org()

    simulated_now = datetime(2026, 10, 6, 10, 0, tzinfo=tz)

    scheduled = _make_appt(
        org_id=org_id,
        token_number=1,
        source="ai_voice",
        start_time=simulated_now,
        checked_in_at=simulated_now,
        appointment_time="10:00 AM",
    )
    walkin = _make_appt(
        org_id=org_id,
        token_number=2,
        source="walk_in",
        start_time=simulated_now,
        checked_in_at=simulated_now,
        appointment_time=None,
    )

    db = AsyncMock()
    db.get.return_value = org
    res = MagicMock()
    res.scalars.return_value.all.return_value = [walkin, scheduled]
    db.execute.return_value = res

    ordered = await get_ordered_active_queue(db, org_id)

    assert len(ordered) == 2
    assert ordered[0].id == scheduled.id
    assert ordered[1].id == walkin.id


@pytest.mark.anyio
async def test_late_arrival_demoted_to_tier_4_behind_walkin_without_cancellation():
    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    org_id = uuid4()
    org = _make_org(late_grace=15)

    slot_time = datetime(2026, 10, 6, 10, 0, tzinfo=tz)
    late_arrival_time = slot_time + timedelta(minutes=25)

    late_scheduled = _make_appt(
        org_id=org_id,
        token_number=1,
        source="ai_voice",
        start_time=slot_time,
        checked_in_at=late_arrival_time,
        appointment_time="10:00 AM",
    )
    punctual_walkin = _make_appt(
        org_id=org_id,
        token_number=2,
        source="walk_in",
        start_time=slot_time,
        checked_in_at=slot_time + timedelta(minutes=20),
        appointment_time=None,
    )

    db = AsyncMock()
    db.get.return_value = org
    res = MagicMock()
    res.scalars.return_value.all.return_value = [late_scheduled, punctual_walkin]
    db.execute.return_value = res

    ordered = await get_ordered_active_queue(db, org_id)

    assert len(ordered) == 2
    assert ordered[0].id == punctual_walkin.id
    assert ordered[1].id == late_scheduled.id
    assert late_scheduled.status == "arrived"


@pytest.mark.anyio
async def test_early_arrival_held_at_tier_3_until_window_opens():
    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    org_id = uuid4()
    org = _make_org(priority_window=15)

    future_slot = datetime(2026, 10, 6, 11, 0, tzinfo=tz)
    arrival_time = datetime(2026, 10, 6, 10, 0, tzinfo=tz)

    early_scheduled = _make_appt(
        org_id=org_id,
        token_number=1,
        source="ai_voice",
        start_time=future_slot,
        checked_in_at=arrival_time,
        appointment_time="11:00 AM",
    )
    regular_walkin = _make_appt(
        org_id=org_id,
        token_number=2,
        source="walk_in",
        start_time=arrival_time,
        checked_in_at=arrival_time - timedelta(minutes=5),
        appointment_time=None,
    )

    db = AsyncMock()
    db.get.return_value = org
    res = MagicMock()
    res.scalars.return_value.all.return_value = [early_scheduled, regular_walkin]
    db.execute.return_value = res

    ordered = await get_ordered_active_queue(db, org_id)

    assert len(ordered) == 2
    assert ordered[0].id == regular_walkin.id
    assert ordered[1].id == early_scheduled.id


@pytest.mark.anyio
async def test_walkin_waiting_over_60_minutes_escalates_to_tier_2():
    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    org_id = uuid4()
    org = _make_org()

    clinic_now = datetime.now(tz)
    long_waiting_arrival = clinic_now - timedelta(minutes=65)
    recent_arrival = clinic_now - timedelta(minutes=5)

    long_waiting_walkin = _make_appt(
        org_id=org_id,
        token_number=1,
        source="walk_in",
        start_time=clinic_now,
        checked_in_at=long_waiting_arrival,
    )
    new_walkin = _make_appt(
        org_id=org_id,
        token_number=2,
        source="walk_in",
        start_time=clinic_now,
        checked_in_at=recent_arrival,
    )

    db = AsyncMock()
    db.get.return_value = org
    res = MagicMock()
    res.scalars.return_value.all.return_value = [new_walkin, long_waiting_walkin]
    db.execute.return_value = res

    ordered = await get_ordered_active_queue(db, org_id)

    assert len(ordered) == 2
    assert ordered[0].id == long_waiting_walkin.id
    assert ordered[1].id == new_walkin.id


@pytest.mark.anyio
async def test_rollover_priority_active_holds_tier_1():
    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    org_id = uuid4()
    clinic_now = datetime.now(tz)
    today_name = clinic_now.strftime("%A").lower()

    ten_mins_ago = (clinic_now - timedelta(minutes=10)).strftime("%I:%M %p")
    org = _make_org(rollover_minutes=90)
    org.weekly_schedule = {
        today_name: {"morningStart": ten_mins_ago, "morningEnd": "08:00 PM"},
    }

    rollover_appt = _make_appt(
        org_id=org_id,
        token_number=1,
        token_prefix="R",
        source="manual",
        start_time=clinic_now,
        checked_in_at=clinic_now,
    )
    regular_on_time = _make_appt(
        org_id=org_id,
        token_number=2,
        source="ai_voice",
        start_time=clinic_now,
        checked_in_at=clinic_now - timedelta(minutes=10),
        appointment_time=clinic_now.strftime("%I:%M %p"),
    )

    db = AsyncMock()
    db.get.return_value = org
    res = MagicMock()
    res.scalars.return_value.all.return_value = [regular_on_time, rollover_appt]
    db.execute.return_value = res

    ordered = await get_ordered_active_queue(db, org_id)

    assert len(ordered) == 2
    assert ordered[0].id == regular_on_time.id
    assert ordered[1].id == rollover_appt.id


@pytest.mark.anyio
async def test_skipped_patient_sorted_to_tier_5():
    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    org_id = uuid4()
    org = _make_org()

    clinic_now = datetime.now(tz)

    skipped = _make_appt(
        org_id=org_id,
        token_number=1,
        source="walk_in",
        status="skipped",
        queue_state="stepped_out",
        start_time=clinic_now,
        checked_in_at=clinic_now - timedelta(minutes=50),
    )
    fresh_walkin = _make_appt(
        org_id=org_id,
        token_number=2,
        source="walk_in",
        status="arrived",
        queue_state="waiting",
        start_time=clinic_now,
        checked_in_at=clinic_now,
    )

    db = AsyncMock()
    db.get.return_value = org
    res = MagicMock()
    res.scalars.return_value.all.return_value = [skipped, fresh_walkin]
    db.execute.return_value = res

    ordered = await get_ordered_active_queue(db, org_id)

    assert len(ordered) == 2
    assert ordered[0].id == fresh_walkin.id
    assert ordered[1].id == skipped.id


@pytest.mark.anyio
async def test_identical_arrival_tie_broken_by_token_number():
    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    org_id = uuid4()
    org = _make_org()

    simultaneous_time = datetime(2026, 10, 6, 10, 0, tzinfo=tz)

    token_10 = _make_appt(
        org_id=org_id,
        token_number=10,
        source="walk_in",
        start_time=simultaneous_time,
        checked_in_at=simultaneous_time,
    )
    token_3 = _make_appt(
        org_id=org_id,
        token_number=3,
        source="walk_in",
        start_time=simultaneous_time,
        checked_in_at=simultaneous_time,
    )

    db = AsyncMock()
    db.get.return_value = org
    res = MagicMock()
    res.scalars.return_value.all.return_value = [token_10, token_3]
    db.execute.return_value = res

    ordered = await get_ordered_active_queue(db, org_id)

    assert len(ordered) == 2
    assert ordered[0].token_number == 3
    assert ordered[1].token_number == 10


@pytest.mark.anyio
async def test_expired_rollover_priority_demoted_from_tier_1():
    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    org_id = uuid4()
    clinic_now = datetime.now(tz)
    today_name = clinic_now.strftime("%A").lower()

    one_hundred_mins_ago = (clinic_now - timedelta(minutes=100)).strftime("%I:%M %p")
    org = _make_org(rollover_minutes=90)
    org.weekly_schedule = {
        today_name: {"morningStart": one_hundred_mins_ago, "morningEnd": "08:00 PM"},
    }

    expired_rollover = _make_appt(
        org_id=org_id,
        token_number=1,
        token_prefix="R",
        source="manual",
        start_time=clinic_now,
        checked_in_at=clinic_now - timedelta(minutes=5),
        appointment_time=clinic_now.strftime("%I:%M %p"),
    )
    scheduled_on_time = _make_appt(
        org_id=org_id,
        token_number=2,
        source="ai_voice",
        start_time=clinic_now,
        checked_in_at=clinic_now - timedelta(minutes=15),
        appointment_time=clinic_now.strftime("%I:%M %p"),
    )

    db = AsyncMock()
    db.get.return_value = org
    res = MagicMock()
    res.scalars.return_value.all.return_value = [expired_rollover, scheduled_on_time]
    db.execute.return_value = res

    ordered = await get_ordered_active_queue(db, org_id)

    assert len(ordered) == 2
    assert ordered[0].id == scheduled_on_time.id
    assert ordered[1].id == expired_rollover.id


@pytest.mark.anyio
async def test_missing_checked_in_at_falls_back_gracefully():
    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    org_id = uuid4()
    org = _make_org()

    appt = _make_appt(
        org_id=org_id,
        token_number=1,
        source="walk_in",
        start_time=datetime.now(tz),
        checked_in_at=None,
    )
    appt.created_at = None

    db = AsyncMock()
    db.get.return_value = org
    res = MagicMock()
    res.scalars.return_value.all.return_value = [appt]
    db.execute.return_value = res

    ordered = await get_ordered_active_queue(db, org_id)
    assert len(ordered) == 1
    assert ordered[0].id == appt.id
