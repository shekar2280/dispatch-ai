from app.core.clinic_config import require_clinic_booking_integer
from app.core.clinic_config import require_clinic_timezone
from datetime import date, datetime, timedelta, time
from enum import Enum
import zoneinfo
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, text

from app.models.organization import Organization
from app.models.appointment import Appointment
from app.schemas.appointment import AppointmentResponse
from app.services.appointments.encounter_service import write_visit_event
from app.services.appointments.schedule_service import (
    get_effective_weekly_schedule,
    parse_time_str,
    format_time_label,
)
from app.services.appointments.serializers import build_appointment_list_response


def parse_time_to_minutes(time_str: Optional[str]) -> Optional[int]:
    if not time_str:
        return None
    try:
        dt = datetime.strptime(time_str.strip(), "%I:%M %p")
        return dt.hour * 60 + dt.minute
    except ValueError:
        return None


async def get_ordered_active_queue(
    db: AsyncSession,
    org_id: UUID,
    clinic_tz: Optional[str] = None,
    priority_window_minutes: Optional[int] = None,
    doctor_id: Optional[UUID] = None,
) -> List[Appointment]:
    org = await db.get(Organization, org_id)
    resolved_tz_name = clinic_tz or require_clinic_timezone(org)
    tz = zoneinfo.ZoneInfo(resolved_tz_name)

    now_clinic = datetime.now(tz)
    today = now_clinic.date()

    result = await db.execute(
        select(Appointment)
        .where(
            Appointment.org_id == org_id,
            Appointment.doctor_id == doctor_id if doctor_id else Appointment.org_id == org_id,
            Appointment.start_time >= datetime.combine(today, datetime.min.time(), tzinfo=tz),
            Appointment.start_time < datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=tz),
            Appointment.status.in_(["arrived", "skipped"]),
            Appointment.queue_state.in_(["waiting", "called", "stepped_out"]),
        )
    )
    appointments = list(result.scalars().all())

    appointments.sort(key=lambda appt: (
        appt.status == "skipped",
        appt.queue_state != "called",
        not bool((appt.booking_metadata or {}).get("urgent_reason")),
        (appt.checked_in_at or appt.created_at or now_clinic).timestamp(),
        appt.token_number or 0,
        str(appt.id),
    ))
    return appointments


class ClinicReconciliationAction(str, Enum):
    ROLLOVER_MORNING = "rollover_morning"
    ROLLOVER_SAME_TIME = "rollover_same_time"
    CUSTOM_TIME = "custom_time"
    CANCEL = "cancel"


class ClinicReconciliationItem(BaseModel):
    appointment_id: UUID
    action: ClinicReconciliationAction
    target_date: Optional[date] = None
    target_time: Optional[str] = None
    patient_confirmed: bool = False


class ClinicBatchReconciliationRequest(BaseModel):
    actions: List[ClinicReconciliationItem]


async def get_clinic_queue(
    db: AsyncSession,
    org_id: UUID,
    doctor_id: Optional[UUID] = None,
) -> List[AppointmentResponse]:
    ordered_appointments = await get_ordered_active_queue(db=db, org_id=org_id, doctor_id=doctor_id)
    if not ordered_appointments:
        return []
    return await build_appointment_list_response(db, ordered_appointments, org_id)


async def rollover_clinic_queue(
    db: AsyncSession,
    org_id: UUID,
):
    raise HTTPException(
        status_code=409,
        detail="Review each patient in End of Day Wrap-Up and record confirmation before rollover.",
    )


