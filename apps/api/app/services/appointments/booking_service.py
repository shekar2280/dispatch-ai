from app.core.clinic_config import require_clinic_booking_integer
from app.core.clinic_config import require_clinic_timezone
from app.services.appointments.intake import validate_intake
import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, time, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo
import logging

from fastapi import HTTPException, status
from sqlalchemy import cast, String, func, text, or_, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import AsyncSessionLocal
from app.core.phone_utils import normalize_phone_e164
from app.models.organization import Organization
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.user import User
from app.models.payment_receipt import PaymentReceipt
from app.models.clinic_membership import ClinicMembership
from app.models.audit_log import SystemAuditLog
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentResponse,
    ClinicWalkinBookingRequest,
    ClinicScheduledBookingRequest,
)
from app.services.infra.redis_cache import invalidate_slot_cache
from app.services.appointments.encounter_service import write_visit_event
from app.services.appointments.schedule_service import (
    parse_time_str,
    format_time_label,
    get_effective_weekly_schedule,
    merge_opening_windows,
    get_org_timezone,
    resolve_org_timezone,
)

logger = logging.getLogger(__name__)

CAPACITY_STATUSES = ("scheduled", "arrived", "in_progress", "completed", "skipped")


def capacity_window(start: datetime, window_minutes: int) -> tuple[datetime, datetime]:
    midnight = start.replace(hour=0, minute=0, second=0, microsecond=0)
    minutes = start.hour * 60 + start.minute
    bucket_start = midnight + timedelta(minutes=(minutes // window_minutes) * window_minutes)
    return bucket_start, bucket_start + timedelta(minutes=window_minutes)


async def lock_capacity_window(
    db: AsyncSession, org_id: UUID, doctor_id: Optional[UUID], start: datetime,
    window_minutes: int,
) -> tuple[datetime, datetime]:
    window_start, window_end = capacity_window(start, window_minutes)
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"clinic-capacity:{org_id}:{doctor_id}:{window_start.astimezone(timezone.utc).isoformat()}"},
    )
    return window_start, window_end


async def count_window_bookings(
    db: AsyncSession, org_id: UUID, doctor_id: Optional[UUID],
    window_start: datetime, window_end: datetime, exclude_id: Optional[UUID] = None,
) -> int:
    query = select(func.count(Appointment.id)).where(
        Appointment.org_id == org_id,
        Appointment.start_time >= window_start,
        Appointment.start_time < window_end,
        Appointment.source != "walk_in",
        cast(Appointment.status, String).in_(CAPACITY_STATUSES),
    )
    query = query.where(Appointment.doctor_id == doctor_id) if doctor_id else query.where(Appointment.doctor_id.is_(None))
    if exclude_id:
        query = query.where(Appointment.id != exclude_id)
    return int(await db.scalar(query) or 0)


def build_capacity_blocks(
    target_date: date,
    schedule: Dict[str, Any],
    window_duration_minutes: int,
    timezone: ZoneInfo,
    slot_step_minutes: Optional[int] = None,
    consultation_duration_minutes: Optional[int] = None,
) -> List[Dict[str, Any]]:
    day_config = schedule.get(target_date.strftime("%A").lower(), {})
    if not day_config.get("isOpen", True):
        return []

    blocks: List[Dict[str, Any]] = []
    windows = day_config.get("windows") or [
        {"start": day_config.get(start_key, ""), "end": day_config.get(end_key, "")}
        for start_key, end_key in (("morningStart", "morningEnd"), ("eveningStart", "eveningEnd"))
    ]
    for window in windows:
        start = parse_time_str(window.get("start", ""))
        end = parse_time_str(window.get("end", ""))
        if not start or not end:
            continue
        cursor = datetime.combine(target_date, start).replace(tzinfo=timezone)
        finish = datetime.combine(target_date, end).replace(tzinfo=timezone)
        step = slot_step_minutes or window_duration_minutes
        visit_duration = consultation_duration_minutes or window_duration_minutes
        # An arrival time is only offered when the expected consultation can
        # finish inside the clinic session. This prevents a 7:45 PM arrival
        # from being offered for an 8:00 PM close and a 30 minute visit.
        while cursor + timedelta(minutes=visit_duration) <= finish:
            block_end = cursor + timedelta(minutes=step)
            blocks.append({
                "time": format_time_label(cursor.time()),
                "start": cursor,
                "end": block_end,
                "hour_label": cursor.strftime("%I:00 %p"),
            })
            cursor += timedelta(minutes=step)
    return blocks


async def lock_daily_capacity(
    db: AsyncSession,
    org_id: UUID,
    target_date: date,
) -> None:
    """Serialize admissions for one clinic day across booking channels."""
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"clinic-daily-capacity:{org_id}:{target_date.isoformat()}"},
    )


async def count_daily_active_visits(
    db: AsyncSession,
    org_id: UUID,
    target_date: date,
    timezone: ZoneInfo,
    exclude_id: Optional[UUID] = None,
) -> int:
    day_start = datetime.combine(target_date, time.min, tzinfo=timezone)
    day_end = day_start + timedelta(days=1)
    query = select(func.count(Appointment.id)).where(
        Appointment.org_id == org_id,
        Appointment.start_time >= day_start,
        Appointment.start_time < day_end,
        cast(Appointment.status, String).in_(CAPACITY_STATUSES),
    )
    if exclude_id:
        query = query.where(Appointment.id != exclude_id)
    return int(await db.scalar(query) or 0)


