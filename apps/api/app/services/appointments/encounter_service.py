from app.core.clinic_config import require_clinic_booking_integer
from app.core.clinic_config import require_clinic_timezone
from datetime import date, datetime, timedelta, time
import zoneinfo
from typing import List, Optional, Dict, Any
import uuid
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, text

from app.models.organization import Organization
from app.models.appointment import Appointment
from app.models.visit_event import VisitEvent
from app.models.patient import Patient
from app.models.payment_receipt import PaymentReceipt
from app.models.user import User
from app.models.clinic_membership import ClinicMembership
from app.schemas.appointment import (
    AppointmentResponse,
    AppointmentStatusUpdate,
    ClinicCheckInRequest,
    ClinicRescheduleRequest,
    VisitEventResponse,
)
from app.services.appointments.intake import validate_intake
from app.services.appointments.schedule_service import parse_time_str
from app.services.appointments.serializers import build_single_appointment_response
from app.services.infra.audit import write_audit_event
from app.services.infra.outbox import enqueue_outbox_event
from app.services.infra.redis_cache import invalidate_slot_cache


async def write_visit_event(
    db: AsyncSession,
    visit_id: UUID,
    org_id: UUID,
    event_type: str,
    actor_id: Optional[UUID] = None,
    actor_type: str = "staff",
    notes: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> VisitEvent:
    event = VisitEvent(
        visit_id=visit_id,
        org_id=org_id,
        event_type=event_type,
        actor_id=actor_id,
        actor_type=actor_type,
        notes=notes,
        event_metadata=metadata or {},
    )
    db.add(event)
    await db.flush()
    await write_audit_event(
        db, org_id=org_id, actor_id=actor_id,
        action_type=f"APPOINTMENT_{event_type}", target_id=visit_id,
        target_name="appointment", metadata=metadata or {},
    )
    return event


async def update_appointment_status(
    db: AsyncSession,
    appointment_id: UUID,
    status_update: AppointmentStatusUpdate,
    org_id: UUID,
) -> AppointmentResponse:
    clinic_appt = await db.scalar(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.org_id == org_id,
        ).with_for_update()
    )
    if not clinic_appt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Clinic appointment not found"
        )

    allowed = {
        "scheduled": {"arrived", "cancelled", "no_show"},
        "arrived": {"in_progress", "skipped", "cancelled", "no_show"},
        "skipped": {"arrived", "cancelled"},
        "in_progress": {"completed"},
        "completed": {"in_progress"},
        "cancelled": set(),
        "no_show": set(),
    }
    current = str(clinic_appt.status)
    target = status_update.status
    if target != current and target not in allowed.get(current, set()):
        raise HTTPException(status_code=409, detail=f"Cannot change appointment from {current} to {target}")
    if target == "arrived" and current == "skipped":
        return await reinsert_skipped_patient(db, appointment_id, org_id)
    if target == "arrived" and current in {"scheduled", "arrived"}:
        return await mark_appointment_arrived(db, appointment_id, ClinicCheckInRequest(), org_id)
    now_utc = datetime.now(zoneinfo.ZoneInfo("UTC"))
    reopening = current == "completed" and target == "in_progress"
    if reopening:
        ended = clinic_appt.consultation_ended_at
        if not ended or now_utc - ended > timedelta(minutes=5):
            raise HTTPException(status_code=409, detail="Reopening is available for five minutes after completion")
    if target == "in_progress":
        await lock_doctor_chamber(db, clinic_appt)
    if target == current and target == "completed":
        return await build_single_appointment_response(db, clinic_appt, org_id)

    if reopening:
        old_duration = clinic_appt.actual_duration_seconds or 0
        membership = await db.scalar(select(ClinicMembership).where(
            ClinicMembership.org_id == org_id,
            ClinicMembership.user_id == clinic_appt.doctor_id,
        ))
        if membership:
            membership.total_consultations = max((membership.total_consultations or 0) - 1, 0)
            membership.total_minutes_worked = max(
                (membership.total_minutes_worked or 0) - max(int(round(old_duration / 60)), 1), 0,
            )
        clinic_appt.consultation_ended_at = None
        clinic_appt.actual_duration_seconds = None
        clinic_appt.encounter_state = "in_progress"
        clinic_appt.queue_state = "served"
    if (
        status_update.status == "in_progress"
        and not clinic_appt.consultation_started_at
    ):
        clinic_appt.consultation_started_at = now_utc
        clinic_appt.encounter_state = "in_progress"
        clinic_appt.queue_state = "served"
    elif status_update.status == "completed":
        if not clinic_appt.consultation_started_at:
            if clinic_appt.status == "in_progress":
                clinic_appt.consultation_started_at = clinic_appt.start_time or now_utc
            else:
                raise HTTPException(status_code=409, detail="Start consultation before completing it")
        clinic_appt.consultation_ended_at = now_utc
        clinic_appt.encounter_state = "completed"
        clinic_appt.queue_state = "served"
        if clinic_appt.consultation_started_at:
            elapsed = int(
                (now_utc - clinic_appt.consultation_started_at).total_seconds()
            )
            clinic_appt.actual_duration_seconds = max(elapsed, 0)
        await record_consultation_completion_metrics(
            db, org_id, clinic_appt.doctor_id, clinic_appt.actual_duration_seconds
        )

    clinic_appt.status = status_update.status
    if target == "arrived":
        clinic_appt.queue_state = "waiting"
        if not clinic_appt.checked_in_at:
            clinic_appt.checked_in_at = now_utc
    elif target == "skipped":
        clinic_appt.queue_state = "stepped_out"
    elif target in ("cancelled", "no_show"):
        clinic_appt.queue_state = "not_checked_in"
    if status_update.chief_complaint is not None:
        clinic_appt.chief_complaint = status_update.chief_complaint
    if status_update.doctor_notes is not None:
        clinic_appt.doctor_notes = status_update.doctor_notes

    if status_update.status == "arrived" and clinic_appt.token_number is None:
        clinic_org = await db.get(Organization, org_id)
        tz = zoneinfo.ZoneInfo(
            require_clinic_timezone(clinic_org)
        )
        today = datetime.now(tz).date()
        target_date = clinic_appt.start_time.astimezone(tz).date()
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": f"clinic-arrive-token:{org_id}:{target_date}"},
        )
        max_token = await db.scalar(
            select(func.max(Appointment.token_number)).where(
                Appointment.org_id == org_id,
                Appointment.appointment_date == target_date,
                Appointment.display_token.like("T-%"),
            )
        )
        next_token = (max_token or 0) + 1
        clinic_appt.token_prefix = "T"
        clinic_appt.token_number = next_token
        clinic_appt.display_token = f"T-{next_token}"

    status_event_map = {
        "cancelled": "CANCELLED",
        "arrived": "CHECKED_IN",
        "in_progress": "CONSULTATION_STARTED",
        "completed": "CONSULTATION_ENDED",
        "skipped": "SKIPPED",
        "no_show": "NO_SHOW",
    }
    event_type = "CONSULTATION_REOPENED" if reopening else (status_event_map.get(status_update.status) if target != current else None)
    if event_type:
        await write_visit_event(
            db=db,
            visit_id=clinic_appt.id,
            org_id=org_id,
            event_type=event_type,
            notes="Appointment state changed",
        )
    await db.commit()
    await db.refresh(clinic_appt)

    return await build_single_appointment_response(db, clinic_appt, org_id)