async def batch_reconcile_clinic_queue(
    db: AsyncSession,
    org_id: UUID,
    payload: ClinicBatchReconciliationRequest,
    actor_id: Optional[UUID] = None,
):
    clinic_org = await db.get(Organization, org_id)
    if not clinic_org:
        raise HTTPException(status_code=404, detail="Clinic organization not found")

    tz = zoneinfo.ZoneInfo(require_clinic_timezone(clinic_org))
    today = datetime.now(tz).date()
    tomorrow = today + timedelta(days=1)

    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"clinic-batch-reconcile:{org_id}:{tomorrow}"},
    )

    existing = await db.execute(
        select(func.max(Appointment.token_number)).where(
            Appointment.org_id == org_id,
            Appointment.appointment_date == tomorrow,
            Appointment.display_token.like("R-%"),
        )
    )
    next_token = (existing.scalar() or 0) + 1

    schedule = get_effective_weekly_schedule(clinic_org.weekly_schedule)
    tomorrow_day = tomorrow.strftime("%A").lower()
    day_cfg = schedule.get(tomorrow_day, {})
    m_start_str = day_cfg.get("morningStart", "10:00 AM")
    opening_time = parse_time_str(m_start_str) or time(10, 0)
    slot_duration = require_clinic_booking_integer(clinic_org, "default_slot_duration_minutes")

    morning_offset_minutes = 0
    rolled_over_count = 0
    cancelled_count = 0

    for item in payload.actions:
        appointment = await db.scalar(
            select(Appointment).where(
                Appointment.id == item.appointment_id,
                Appointment.org_id == org_id,
            ).with_for_update()
        )
        if not appointment:
            raise HTTPException(status_code=404, detail=f"Appointment {item.appointment_id} not found")

        if item.action == ClinicReconciliationAction.CANCEL:
            if appointment.status not in ("scheduled", "arrived", "skipped") or appointment.appointment_date != today:
                raise HTTPException(status_code=409, detail="Only today's unserved visits may be cancelled")
            appointment.status = "cancelled"
            appointment.queue_state = "not_checked_in"
            appointment.cancellation_reason = "Cancelled at End of Day reconciliation"
            await write_visit_event(
                db=db, visit_id=appointment.id, org_id=org_id, actor_id=actor_id,
                event_type="CANCELLED", notes=appointment.cancellation_reason,
            )
            cancelled_count += 1
            continue

        if not item.patient_confirmed:
            raise HTTPException(status_code=422, detail=f"Patient confirmation required for {appointment.id}")

        target_date = item.target_date or tomorrow
        if target_date <= today:
            raise HTTPException(status_code=422, detail="Rollover must target a future clinic day")

        if item.action == ClinicReconciliationAction.ROLLOVER_MORNING:
            start_dt = datetime.combine(
                target_date, opening_time, tzinfo=tz
            ) + timedelta(minutes=morning_offset_minutes)
            chosen_time_label = format_time_label(start_dt.time())
            morning_offset_minutes += slot_duration
        elif item.action == ClinicReconciliationAction.ROLLOVER_SAME_TIME:
            existing_time_str = appointment.appointment_time
            parsed_time = (
                parse_time_str(existing_time_str)
                if existing_time_str
                else opening_time
            ) or opening_time
            start_dt = datetime.combine(target_date, parsed_time, tzinfo=tz)
            chosen_time_label = format_time_label(start_dt.time())
        elif item.action == ClinicReconciliationAction.CUSTOM_TIME:
            custom_time_str = item.target_time or "10:00 AM"
            parsed_time = parse_time_str(custom_time_str) or opening_time
            start_dt = datetime.combine(target_date, parsed_time, tzinfo=tz)
            chosen_time_label = format_time_label(start_dt.time())
        else:
            continue

        if appointment.status not in ("scheduled", "arrived", "skipped") or appointment.appointment_date != today:
            raise HTTPException(status_code=409, detail="Only today's unserved visits may roll over")
        from app.services.appointments.booking_service import (
            get_future_capacity,
            lock_capacity_window,
            count_window_bookings,
        )
        capacity = await get_future_capacity(
            db, clinic_org, org_id, target_date, chosen_time_label,
            doctor_id=appointment.doctor_id, exclude_id=appointment.id,
        )
        if capacity["availability"] != "AVAILABLE":
            raise HTTPException(status_code=409, detail=f"No capacity for {chosen_time_label} on {target_date}")
        window_minutes = int((clinic_org.booking_settings or {}).get("window_duration_minutes", 30))
        window_start, window_end = await lock_capacity_window(
            db, org_id, appointment.doctor_id, start_dt, window_minutes,
        )
        occupied = await count_window_bookings(
            db, org_id, appointment.doctor_id, window_start, window_end,
            exclude_id=appointment.id,
        )
        quota = int((clinic_org.booking_settings or {}).get("booking_quota_per_window", 2))
        if occupied >= quota:
            raise HTTPException(status_code=409, detail=f"No capacity for {chosen_time_label} on {target_date}")
        replacement = Appointment(
            org_id=org_id, patient_id=appointment.patient_id, doctor_id=appointment.doctor_id,
            appointment_timezone=require_clinic_timezone(clinic_org),
            start_time=start_dt, end_time=start_dt + timedelta(minutes=slot_duration),
            source="manual", status="scheduled", queue_state="not_checked_in",
            booking_metadata={"previous_visit_id": str(appointment.id), "link_reason": "unserved_rebooking"},
        )
        if clinic_org.consultation_fee is None:
            raise HTTPException(422, "Configure a consultation fee before rebooking")
        replacement.fee = clinic_org.consultation_fee
        replacement.payment_status = "pending"
        db.add(replacement)
        appointment.status = "cancelled"
        appointment.queue_state = "not_checked_in"
        appointment.cancellation_reason = "Unserved; rebooked with patient consent"
        await db.flush()

        await write_visit_event(
            db=db,
            visit_id=appointment.id,
            org_id=org_id,
            actor_id=actor_id,
            event_type="ROLLOVER",
            notes=f"Reconciled and rolled over to {target_date} {chosen_time_label} as {appointment.display_token}",
            metadata={
                "new_date": str(target_date),
                "new_time": chosen_time_label,
                "replacement_visit_id": str(replacement.id),
                "reconciliation_action": item.action.value,
                "patient_confirmed": item.patient_confirmed,
            },
        )
        next_token += 1
        rolled_over_count += 1

    await db.commit()
    return {
        "status": "success",
        "rolled_over_count": rolled_over_count,
        "cancelled_count": cancelled_count,
    }