async def get_effective_consultation_duration(
    db: AsyncSession,
    org: Organization,
    org_id: UUID,
    target_date: date,
) -> Tuple[int, bool]:
    configured_duration = int(require_clinic_booking_integer(org, "default_slot_duration_minutes"))

    start_history_date = target_date - timedelta(days=3)
    telemetry_query = select(Appointment.actual_duration_seconds).where(
        Appointment.org_id == org_id,
        Appointment.appointment_date >= start_history_date,
        Appointment.appointment_date <= target_date,
        Appointment.actual_duration_seconds.isnot(None),
        Appointment.actual_duration_seconds >= 60,
    )
    res = await db.execute(telemetry_query)
    durations = [row[0] for row in res.all() if row[0] is not None]

    if len(durations) >= 3:
        durations_sorted = sorted(durations)
        mid = len(durations_sorted) // 2
        if len(durations_sorted) % 2 == 1:
            median_seconds = durations_sorted[mid]
        else:
            median_seconds = (durations_sorted[mid - 1] + durations_sorted[mid]) / 2.0
        empirical_minutes = max(int(round(median_seconds / 60.0)), 5)
        return empirical_minutes, True

    return configured_duration, False


async def get_future_capacity(
    db: AsyncSession,
    org: Organization,
    org_id: UUID,
    target_date: date,
    requested_time: Optional[str] = None,
    doctor_id: Optional[UUID] = None,
    exclude_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    timezone = ZoneInfo(require_clinic_timezone(org))
    now_local = datetime.now(timezone)
    is_today = target_date == now_local.date()

    effective_duration, is_empirical = await get_effective_consultation_duration(
        db, org, org_id, target_date
    )
    configured_duration = require_clinic_booking_integer(org, "default_slot_duration_minutes")
    window_duration = int((org.booking_settings or {}).get("window_duration_minutes", 30))
    max_daily_patients = require_clinic_booking_integer(org, "max_daily_patients")

    from app.models.schedule_override import ScheduleOverride
    schedule = get_effective_weekly_schedule(org.weekly_schedule)
    overrides = list((await db.execute(select(ScheduleOverride).where(
        ScheduleOverride.org_id == org_id, ScheduleOverride.start_date <= target_date,
        ScheduleOverride.end_date >= target_date,
        or_(ScheduleOverride.doctor_id.is_(None), ScheduleOverride.doctor_id == doctor_id),
    ))).scalars().all())
    for override in overrides:
        if override.override_type == "special_hours" and override.custom_hours:
            day_name = target_date.strftime("%A").lower()
            day_cfg = schedule.get(day_name, {})
            schedule = {
                **schedule,
                day_name: {
                    **day_cfg,
                    "isOpen": True,
                    "windows": merge_opening_windows(day_cfg.get("windows") or [], override.custom_hours),
                },
            }
        elif not override.is_available:
            return {"availability": "UNAVAILABLE", "reason": "CLINIC_CLOSED", "available_slots": [], "next_available": None}
    if target_date < now_local.date():
        return {"availability": "UNAVAILABLE", "reason": "PAST_DATE", "available_slots": [], "next_available": None}
    blocks = build_capacity_blocks(
        target_date,
        schedule,
        window_duration,
        timezone,
        min(15, window_duration),
        consultation_duration_minutes=configured_duration,
    )

    daily_active_count = await count_daily_active_visits(
        db, org_id, target_date, timezone, exclude_id=exclude_id,
    )
    if daily_active_count >= max_daily_patients:
        return {
            "availability": "UNAVAILABLE",
            "reason": "DAILY_CAPACITY_REACHED",
            "requested_time": requested_time,
            "next_available": None,
            "available_slots": [],
            "waiting_patients": 0,
            "effective_duration_minutes": effective_duration,
            "is_empirical_duration": is_empirical,
            "queue_clearance_time": None,
            "arrival_slots": [],
            "recommended_slots": [],
            "busy_slots": [],
        }

    # A planning window is a demand signal, not a hard admission quota.  One
    # expected arrival per 30 minutes is the conservative default until a
    # clinic explicitly calibrates its own target from real consultation data.
    arrival_target = max(1, int((org.booking_settings or {}).get("arrival_target_per_window", 1)))
    day_start = datetime.combine(target_date, time.min, tzinfo=timezone)
    day_end = day_start + timedelta(days=1)
    expected_query = select(Appointment.start_time).where(
        Appointment.org_id == org_id,
        Appointment.start_time >= day_start,
        Appointment.start_time < day_end,
        Appointment.source != "walk_in",
        cast(Appointment.status, String).in_(CAPACITY_STATUSES),
        *([Appointment.doctor_id == doctor_id] if doctor_id else []),
    )
    if exclude_id:
        expected_query = expected_query.where(Appointment.id != exclude_id)
    expected_rows = (await db.execute(expected_query)).scalars().all()
    expected_by_window: Dict[datetime, int] = {}
    for start_time in expected_rows:
        local_start = start_time if start_time.tzinfo else start_time.replace(tzinfo=timezone)
        window_start, _ = capacity_window(local_start.astimezone(timezone), window_duration)
        expected_by_window[window_start] = expected_by_window.get(window_start, 0) + 1

    waiting_count = 0
    clearance_time: Optional[datetime] = None
    if is_today:
        waiting_res = await db.execute(
            select(func.count(Appointment.id)).where(
                Appointment.org_id == org_id,
                Appointment.start_time >= datetime.combine(target_date, time.min, tzinfo=timezone),
                Appointment.start_time < datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=timezone),
                cast(Appointment.status, String).in_(["arrived", "in_progress"]),
                *([Appointment.doctor_id == doctor_id] if doctor_id else []),
            )
        )
        waiting_count = waiting_res.scalar() or 0
        clearance_time = now_local + timedelta(minutes=waiting_count * effective_duration)

    available: List[Dict[str, Any]] = []
    overlap_blocks: List[Dict[str, Any]] = []

    for block in blocks:
        lead_minutes = int((org.booking_settings or {}).get("quiet_booking_lead_minutes", 5) if waiting_count == 0 else (org.booking_settings or {}).get("booking_lead_minutes", 15))
        if is_today and (block["start"] < now_local + timedelta(minutes=lead_minutes) or (clearance_time and block["start"] < clearance_time)):
            overlap_blocks.append(block)
        else:
            available.append(block)

    requested_value = parse_time_str(requested_time or "")
    requested_block = next(
        (block for block in blocks if requested_value and block["start"].time() == requested_value),
        None,
    )

    requested_available = False
    rejection_reason: Optional[str] = None

    if requested_block:
        if any(block["time"] == requested_block["time"] for block in available):
            requested_available = True
        elif any(block["time"] == requested_block["time"] for block in overlap_blocks):
            rejection_reason = "QUEUE_OVERLAP"
        else:
            rejection_reason = "INSUFFICIENT_CAPACITY"
    elif requested_time:
        rejection_reason = "SLOT_NOT_FOUND"

    next_block = next(
        (block for block in available if requested_block is None or block["start"] >= requested_block["start"]),
        available[0] if available else None,
    )

    clearance_str = (
        format_time_label(clearance_time.time())
        if clearance_time
        else None
    )
    arrival_slots = []
    for block in available:
        window_start, _ = capacity_window(block["start"], window_duration)
        expected_arrivals = expected_by_window.get(window_start, 0)
        arrival_slots.append({
            "time": block["time"],
            "expected_arrivals": expected_arrivals,
            "demand": "BUSY" if expected_arrivals >= arrival_target else "AVAILABLE",
        })
    recommended_slots = [slot["time"] for slot in arrival_slots if slot["demand"] == "AVAILABLE"]
    busy_slots = [slot["time"] for slot in arrival_slots if slot["demand"] == "BUSY"]
    requested_demand = next(
        (slot["demand"] for slot in arrival_slots if requested_block and slot["time"] == requested_block["time"]),
        None,
    )

    return {
        "availability": "AVAILABLE" if requested_available else ("UNAVAILABLE" if requested_time else ("AVAILABLE" if available else "UNAVAILABLE")),
        "reason": rejection_reason,
        "requested_time": requested_time,
        "next_available": next_block["time"] if next_block else None,
        "available_slots": [block["time"] for block in available],
        "capacity_blocks": len(blocks),
        "reserved_blocks": len(overlap_blocks),
        "daily_active_visits": daily_active_count,
        "max_daily_patients": max_daily_patients,
        "waiting_patients": waiting_count,
        "effective_duration_minutes": effective_duration,
        "is_empirical_duration": is_empirical,
        "queue_clearance_time": clearance_str,
        "arrival_target_per_window": arrival_target,
        "arrival_slots": arrival_slots,
        "recommended_slots": recommended_slots,
        "busy_slots": busy_slots,
        "requested_demand": requested_demand,
    }