async def mark_appointment_arrived(
    db: AsyncSession,
    appointment_id: UUID,
    req: Optional[ClinicCheckInRequest],
    org_id: UUID,
    actor_id: Optional[UUID] = None,
) -> AppointmentResponse:
    clinic_appt = await db.scalar(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.org_id == org_id,
        ).with_for_update()
    )
    if not clinic_appt:
        raise HTTPException(status_code=404, detail="Clinic appointment not found")
    if clinic_appt.status not in ("scheduled", "arrived"):
        raise HTTPException(status_code=409, detail="Only a scheduled appointment may check in")

    clinic_org = await db.get(Organization, org_id)
    tz = zoneinfo.ZoneInfo(
        require_clinic_timezone(clinic_org)
    )
    today = datetime.now(tz).date()
    target_date = clinic_appt.start_time.astimezone(tz).date()
    if target_date != today:
        raise HTTPException(
            status_code=400,
            detail=f"Patient check-in is only permitted on the scheduled appointment date ({target_date.strftime('%d %b %Y')}).",
        )

    if clinic_appt.checked_in_at and clinic_appt.status == "arrived":
        return await build_single_appointment_response(db, clinic_appt, org_id)
    patient = await db.get(Patient, clinic_appt.patient_id)
    if not patient or patient.org_id != org_id:
        raise HTTPException(404, "Patient not found")
    req = req or ClinicCheckInRequest()
    previous_patient_name = " ".join(f"{patient.first_name} {patient.last_name}".split())
    if req.doctor_id:
        doctor = await db.get(User, req.doctor_id)
        if not doctor or doctor.org_id != org_id or doctor.role != "doctor" or not doctor.is_active:
            raise HTTPException(422, "Select an active clinic doctor")
        clinic_appt.doctor_id = doctor.id
    if not clinic_appt.doctor_id:
        raise HTTPException(422, "Select a doctor at check-in")
    snapshot = validate_intake(patient, req, today)
    verified_patient_name = " ".join(f"{patient.first_name} {patient.last_name}".split())
    clinic_appt.booking_metadata = {**(clinic_appt.booking_metadata or {}), "age_at_check_in": snapshot}
    if req.chief_complaint:
        clinic_appt.chief_complaint = req.chief_complaint

    clinic_appt.status = "arrived"
    clinic_appt.queue_state = "waiting"
    if not clinic_appt.checked_in_at:
        clinic_appt.checked_in_at = datetime.now(zoneinfo.ZoneInfo("UTC"))
    if clinic_appt.token_number is None:
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": f"clinic-arrive-token:{org_id}:{target_date}"},
        )
        max_token = await db.scalar(
            select(func.max(Appointment.token_number)).where(
                Appointment.org_id == org_id,
                Appointment.appointment_date == target_date,
                Appointment.display_token.like("T-%"),
            )
        )
        next_token = (max_token or 0) + 1
        clinic_appt.token_prefix = "T"
        clinic_appt.token_number = next_token
        clinic_appt.display_token = f"T-{next_token}"

    await db.flush()
    await db.refresh(clinic_appt)
    await write_visit_event(
        db=db,
        visit_id=clinic_appt.id,
        org_id=org_id,
        event_type="CHECKED_IN",
        notes="Patient arrived and verified at clinic",
        metadata={
            "token": clinic_appt.display_token,
            "patient_name_corrected": previous_patient_name != verified_patient_name,
            "previous_patient_name": previous_patient_name,
            "verified_patient_name": verified_patient_name,
        },
    )
    await db.commit()
    return await build_single_appointment_response(db, clinic_appt, org_id)