async def execute_end_of_day_action(
    db: AsyncSession,
    org_id: UUID,
    payload: dict,
):
    if payload.get("action") != "cancel":
        raise HTTPException(
            status_code=409,
            detail="Use End of Day Wrap-Up with a confirmed patient and validated slot.",
        )
    appointment_id = payload.get("appointment_id")
    action = payload.get("action")
    if not appointment_id or not action:
        raise HTTPException(
            status_code=400, detail="appointment_id and action are required."
        )

    appointment = await db.scalar(
        select(Appointment).where(
            Appointment.id == UUID(str(appointment_id)),
            Appointment.org_id == org_id,
        )
    )
    if not appointment:
        raise HTTPException(status_code=404, detail="Clinic appointment not found")

    clinic_org = await db.get(Organization, org_id)
    tz = zoneinfo.ZoneInfo(
        require_clinic_timezone(clinic_org)
    )
    today = datetime.now(tz).date()
    if appointment.appointment_date != today or appointment.status not in (
        "scheduled",
        "arrived",
        "skipped",
    ):
        raise HTTPException(
            status_code=400, detail="Only active tokens from today can be closed out."
        )

    if action == "cancel":
        appointment.status = "cancelled"
    await db.commit()
    return {
        "status": "success",
        "action": action,
        "appointment_id": str(appointment.id),
        "payment_status": appointment.payment_status,
    }


async def expire_rollover_priority(
    db: AsyncSession,
    org_id: UUID,
):
    clinic_org = await db.get(Organization, org_id)
    if not clinic_org:
        raise HTTPException(status_code=404, detail="Clinic organization not found")
    tz = zoneinfo.ZoneInfo(require_clinic_timezone(clinic_org))
    now = datetime.now(tz)
    today = now.date()
    schedule = clinic_org.weekly_schedule or {}
    opening = schedule.get(today.strftime("%A").lower(), {}).get(
        "morningStart", "09:00 AM"
    )
    try:
        opening_time = datetime.strptime(opening, "%I:%M %p").time()
    except ValueError:
        opening_time = datetime.strptime("09:00 AM", "%I:%M %p").time()
    if now < datetime.combine(today, opening_time, tzinfo=tz) + timedelta(minutes=90):
        raise HTTPException(
            status_code=400,
            detail="Rollover priority expires 90 minutes after opening.",
        )

    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"clinic-expire-rollover:{org_id}:{today}"},
    )
    result = await db.execute(
        select(Appointment)
        .where(
            Appointment.org_id == org_id,
            Appointment.appointment_date == today,
            Appointment.display_token.like("R-%"),
            Appointment.status.in_(["scheduled", "arrived"]),
        )
        .order_by(Appointment.token_number.asc())
    )
    rollovers = list(result.scalars().all())
    max_token = (
        await db.scalar(
            select(func.max(Appointment.token_number)).where(
                Appointment.org_id == org_id,
                Appointment.appointment_date == today,
                Appointment.display_token.like("T-%"),
            )
        )
        or 0
    )
    for index, appointment in enumerate(rollovers, start=1):
        token_number = max_token + index
        appointment.token_prefix = "T"
        appointment.token_number = token_number
        appointment.display_token = f"T-{token_number}"
    await db.commit()
    return {"status": "success", "expired_count": len(rollovers)}