async def get_hourly_capacity_ledger(
    db: AsyncSession,
    org: Organization,
    org_id: UUID,
    target_date: date,
) -> List[Dict[str, Any]]:
    timezone = ZoneInfo(require_clinic_timezone(org))
    now_local = datetime.now(timezone)
    is_today = target_date == now_local.date()

    effective_duration, is_empirical = await get_effective_consultation_duration(
        db, org, org_id, target_date
    )
    window_duration = int((org.booking_settings or {}).get("window_duration_minutes", 30))

    blocks = build_capacity_blocks(
        target_date,
        get_effective_weekly_schedule(org.weekly_schedule),
        window_duration,
        timezone,
    )

    clearance_time: Optional[datetime] = None
    if is_today:
        waiting_res = await db.execute(
            select(func.count(Appointment.id)).where(
                Appointment.org_id == org_id,
                Appointment.start_time >= datetime.combine(target_date, time.min, tzinfo=timezone),
                Appointment.start_time < datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=timezone),
                cast(Appointment.status, String).in_(["arrived"]),
            )
        )
        waiting_count = waiting_res.scalar() or 0
        clearance_time = now_local + timedelta(minutes=waiting_count * effective_duration)

    appts_res = await db.execute(
        select(Appointment).where(
            Appointment.org_id == org_id,
            Appointment.start_time >= datetime.combine(target_date, time.min, tzinfo=timezone),
            Appointment.start_time < datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=timezone),
            Appointment.source != "walk_in",
            cast(Appointment.status, String).in_(CAPACITY_STATUSES),
        )
    )
    booked_appointments = appts_res.scalars().all()

    buckets_dict: Dict[str, Dict[str, Any]] = {}
    for block in blocks:
        h_label = block["hour_label"]
        if h_label not in buckets_dict:
            buckets_dict[h_label] = {
                "hour_label": h_label,
                "total_slots": 0,
                "booked_slots": 0,
                "available_slots": 0,
                "in_queue_clearance_zone": False,
                "slots": [],
            }

        window_start, window_end = capacity_window(block["start"], window_duration)
        occupied_count = sum(
            1 for appt in booked_appointments if appt.start_time and
            window_start <= (appt.start_time if appt.start_time.tzinfo else appt.start_time.replace(tzinfo=timezone)) < window_end
        )
        quota = int((org.booking_settings or {}).get("booking_quota_per_window", 2))
        occupied = occupied_count >= quota
        in_clearance = is_today and clearance_time is not None and block["start"] < clearance_time

        buckets_dict[h_label]["total_slots"] += quota
        buckets_dict[h_label]["booked_slots"] += occupied_count
        if in_clearance:
            buckets_dict[h_label]["in_queue_clearance_zone"] = True
        else:
            buckets_dict[h_label]["available_slots"] += max(quota - occupied_count, 0)

        buckets_dict[h_label]["slots"].append({
            "time": block["time"],
            "is_booked": occupied,
            "booked_count": occupied_count,
            "remaining_capacity": max(quota - occupied_count, 0),
            "is_in_clearance": in_clearance,
        })

    return list(buckets_dict.values())