async def call_appointment_patient(
    db: AsyncSession,
    appointment_id: UUID,
    org_id: UUID,
) -> AppointmentResponse:
    clinic_appt = await db.scalar(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.org_id == org_id,
        ).with_for_update()
    )
    if not clinic_appt:
        raise HTTPException(status_code=404, detail="Clinic appointment not found")
    if clinic_appt.status != "arrived":
        raise HTTPException(status_code=409, detail="Check in the patient before calling")
    await lock_doctor_chamber(db, clinic_appt)
    clinic_appt.queue_state = "called"
    clinic_appt.called_at = datetime.now(zoneinfo.ZoneInfo("UTC"))
    clinic_appt.call_count = (clinic_appt.call_count or 0) + 1
    await db.flush()
    await db.refresh(clinic_appt)
    await write_visit_event(
        db=db,
        visit_id=clinic_appt.id,
        org_id=org_id,
        event_type="CALLED_IN",
        notes=f"Patient called into chamber (attempt {clinic_appt.call_count})",
        metadata={"call_count": clinic_appt.call_count},
    )
    await db.commit()
    return await build_single_appointment_response(db, clinic_appt, org_id)


async def lock_doctor_chamber(db, appointment):
    if not appointment.doctor_id:
        raise HTTPException(409, "Assign a doctor before starting consultation")
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                     {"key": f"chamber:{appointment.org_id}:{appointment.doctor_id}"})
    active = await db.scalar(select(Appointment.id).where(
        Appointment.org_id == appointment.org_id,
        Appointment.doctor_id == appointment.doctor_id,
        Appointment.status == "in_progress",
        Appointment.id != appointment.id,
    ))
    if active:
        raise HTTPException(409, "This doctor already has an active consultation")
    if appointment.status == "arrived":
        from app.services.appointments.queue_service import get_ordered_active_queue
        queue = await get_ordered_active_queue(db, appointment.org_id, doctor_id=appointment.doctor_id)
        eligible = [a for a in queue if a.status == "arrived"]
        if eligible and eligible[0].id != appointment.id:
            raise HTTPException(409, "Call the next checked-in patient first, or record a staff-confirmed urgency override")