async def has_active_visit(
    db: AsyncSession,
    org_id: UUID,
    patient_id: UUID,
    exclude_id: Optional[UUID] = None,
) -> bool:
    query = select(Appointment.id).where(
        Appointment.org_id == org_id,
        Appointment.patient_id == patient_id,
        cast(Appointment.status, String).in_(
            ["scheduled", "arrived", "in_progress"]
        ),
    )
    if exclude_id:
        query = query.where(Appointment.id != exclude_id)
    return (await db.scalar(query.limit(1))) is not None


async def book_appointment(
    db: AsyncSession, appointment_in: AppointmentCreate
) -> Appointment:
    db_appointment = Appointment(**appointment_in.model_dump())
    db.add(db_appointment)
    await db.commit()
    await db.refresh(db_appointment)
    return db_appointment


async def book_appointment_atomic(
    db: AsyncSession,
    org_id: UUID,
    patient_id: UUID,
    doctor_id: UUID,
    start_time: datetime,
    end_time: datetime,
    chief_complaint: str,
    session_id: Optional[str] = None,
    exclude_appointment_id: Optional[UUID] = None,
    booked_by_type: str = "VOICE_AI",
    booked_by_name: str = "Dispatch AI Voice Assistant",
    verification_status: Optional[str] = None,
) -> Optional[Appointment]:
    tz_name = await get_org_timezone(db, org_id)
    tz = ZoneInfo(tz_name)

    s_time_tz = start_time.replace(tzinfo=tz) if not start_time.tzinfo else start_time.astimezone(tz)
    e_time_tz = end_time.replace(tzinfo=tz) if not end_time.tzinfo else end_time.astimezone(tz)
    org = await db.get(Organization, org_id)
    if not org:
        return None
    if org.consultation_fee is None:
        raise HTTPException(422, "Configure a consultation fee before booking")
    await lock_daily_capacity(db, org_id, s_time_tz.date())
    capacity = await get_future_capacity(db, org, org_id, s_time_tz.date(), format_time_label(s_time_tz.time()), doctor_id=doctor_id, exclude_id=exclude_appointment_id)
    if capacity["availability"] != "AVAILABLE":
        return None

    v_status = verification_status or ("unverified" if booked_by_type == "VOICE_AI" else "verified")
    auto_deadline = (datetime.now(ZoneInfo("UTC")) + timedelta(minutes=30)) if v_status == "unverified" else None

    s_date = s_time_tz.date()
    s_time_fmt = s_time_tz.strftime("%I:%M %p")

    new_appt = Appointment(
        org_id=org_id,
        appointment_timezone=tz_name,
        patient_id=patient_id,
        doctor_id=doctor_id,
        start_time=s_time_tz,
        end_time=e_time_tz,
        status="scheduled",
        chief_complaint=chief_complaint,
        verification_status=v_status,
        auto_confirm_deadline=auto_deadline,
        source="ai_voice" if booked_by_type == "VOICE_AI" else "manual",
        fee=org.consultation_fee,
        payment_status="pending",
        booking_metadata={
            "booked_by_type": booked_by_type,
            "booked_by_name": booked_by_name or "Voice AI Assistant",
            "arrival_time": s_time_fmt,
            "queue_policy": "service_order_is_set_when_the_patient_checks_in",
        },
    )
    db.add(new_appt)
    await db.flush()
    await write_visit_event(
        db=db, visit_id=new_appt.id, org_id=org_id,
        event_type="APPOINTMENT_BOOKED", actor_type="ai_voice" if booked_by_type == "VOICE_AI" else "staff",
        metadata={"start_time": s_time_tz.isoformat()},
    )

    try:
        audit_entry = SystemAuditLog(
            org_id=org_id,
            actor_email=booked_by_name or "voice_ai@system.local",
            action_type="APPOINTMENT_BOOKED",
            target_id=new_appt.id,
            target_name="appointment",
            new_state={
                "start_time": s_time_tz.isoformat(),
                "doctor_id": str(doctor_id),
                "patient_id": str(patient_id),
            },
        )
        db.add(audit_entry)
        await db.flush()
    except Exception as audit_err:
        logger.error(f"[BOOKING AUDIT ERROR] Failed to record system audit log: {audit_err}")

    from app.services.infra.outbox import enqueue_outbox_event
    await enqueue_outbox_event(
        db=db,
        org_id=org_id,
        event_type="APPOINTMENT_CREATED",
        payload={
            "event": "APPOINTMENT_CREATED",
            "appointment_id": str(new_appt.id),
            "org_id": str(org_id),
            "doctor_id": str(doctor_id),
            "patient_id": str(patient_id),
            "verification_status": v_status,
            "auto_confirm_deadline": auto_deadline.isoformat() if auto_deadline else None,
            "start_time": s_time_tz.isoformat(),
            "end_time": e_time_tz.isoformat(),
        },
    )

    invalidate_slot_cache(str(org_id), start_time.strftime("%Y-%m-%d"))

    try:
        from app.services.infra.websocket_manager import ws_manager
        await ws_manager.broadcast_to_org(
            str(org_id),
            {
                "event": "APPOINTMENT_CREATED",
                "appointment_id": str(new_appt.id),
                "org_id": str(org_id),
                "doctor_id": str(doctor_id),
                "patient_id": str(patient_id),
                "verification_status": v_status,
                "auto_confirm_deadline": auto_deadline.isoformat() if auto_deadline else None,
                "start_time": s_time_tz.isoformat(),
                "end_time": e_time_tz.isoformat(),
            },
        )
    except Exception as ws_err:
        logger.warning(f"[WEBSOCKET BROADCAST WARNING] Failed to broadcast appointment: {ws_err}")

    return new_appt


async def cancel_patient_appointment(
    db: AsyncSession, appointment_id: UUID
) -> Optional[Appointment]:
    query = select(Appointment).where(
        Appointment.id == appointment_id
    )
    res = await db.execute(query)
    appt = res.scalar_one_or_none()
    if not appt:
        return None

    appt.status = "cancelled"
    await db.flush()

    invalidate_slot_cache(str(appt.org_id), appt.start_time.strftime("%Y-%m-%d"))
    return appt


async def reschedule_patient_appointment(
    db: AsyncSession,
    org_id: UUID,
    patient_id: UUID,
    old_appointment_id: UUID,
    new_doctor_id: UUID,
    new_start_time: datetime,
    new_end_time: datetime,
    chief_complaint: str,
    session_id: Optional[str] = None,
) -> Optional[Appointment]:
    old = await db.scalar(select(Appointment).where(
        Appointment.id == old_appointment_id,
        Appointment.org_id == org_id,
        Appointment.patient_id == patient_id,
    ).with_for_update())
    if not old or old.status in ("cancelled", "completed"):
        return None
    replacement = await book_appointment_atomic(
        db=db,
        org_id=org_id,
        patient_id=patient_id,
        doctor_id=new_doctor_id,
        start_time=new_start_time,
        end_time=new_end_time,
        chief_complaint=chief_complaint,
        session_id=session_id,
        exclude_appointment_id=old_appointment_id,
    )
    if replacement:
        old.status = "cancelled"
        old.cancellation_reason = "Rescheduled"
        await db.flush()
    return replacement


def _phone_matches_patient(phone: str):
    digits = "".join(character for character in phone if character.isdigit())
    if len(digits) < 10:
        return Patient.phone_number == phone
    stored_digits = func.regexp_replace(Patient.phone_number, "[^0-9]", "", "g")
    local_digits = digits[-10:]
    return or_(
        stored_digits == digits,
        and_(func.length(stored_digits) == 10, stored_digits == local_digits),
        and_(func.length(stored_digits) == 11, stored_digits == f"0{local_digits}"),
    )