async def start_consultation(db: AsyncSession, appointment_id: UUID, org_id: UUID) -> AppointmentResponse:
    return await update_appointment_status(db, appointment_id, AppointmentStatusUpdate(status="in_progress"), org_id)


async def record_consultation_completion_metrics(
    db: AsyncSession,
    org_id: UUID,
    doctor_id: Optional[UUID],
    duration_seconds: Optional[int],
) -> None:
    membership = None
    if doctor_id:
        membership = await db.scalar(
            select(ClinicMembership).where(
                ClinicMembership.org_id == org_id,
                ClinicMembership.user_id == doctor_id,
            )
        )
    if not membership:
        membership = await db.scalar(
            select(ClinicMembership)
            .where(
                ClinicMembership.org_id == org_id,
                ClinicMembership.role.in_(["admin", "doctor"]),
                ClinicMembership.status == "active",
            )
            .order_by(ClinicMembership.created_at.asc())
        )
    if membership:
        minutes = max(int(round((duration_seconds or 0) / 60)), 1)
        membership.total_consultations = (membership.total_consultations or 0) + 1
        membership.total_minutes_worked = (membership.total_minutes_worked or 0) + minutes
        db.add(membership)


async def complete_consultation(
    db: AsyncSession,
    appointment_id: UUID,
    org_id: UUID,
) -> AppointmentResponse:
    clinic_appt = await db.scalar(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.org_id == org_id,
        ).with_for_update()
    )
    if not clinic_appt:
        raise HTTPException(status_code=404, detail="Clinic appointment not found")
    if clinic_appt.status == "completed":
        return await build_single_appointment_response(db, clinic_appt, org_id)
    if clinic_appt.status != "in_progress":
        raise HTTPException(status_code=409, detail="Start consultation before completing it")
    now_utc = datetime.now(zoneinfo.ZoneInfo("UTC"))
    if not clinic_appt.consultation_started_at:
        clinic_appt.consultation_started_at = clinic_appt.start_time or now_utc
    clinic_appt.status = "completed"
    clinic_appt.encounter_state = "completed"
    clinic_appt.queue_state = "served"
    clinic_appt.consultation_ended_at = now_utc
    if clinic_appt.consultation_started_at:
        elapsed = int((now_utc - clinic_appt.consultation_started_at).total_seconds())
        clinic_appt.actual_duration_seconds = max(elapsed, 0)
    await record_consultation_completion_metrics(
        db, org_id, clinic_appt.doctor_id, clinic_appt.actual_duration_seconds
    )
    await db.flush()
    await db.refresh(clinic_appt)
    await write_visit_event(
        db=db,
        visit_id=clinic_appt.id,
        org_id=org_id,
        event_type="CONSULTATION_ENDED",
        notes="Consultation finalized",
        metadata={"duration_seconds": clinic_appt.actual_duration_seconds},
    )
    await db.commit()
    return await build_single_appointment_response(db, clinic_appt, org_id)


async def skip_appointment_patient(
    db: AsyncSession,
    appointment_id: UUID,
    org_id: UUID,
) -> AppointmentResponse:
    clinic_appt = await db.scalar(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.org_id == org_id,
        ).with_for_update()
    )
    if not clinic_appt:
        raise HTTPException(status_code=404, detail="Clinic appointment not found")
    if clinic_appt.status != "arrived":
        raise HTTPException(status_code=409, detail="Only a waiting or called patient may step out")
    clinic_appt.status = "skipped"
    clinic_appt.queue_state = "stepped_out"
    await db.flush()
    await db.refresh(clinic_appt)
    await write_visit_event(
        db=db,
        visit_id=clinic_appt.id,
        org_id=org_id,
        event_type="SKIPPED",
        notes="Patient stepped out / skipped in queue",
    )
    await db.commit()
    return await build_single_appointment_response(db, clinic_appt, org_id)


async def reinsert_skipped_patient(
    db: AsyncSession,
    appointment_id: UUID,
    org_id: UUID,
) -> AppointmentResponse:
    clinic_appt = await db.scalar(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.org_id == org_id,
        ).with_for_update()
    )
    if not clinic_appt:
        raise HTTPException(status_code=404, detail="Clinic appointment not found")
    if clinic_appt.status == "completed":
        return await update_appointment_status(db, appointment_id, AppointmentStatusUpdate(status="in_progress"), org_id)
    if clinic_appt.status != "skipped":
        raise HTTPException(status_code=409, detail="Only a stepped-out patient may rejoin the queue")
    clinic_appt.status = "arrived"
    clinic_appt.queue_state = "waiting"
    clinic_appt.checked_in_at = datetime.now(zoneinfo.ZoneInfo("UTC"))
    await db.flush()
    await db.refresh(clinic_appt)
    await write_visit_event(
        db=db,
        visit_id=clinic_appt.id,
        org_id=org_id,
        event_type="REINSERTED",
        notes="Patient re-entered waiting queue at the current queue position",
    )
    await db.commit()
    return await build_single_appointment_response(db, clinic_appt, org_id)


async def move_appointment_to_tomorrow(
    db: AsyncSession,
    appointment_id: UUID,
    org_id: UUID,
) -> AppointmentResponse:
    raise HTTPException(
        status_code=409,
        detail="Use End of Day Wrap-Up to select a valid slot and record patient confirmation.",
    )


async def mark_clinic_late_arrival(db: AsyncSession, appointment_id: UUID, org_id: UUID):
    return await mark_appointment_arrived(db, appointment_id, ClinicCheckInRequest(), org_id)


async def reschedule_clinic_appointment(
    db: AsyncSession,
    appointment_id: UUID,
    req: ClinicRescheduleRequest,
    org_id: UUID,
) -> AppointmentResponse:
    clinic_appt = await db.scalar(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.org_id == org_id,
        ).with_for_update()
    )
    if not clinic_appt:
        raise HTTPException(status_code=404, detail="Clinic appointment not found")
    if clinic_appt.status != "scheduled":
        raise HTTPException(status_code=409, detail="This appointment cannot be rescheduled")
    clinic_org = await db.get(Organization, org_id)
    if not clinic_org:
        raise HTTPException(status_code=404, detail="Clinic organization not found")

    clinic_today = datetime.now(
        zoneinfo.ZoneInfo(require_clinic_timezone(clinic_org))
    ).date()
    if req.new_date < clinic_today:
        raise HTTPException(status_code=400, detail="Cannot reschedule to a past date.")

    tz = zoneinfo.ZoneInfo(require_clinic_timezone(clinic_org))
    old_date = clinic_appt.start_time.astimezone(tz).date()
    parsed_time = parse_time_str(req.new_time)
    if not parsed_time:
        raise HTTPException(status_code=400, detail="Invalid new_time specified.")
    new_start = datetime.combine(req.new_date, parsed_time).replace(tzinfo=tz)
    from app.services.appointments.booking_service import (
        get_future_capacity,
        lock_daily_capacity,
    )
    await lock_daily_capacity(db, org_id, req.new_date)
    capacity = await get_future_capacity(
        db, clinic_org, org_id, req.new_date, req.new_time,
        doctor_id=clinic_appt.doctor_id, exclude_id=clinic_appt.id,
    )
    if capacity["availability"] != "AVAILABLE":
        raise HTTPException(
            status_code=409,
            detail={
                "message": "New slot capacity is unavailable.",
                "reason": capacity.get("reason"),
                "next_available": capacity.get("next_available"),
            },
        )

    duration = require_clinic_booking_integer(clinic_org, "default_slot_duration_minutes")
    new_end = new_start + timedelta(minutes=duration)

    clinic_appt.start_time = new_start
    clinic_appt.end_time = new_end
    clinic_appt.status = "scheduled"
    await db.flush()
    await db.refresh(clinic_appt)
    await write_visit_event(
        db=db,
        visit_id=clinic_appt.id,
        org_id=org_id,
        event_type="RESCHEDULED",
        notes=req.reason or f"Rescheduled to {req.new_date} {req.new_time}",
        metadata={"new_date": str(req.new_date), "new_time": req.new_time},
    )
    await enqueue_outbox_event(
        db=db,
        org_id=org_id,
        event_type="APPOINTMENT_RESCHEDULED",
        payload={
            "event": "APPOINTMENT_RESCHEDULED",
            "appointment_id": str(clinic_appt.id),
            "org_id": str(org_id),
            "new_date": str(req.new_date),
            "new_time": req.new_time,
        },
    )
    await db.commit()
    invalidate_slot_cache(str(org_id), old_date.isoformat())
    invalidate_slot_cache(str(org_id), clinic_appt.start_time.strftime("%Y-%m-%d"))
    return await build_single_appointment_response(db, clinic_appt, org_id)