async def _resolve_patient(db: AsyncSession, org_id: UUID, req, phone: str) -> Patient:
    if req.patient_id:
        patient = await db.scalar(select(Patient).where(
            Patient.id == req.patient_id, Patient.org_id == org_id,
        ).with_for_update())
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found in this clinic")
        if " ".join(req.patient_name.split()).casefold() != " ".join(f"{patient.first_name} {patient.last_name}".split()).casefold():
            raise HTTPException(409, "Verify the selected patient name")
        return patient

    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"patient-intake:{org_id}:{phone}:{req.patient_name.strip().casefold()}"})
    full_name = " ".join(req.patient_name.split()).casefold()
    candidates = (await db.execute(select(Patient).where(
        Patient.org_id == org_id, _phone_matches_patient(phone),
    ))).scalars().all()
    matches = [patient for patient in candidates if
        " ".join(f"{patient.first_name} {patient.last_name}".split()).casefold() == full_name
        and (req.dob is None or patient.dob is None or patient.dob == req.dob)]
    if len(matches) > 1:
        raise HTTPException(status_code=409, detail="Multiple patient profiles match. Select a patient ID after verification.")
    if matches:
        return matches[0]
    parts = " ".join(req.patient_name.split()).split(" ", 1)
    patient = Patient(
        org_id=org_id, first_name=parts[0],
        last_name=parts[1] if len(parts) > 1 else "",
        phone_number=phone, dob=req.dob,
    )
    db.add(patient)
    await db.flush()
    return patient


async def list_clinic_appointments(db: AsyncSession, org_id: UUID, target_date: Optional[date] = None) -> List[AppointmentResponse]:
    from app.services.appointments.serializers import build_appointment_list_response
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Clinic not found")
    query = select(Appointment).where(Appointment.org_id == org_id)
    if target_date:
        tz = ZoneInfo(require_clinic_timezone(org))
        start = datetime.combine(target_date, time.min, tzinfo=tz)
        query = query.where(Appointment.start_time >= start, Appointment.start_time < start + timedelta(days=1))
    appointments = list((await db.execute(query.order_by(Appointment.created_at))).scalars().all())
    return await build_appointment_list_response(db, appointments, org_id)