async def cancel_clinic_appointment(
    db: AsyncSession,
    appointment_id: UUID,
    reason: str,
    org_id: UUID,
) -> AppointmentResponse:
    clinic_appt = await db.scalar(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.org_id == org_id,
        ).with_for_update()
    )
    if not clinic_appt:
        raise HTTPException(status_code=404, detail="Clinic appointment not found")
    if clinic_appt.status in ("completed", "in_progress"):
        raise HTTPException(status_code=409, detail="An active or completed consultation cannot be cancelled")
    if clinic_appt.status == "cancelled":
        return await build_single_appointment_response(db, clinic_appt, org_id)
    clinic_appt.status = "cancelled"
    clinic_appt.queue_state = "not_checked_in"
    clinic_appt.cancellation_reason = reason or "Cancelled by clinic desk"
    await db.flush()
    await db.refresh(clinic_appt)
    await write_visit_event(
        db=db,
        visit_id=clinic_appt.id,
        org_id=org_id,
        event_type="CANCELLED",
        notes=clinic_appt.cancellation_reason,
    )
    await enqueue_outbox_event(
        db=db,
        org_id=org_id,
        event_type="APPOINTMENT_CANCELLED",
        payload={
            "event": "APPOINTMENT_CANCELLED",
            "appointment_id": str(clinic_appt.id),
            "org_id": str(org_id),
            "reason": clinic_appt.cancellation_reason,
        },
    )
    await db.commit()
    invalidate_slot_cache(str(org_id), clinic_appt.start_time.strftime("%Y-%m-%d"))
    return await build_single_appointment_response(db, clinic_appt, org_id)


async def get_appointment_visit_events(
    db: AsyncSession,
    appointment_id: UUID,
    org_id: UUID,
) -> List[VisitEventResponse]:
    appt = await db.get(Appointment, appointment_id)
    if not appt or appt.org_id != org_id:
        return []

    result = await db.execute(
        select(VisitEvent).where(
            VisitEvent.org_id == org_id,
            VisitEvent.visit_id == appointment_id,
        ).order_by(VisitEvent.occurred_at.asc(), VisitEvent.id.asc())
    )
    return [VisitEventResponse.model_validate(event) for event in result.scalars().all()]


async def update_appointment_doctor_notes(
    db: AsyncSession,
    appointment_id: UUID,
    req: Any,
    org_id: UUID,
):
    from app.services.patients.notes_service import update_clinic_doctor_notes
    return await update_clinic_doctor_notes(
        db=db,
        org_id=org_id,
        appointment_id=appointment_id,
        doctor_notes=req.doctor_notes,
        recent_diagnosis=req.recent_diagnosis,
        bill_items=req.bill_items,
        fee=req.fee,
    )


async def save_patient_clinical_note(
    db: AsyncSession,
    patient_id: UUID,
    req: Any,
    org_id: UUID,
):
    from app.services.patients.notes_service import save_patient_ehr_note_service
    return await save_patient_ehr_note_service(
        db=db,
        org_id=org_id,
        patient_id=patient_id,
        note=req.note,
    )


async def resolve_emergency_callback(
    db: AsyncSession,
    session_id: UUID,
    org_id: UUID,
):
    from app.services.clinic.dashboard_service import resolve_clinic_emergency_callback
    return await resolve_clinic_emergency_callback(
        db=db,
        org_id=org_id,
        session_id=session_id,
    )