async def book_clinic_walkin_appointment(
    db: AsyncSession,
    req: ClinicWalkinBookingRequest,
    org_id: UUID,
) -> AppointmentResponse:
    clinic_org = await db.get(Organization, org_id)
    if not clinic_org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic organization not found",
        )

    clinic_today = datetime.now(
        ZoneInfo(require_clinic_timezone(clinic_org))
    ).date()
    if req.appointment_date != clinic_today:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Walk-in tokens are available for today only.",
        )

    first_name = req.patient_name.strip()
    last_name = ""
    if " " in first_name:
        parts = first_name.split(" ", 1)
        first_name = parts[0]
        last_name = parts[1]

    normalized_phone = normalize_phone_e164(req.patient_phone)
    patient_phone = (
        normalized_phone.e164_phone
        if normalized_phone.is_valid
        else req.patient_phone.strip()
    )
    patient = await _resolve_patient(db, org_id, req, patient_phone)
    if await has_active_visit(db, org_id, patient.id):
        existing = await db.scalar(select(Appointment).where(Appointment.org_id == org_id, Appointment.patient_id == patient.id, Appointment.status.in_(["arrived", "in_progress", "scheduled"])).order_by(Appointment.created_at.desc()).limit(1))
        if existing and existing.status == "arrived" and existing.source == "walk_in" and existing.doctor_id == req.doctor_id:
            from app.services.appointments.serializers import build_single_appointment_response
            return await build_single_appointment_response(db, existing, org_id)
        raise HTTPException(409, "This patient already has an active clinic visit. Check in the existing registration.")
    snapshot = validate_intake(patient, req, clinic_today) if req.is_arrived else None

    doctor_query = select(User).where(
        User.org_id == org_id,
        User.role == "doctor",
        User.is_active == True,
    )
    doc_res = await db.execute(doctor_query)
    doctors = list(doc_res.scalars().all())
    assigned_doctor = next((d for d in doctors if d.id == req.doctor_id), None) if req.doctor_id else (doctors[0] if len(doctors) == 1 else None)
    if not assigned_doctor:
        raise HTTPException(422, "Select an active doctor for check-in")
    doctor_id = assigned_doctor.id if assigned_doctor else None

    assigned_prefix = "W"

    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"clinic-token:{org_id}:{req.appointment_date}:{assigned_prefix}"},
    )
    token_query = select(func.max(Appointment.token_number)).where(
        Appointment.org_id == org_id,
        Appointment.appointment_date == req.appointment_date,
        Appointment.display_token.like(f"{assigned_prefix}-%"),
    )
    max_token_res = await db.execute(token_query)
    max_token = max_token_res.scalar() or 0

    new_token_number = max_token + 1
    display_token = f"{assigned_prefix}-{new_token_number}"

    fee_val = req.fee if req.fee is not None else clinic_org.consultation_fee
    if fee_val is None:
        raise HTTPException(422, "Configure a consultation fee or enter one for this visit")

    tz_str = require_clinic_timezone(clinic_org)
    tz = ZoneInfo(tz_str)
    await lock_daily_capacity(db, org_id, req.appointment_date)
    active_visits = await count_daily_active_visits(
        db, org_id, req.appointment_date, tz,
    )
    max_daily_patients = require_clinic_booking_integer(clinic_org, "max_daily_patients")
    if active_visits >= max_daily_patients:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The clinic has reached its safe capacity for today.",
        )

    current_time = datetime.now(tz)
    safe_start_time = current_time
    duration_mins = require_clinic_booking_integer(clinic_org, "default_slot_duration_minutes")
    safe_end_time = safe_start_time + timedelta(minutes=duration_mins)

    appt = Appointment(
        org_id=org_id,
        appointment_timezone=tz_str,
        patient_id=patient.id,
        doctor_id=doctor_id,
        start_time=safe_start_time,
        end_time=safe_end_time,
        appointment_date=req.appointment_date,
        token_prefix=assigned_prefix,
        token_number=new_token_number,
        display_token=display_token,
        status="arrived" if getattr(req, "is_arrived", True) else "scheduled",
        queue_state="waiting" if getattr(req, "is_arrived", True) else "not_checked_in",
        checked_in_at=(
            datetime.now(ZoneInfo("UTC"))
            if getattr(req, "is_arrived", True)
            else None
        ),
        source="walk_in",
        chief_complaint=req.chief_complaint or None,
        payment_status="pending",
        payment_method=None,
        fee=float(fee_val),
    )
    try:
        if snapshot:
            appt.booking_metadata = {**(appt.booking_metadata or {}), "age_at_check_in": snapshot}
        db.add(appt)
        await db.flush()
        await db.refresh(appt)

        receptionist_membership = await db.scalar(
            select(ClinicMembership)
            .where(
                ClinicMembership.org_id == org_id,
                ClinicMembership.role == "receptionist",
                ClinicMembership.status == "active",
            )
            .order_by(ClinicMembership.created_at.asc())
        )
        if receptionist_membership:
            receptionist_membership.total_walkins_triaged = (
                receptionist_membership.total_walkins_triaged or 0
            ) + 1
            if appt.payment_status == "paid" and (appt.fee or 0) > 0:
                receptionist_membership.total_revenue_collected = (
                    receptionist_membership.total_revenue_collected or 0
                ) + (appt.fee or 0)
            db.add(receptionist_membership)

        if appt.payment_status == "paid" and (appt.fee or 0) > 0:
            receipt = PaymentReceipt(
                org_id=org_id,
                visit_id=appt.id,
                amount=appt.fee,
                status="paid",
                method=appt.payment_method or "cash",
                reference="Walk-in upfront payment",
                received_by=receptionist_membership.user_id if receptionist_membership else None,
            )
            db.add(receipt)
        await write_visit_event(
            db=db,
            visit_id=appt.id,
            org_id=org_id,
            event_type="WALK_IN_REGISTERED",
            notes="Walk-in registration",
            metadata={"token": appt.display_token, "source": "walk_in"},
        )
        if getattr(req, "is_arrived", True):
            await write_visit_event(
                db=db,
                visit_id=appt.id,
                org_id=org_id,
                event_type="CHECKED_IN",
                notes="Checked in upon walk-in registration",
            )
        await db.commit()
        invalidate_slot_cache(str(org_id), req.appointment_date.isoformat())
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Token allocation conflict.",
        )

    is_paid = appt.payment_status == "paid"

    return AppointmentResponse(
        id=appt.id,
        org_id=appt.org_id,
        patient_id=appt.patient_id,
        doctor_id=appt.doctor_id,
        start_time=appt.start_time,
        end_time=appt.end_time,
        status=appt.status,
        chief_complaint=appt.chief_complaint,
        doctor_notes=None,
        booked_by_type="walk_in",
        booked_by_name="Front Desk Reception",
        verification_status="verified",
        created_at=appt.created_at or appt.start_time,
        patient_name=f"{patient.first_name} {patient.last_name}".strip(),
        patient_phone=patient.phone_number,
        dob=patient.dob,
        reported_age=((patient.medical_history or {}).get("reported_age") or {}).get("value"),
        age_unit=((patient.medical_history or {}).get("reported_age") or {}).get("unit"),
        gender=patient.gender,
        blood_group=patient.blood_group,
        address=patient.address,
        doctor_name=(
            assigned_doctor.full_name
            if assigned_doctor
            else clinic_org.lead_doctor_name
        ),
        specialization=(
            assigned_doctor.specialization
            if assigned_doctor
            else clinic_org.clinic_specialty
        ),
        token_number=appt.token_number,
        display_token=appt.display_token,
        token_prefix=appt.token_prefix,
        appointment_date=appt.appointment_date,
        appointment_time=appt.appointment_time,
        payment_status=appt.payment_status,
        fee=appt.fee,
        amount_paid=float(appt.fee or 0.0) if is_paid else 0.0,
        balance_due=0.0 if is_paid else float(appt.fee or 0.0),
        shift_type=appt.shift_type,
        checked_in_at=appt.checked_in_at,
        called_at=appt.called_at,
        queue_state=appt.queue_state,
        encounter_state=appt.encounter_state,
    )


async def book_clinic_scheduled_appointment(
    db: AsyncSession,
    req: ClinicScheduledBookingRequest,
    org_id: UUID,
) -> AppointmentResponse:
    clinic_org = await db.get(Organization, org_id)
    if not clinic_org:
        raise HTTPException(status_code=404, detail="Clinic organization not found")

    clinic_today = datetime.now(
        ZoneInfo(require_clinic_timezone(clinic_org))
    ).date()
    if req.appointment_date < clinic_today:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot book appointments for past dates.",
        )

    doctor_res = await db.execute(
        select(User).where(
            User.org_id == org_id,
            User.role == "doctor",
            User.is_active == True,
            *([User.id == req.doctor_id] if req.doctor_id else []),
        )
    )
    doctor = doctor_res.scalars().first()
    if req.doctor_id and not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found in this clinic")
    if not doctor:
        raise HTTPException(status_code=409, detail="No active doctor is available for scheduled booking")
    tz = ZoneInfo(require_clinic_timezone(clinic_org))
    parsed_time = parse_time_str(req.appointment_time)
    if not parsed_time:
        raise HTTPException(status_code=400, detail="appointment_time must be a valid clinic time.")
    start_time = datetime.combine(req.appointment_date, parsed_time).replace(tzinfo=tz)
    await lock_daily_capacity(db, org_id, req.appointment_date)
    capacity = await get_future_capacity(
        db, clinic_org, org_id, req.appointment_date, req.appointment_time,
        doctor_id=doctor.id if doctor else None,
    )
    if capacity["availability"] != "AVAILABLE":
        err_msg = (
            f"Requested slot is currently within the active morning queue clearance (~{capacity.get('queue_clearance_time')})."
            if capacity.get("reason") == "QUEUE_OVERLAP"
            else "Requested slot capacity is unavailable."
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": err_msg,
                "reason": capacity.get("reason"),
                "next_available": capacity.get("next_available"),
                "queue_clearance_time": capacity.get("queue_clearance_time"),
            },
        )

    normalized_phone = normalize_phone_e164(req.patient_phone)
    patient_phone = (
        normalized_phone.e164_phone
        if normalized_phone.is_valid
        else req.patient_phone.strip()
    )
    patient = await _resolve_patient(db, org_id, req, patient_phone)
    if await has_active_visit(db, org_id, patient.id):
        raise HTTPException(
            status_code=409, detail="This patient already has an active clinic visit."
        )

    if req.reported_age is not None or req.dob:
        validate_intake(patient, req, clinic_today)

    if req.previous_visit_id:
        previous = await db.get(Appointment, req.previous_visit_id)
        if not previous or previous.org_id != org_id or previous.patient_id != patient.id or previous.status != "completed":
            raise HTTPException(422, "Follow-up must link to this patient's completed visit")

    visit_fee = req.fee if req.fee is not None else clinic_org.consultation_fee
    if visit_fee is None:
        raise HTTPException(422, "Configure a consultation fee or enter one for this visit")
    appointment = Appointment(
        id=uuid4(),
        org_id=org_id,
        appointment_timezone=require_clinic_timezone(clinic_org),
        patient_id=patient.id,
        doctor_id=doctor.id if doctor else None,
        start_time=start_time,
        end_time=start_time + timedelta(minutes=int(require_clinic_booking_integer(clinic_org, "default_slot_duration_minutes"))),
        status="scheduled",
        token_number=None,
        token_prefix=None,
        display_token=None,
        source="manual",
        chief_complaint=req.chief_complaint or None,
        payment_status="pending",
        fee=float(visit_fee),
        created_at=datetime.now(timezone.utc),
    )
    appointment.booking_metadata = {
        **(appointment.booking_metadata or {}),
        "arrival_time": appointment.appointment_time,
        "queue_policy": "service_order_is_set_when_the_patient_checks_in",
    }
    if req.previous_visit_id:
        appointment.booking_metadata = {**appointment.booking_metadata, "previous_visit_id": str(req.previous_visit_id), "link_reason": "report_review"}
    db.add(appointment)
    try:
        await db.flush()
        await db.refresh(appointment)
        await write_visit_event(
            db=db,
            visit_id=appointment.id,
            org_id=org_id,
            event_type="APPOINTMENT_BOOKED",
            notes=f"Booked for {appointment.appointment_date} at {appointment.appointment_time}",
            metadata={"source": "scheduled_booking", "fee": appointment.fee},
        )
        await db.commit()
        invalidate_slot_cache(str(org_id), req.appointment_date.isoformat())
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Appointment slot booking conflict")

    return AppointmentResponse(
        id=appointment.id,
        org_id=appointment.org_id,
        patient_id=appointment.patient_id,
        doctor_id=appointment.doctor_id,
        start_time=appointment.start_time,
        end_time=appointment.end_time,
        appointment_date=appointment.appointment_date,
        appointment_time=appointment.appointment_time,
        status=appointment.status,
        chief_complaint=appointment.chief_complaint,
        created_at=appointment.created_at,
        patient_name=f"{patient.first_name} {patient.last_name}".strip(),
        patient_phone=patient.phone_number,
        dob=patient.dob,
        reported_age=((patient.medical_history or {}).get("reported_age") or {}).get("value"),
        age_unit=((patient.medical_history or {}).get("reported_age") or {}).get("unit"),
        gender=patient.gender,
        blood_group=patient.blood_group,
        address=patient.address,
        doctor_name=doctor.full_name if doctor else clinic_org.lead_doctor_name,
        specialization=doctor.specialization if doctor else clinic_org.clinic_specialty,
        payment_status=appointment.payment_status,
        fee=appointment.fee,
        previous_visit_id=(appointment.booking_metadata or {}).get("previous_visit_id"),
    )
