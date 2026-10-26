import logging
import re
import uuid
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import String, and_, cast, func, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.clinic_config import (
    require_clinic_booking_integer,
    require_clinic_timezone,
)
from app.core.phone_utils import normalize_phone_e164
from app.models.appointment import Appointment
from app.models.call_session import CallLog
from app.models.organization import Organization
from app.models.patient import Patient
from app.models.user import User
from app.schemas.appointment import ClinicRescheduleRequest
from app.services.appointments.booking_service import (
    get_future_capacity,
    has_active_visit,
    lock_daily_capacity,
)
from app.services.appointments.encounter_service import (
    cancel_clinic_appointment,
    reschedule_clinic_appointment,
    write_visit_event,
)
from app.services.appointments.schedule_service import (
    get_effective_weekly_schedule,
    parse_time_str,
)
from app.services.infra.outbox import (
    enqueue_outbox_event,
    get_mutation_operation,
    record_mutation_operation,
)

logger = logging.getLogger(__name__)


def _format_spoken_date(target_d: date, tz_name: str) -> str:
    today_d = datetime.now(ZoneInfo(tz_name)).date()
    if target_d == today_d:
        return "today"
    if target_d == today_d + timedelta(days=1):
        return "tomorrow"
    if target_d == today_d - timedelta(days=1):
        return "yesterday"
    diff = (target_d - today_d).days
    if 0 < diff < 7:
        return target_d.strftime("%A, %B %d")
    return target_d.strftime("%B %d")


def _canonical_phone(phone: str | None) -> str:
    raw = (phone or "").strip()
    normalized = normalize_phone_e164(raw)
    return normalized.e164_phone if normalized.is_valid else raw


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


async def _find_named_patient(
    db: AsyncSession, org_id: UUID, phone: str, first_name: str, last_name: str,
) -> tuple[Patient | None, bool]:
    candidates = (await db.execute(select(Patient).where(
        Patient.org_id == org_id, _phone_matches_patient(phone),
    ))).scalars().all()
    first = first_name.strip().casefold()
    last = last_name.strip().casefold()
    matches = [patient for patient in candidates if
        patient.first_name.strip().casefold() == first and
        patient.last_name.strip().casefold() == last]
    return (matches[0] if len(matches) == 1 else None, len(matches) > 1)


async def _select_doctor(db: AsyncSession, org_id: UUID, requested_id: str | None, requested_name: str | None = None) -> User | None:
    query = select(User).where(
        User.org_id == org_id, cast(User.role, String) == "doctor", User.is_active == True,
    )
    if requested_id:
        try:
            query = query.where(User.id == UUID(str(requested_id)))
        except ValueError:
            return None
    doctors = (await db.execute(query)).scalars().all()
    if requested_name and not requested_id:
        def normalized_name(value):
            return re.sub(r"^(?:dr\.?|doctor)\s+", "", " ".join(value.split()).casefold())
        name = normalized_name(requested_name)
        matches = [doctor for doctor in doctors if normalized_name(doctor.full_name or "") == name]
        # Never silently select a different doctor or guess between namesakes.
        return matches[0] if len(matches) == 1 else None
    return doctors[0] if doctors else None

CLINIC_TOOLS = {
    "verify_patient_identity",
    "search_doctor_slots",
    "confirm_appointment_booking",
    "reschedule_appointment",
    "cancel_appointment",
    "check_doctor_live_status",
    "lookup_clinic_faq",
    "transfer_to_human_operator",
}


async def dispatch_clinic_tool(
    tool_name: str,
    arguments: dict[str, Any],
    db: AsyncSession,
    org_id: UUID,
    clean_phone: str | None = None,
    call_session_id: UUID | None = None,
) -> dict[str, Any]:
    logger.info("[CLINIC TOOL ROUTER] '%s' | org=%s", tool_name, org_id)

    if tool_name not in CLINIC_TOOLS:
        logger.warning(f"[CLINIC TOOL ROUTER] Tool '{tool_name}' not in clinic surface — refused.")
        return {"error": f"Tool '{tool_name}' is not available for clinic tenants."}

    org_res = await db.execute(select(Organization).where(Organization.id == org_id))
    org_obj = org_res.scalar_one_or_none()
    if not org_obj:
        return {"status": "unavailable", "message": "Clinic configuration is unavailable."}

    if tool_name == "verify_patient_identity":
        return await _verify_patient(arguments, db, org_id, org_obj, clean_phone, call_session_id)
    elif tool_name == "search_doctor_slots":
        return await _search_slots(arguments, db, org_id, org_obj)
    elif tool_name == "confirm_appointment_booking":
        return await _confirm_booking(arguments, db, org_id, org_obj, clean_phone, call_session_id)
    elif tool_name == "reschedule_appointment":
        return await _reschedule(arguments, db, org_id, org_obj, clean_phone, call_session_id)
    elif tool_name == "cancel_appointment":
        return await _cancel(arguments, db, org_id, clean_phone, call_session_id)
    elif tool_name == "check_doctor_live_status":
        return await _check_doctor_status(arguments, db, org_id)
    elif tool_name == "lookup_clinic_faq":
        return await _lookup_faq(arguments, org_obj)
    elif tool_name == "transfer_to_human_operator":
        return await _transfer_to_human(arguments, org_obj)

    return {"error": "Unhandled clinic tool."}


async def _verify_patient(
    arguments: dict[str, Any],
    db: AsyncSession,
    org_id: UUID,
    org_obj: Organization | None,
    clean_phone: str | None,
    call_session_id: UUID | None = None,
) -> dict[str, Any]:
    first_name = arguments.get("first_name", "").strip()
    last_name = arguments.get("last_name", "").strip()
    target_phone = _canonical_phone(clean_phone or arguments.get("phone") or arguments.get("patient_phone"))

    patient, ambiguous = await _find_named_patient(
        db, org_id, target_phone, first_name, last_name,
    )
    if ambiguous:
        return {"verified": False, "message": "More than one profile matches. Please contact reception for identity verification."}

    if not patient:
        return {
            "verified": False,
            "message": f"No record found for '{first_name} {last_name}'. We can create a new appointment.",
        }

    if call_session_id:
        call = await db.scalar(select(CallLog).where(
            CallLog.id == call_session_id, CallLog.org_id == org_id,
            CallLog.end_time.is_(None),
        ).with_for_update())
        if not call or _canonical_phone(call.caller_phone) != target_phone:
            return {"verified": False, "message": "An active matching call is required for verification."}
        call.patient_id = patient.id
        await db.commit()

    tz_name = require_clinic_timezone(org_obj)
    clinic_today = datetime.now(ZoneInfo(tz_name)).date()

    appt_res = await db.execute(
        select(Appointment, User).outerjoin(User, Appointment.doctor_id == User.id).where(
            Appointment.patient_id == patient.id,
            Appointment.org_id == org_id,
            cast(Appointment.status, String).in_(["scheduled", "in_progress", "confirmed"]),
            Appointment.appointment_date >= clinic_today,
        ).order_by(Appointment.appointment_date.asc(), Appointment.start_time.asc())
    )
    rows = appt_res.all()
    active_appts = []
    for a, doc in rows:
        doctor_name = doc.full_name.strip() if doc and doc.full_name else "Attending Physician"
        if doc and not re.match(r"^(?:dr\.?|doctor)\s+", doctor_name, re.IGNORECASE):
            doctor_name = f"Dr. {doctor_name}"
        active_appts.append({
            "appointment_id": str(a.id),
            "appointment_date": a.appointment_date.isoformat() if a.appointment_date else None,
            "appointment_time": a.appointment_time,
            "doctor_name": doctor_name,
            "status": a.status,
        })

    return {
        "verified": True,
        "patient_id": str(patient.id),
        "patient_name": f"{patient.first_name} {patient.last_name}",
        "active_appointments": active_appts,
        "message": f"Identity verified for {patient.first_name} {patient.last_name}. Found {len(active_appts)} upcoming appointment(s).",
    }


async def _search_slots(
    arguments: dict[str, Any],
    db: AsyncSession,
    org_id: UUID,
    org_obj: Organization | None,
) -> dict[str, Any]:
    tz = ZoneInfo(require_clinic_timezone(org_obj))
    try:
        req_date = date.fromisoformat(arguments.get("target_date", ""))
    except Exception:
        return {"available": False, "reason": "INVALID_DATE", "message": "Which day would you like to come?"}

    clinic_today = datetime.now(tz).date()
    tz_name = require_clinic_timezone(org_obj)
    schedule = get_effective_weekly_schedule(org_obj.weekly_schedule if org_obj else None)
    day_name = req_date.strftime("%A").lower()
    day_cfg = schedule.get(day_name, {})

    if not day_cfg.get("isOpen", True):
        return {
            "available": False,
            "reason": f"The clinic is closed on {day_name.capitalize()}.",
            "alternative_slots": [],
        }

    doctor = await _select_doctor(db, org_id, arguments.get("doctor_id"), arguments.get("preferred_doctor_name"))
    if arguments.get("doctor_id") and not doctor:
        return {"available": False, "reason": "The requested doctor is unavailable at this clinic."}
    if not doctor:
        return {"available": False, "reason": "No active doctor is available for booking."}
    doc_name = doctor.full_name.strip() if doctor else "Attending Physician"
    doctor_name = doc_name if doc_name.lower().startswith("dr.") else f"Dr. {doc_name}"
    doctor_id = doctor.id if doctor else None

    req_time = arguments.get("target_time", "")
    capacity = await get_future_capacity(db, org_obj, org_id, req_date, req_time or None, doctor_id=doctor_id)
    available = capacity["available_slots"]
    requested_time = parse_time_str(req_time) if req_time else None
    requested_past = bool(requested_time and req_date == clinic_today and
                          datetime.combine(req_date, requested_time, tzinfo=tz) <= datetime.now(tz))

    if not requested_past and req_date == clinic_today and capacity.get("reason") == "QUEUE_OVERLAP":
        waiting_count = capacity.get("waiting_patients", 0)
        clearance = capacity.get("queue_clearance_time")
        next_avail = capacity.get("next_available")
        return {
            "available": False,
            "booking_mode": "queue_overlap",
            "reason": f"Dr. is currently with walk-in patients (approx. {waiting_count} waiting) until {clearance}. Appointment capacity opens at {next_avail}, Please choose a later arrival window. Queue order begins at physical check-in.",
            "next_available": next_avail,
            "queue_clearance_time": clearance,
            "available_slots": available[:5],
        }

    if not available:
        next_day = None
        for offset in range(1, 8):
            candidate_date = req_date + timedelta(days=offset)
            later = await get_future_capacity(db, org_obj, org_id, candidate_date, doctor_id=doctor_id)
            if later["available_slots"]:
                next_day = {"date": candidate_date.isoformat(), "time": later["available_slots"][0]}
                break
        return {
            "available": False,
            "availability": capacity["availability"],
            "reason": capacity["reason"] or "No future capacity remains on this date.",
            "next_available": capacity["next_available"],
            "alternative_slots": [],
            "next_day_opening": next_day,
        }

    recommended = capacity.get("recommended_slots", [])
    busy = capacity.get("busy_slots", [])
    chosen = (recommended or busy or available)[0]
    if req_time:
        chosen = capacity["next_available"] or chosen

    requested = parse_time_str(req_time) if req_time else None
    alternatives = available
    if requested:
        requested_minutes = requested.hour * 60 + requested.minute
        alternatives = sorted(available, key=lambda label: (
            abs((parse_time_str(label).hour * 60 + parse_time_str(label).minute) - requested_minutes),
            parse_time_str(label),
        ))

    offered_slots = alternatives[:2] if requested else (recommended[:2] or busy[:2])
    requested_available = (capacity["availability"] == "AVAILABLE") if req_time else None
    return {
        "status": "available",
        "doctor": doctor_name,
        "date": req_date.isoformat(),
        "spoken_date": _format_spoken_date(req_date, tz_name),
        "requested_time": req_time or None,
        "requested_time_available": requested_available,
        "reason": "PAST_TIME" if requested_past else capacity.get("reason"),
        "offers": [
            {"label": slot, "demand": "busy" if slot in busy else "normal"}
            for slot in offered_slots
        ],
        "all_available_slots": available,
    }


async def _confirm_booking(
    arguments: dict[str, Any],
    db: AsyncSession,
    org_id: UUID,
    org_obj: Organization | None,
    clean_phone: str | None,
    call_session_id: UUID | None = None,
) -> dict[str, Any]:

    raw_f = str(arguments.get("first_name") or "").strip()
    raw_l = str(arguments.get("last_name") or "").strip()
    if not raw_f or not raw_l:
        return {
            "status": "validation_error",
            "message": "Patient first name and last name are required. Please ask the caller: 'May I have your full name?'",
        }

    slot_date_str = arguments.get("slot_date", "")
    slot_time_str = arguments.get("slot_time", "")
    try:
        s_date = date.fromisoformat(slot_date_str)
    except (ValueError, TypeError):
        return {"status": "validation_error", "message": "Please provide a valid appointment date in YYYY-MM-DD format."}

    tz = ZoneInfo(require_clinic_timezone(org_obj))
    clinic_today = datetime.now(tz).date()
    if not call_session_id:
        return {"status": "confirmation_required", "message": "A confirmed active voice call is required."}

    target_phone = _canonical_phone(clean_phone or arguments.get("phone") or arguments.get("patient_phone"))
    op_key = arguments.get("operation_key")
    if op_key:
        existing_op = await get_mutation_operation(db, org_id, op_key)
        if existing_op and existing_op.status == "completed":
            return existing_op.response_payload

    from app.services.voice.booking_consent import authorize_booking
    details = {key: arguments.get(key, "appointment" if key == "booking_mode" else "") for key in
               ("first_name", "last_name", "slot_date", "slot_time", "doctor_name", "chief_complaint", "booking_mode")}
    call_log, refusal = await authorize_booking(db, org_id, call_session_id, details)
    if refusal:
        return refusal

    doctor = await _select_doctor(db, org_id, arguments.get("doctor_id"), arguments.get("doctor_name"))
    if arguments.get("doctor_id") and not doctor:
        return {"status": "unavailable", "message": "The requested doctor is unavailable at this clinic."}
    if not doctor:
        return {"status": "doctor_unavailable", "message": "I couldn't match that doctor. Please check the doctor's name. This does not mean the time is fully booked."}
    doctor_id = doctor.id if doctor else None
    if s_date < clinic_today:
        return {
            "status": "validation_error",
            "message": "Cannot book appointments in the past.",
        }

    parsed_requested_time = parse_time_str(slot_time_str)
    if not parsed_requested_time:
        return {"status": "validation_error", "message": "Please provide a valid clinic time."}
    if s_date == clinic_today and datetime.combine(s_date, parsed_requested_time, tzinfo=tz) <= datetime.now(tz):
        return {"status": "validation_error", "message": "That time has already passed today. Please choose a future time."}

    if s_date == clinic_today:
        capacity = await get_future_capacity(db, org_obj, org_id, s_date, slot_time_str, doctor_id=doctor_id)
        if arguments.get("booking_mode") == "queue":
            return await _create_same_day_token(
                arguments=arguments,
                db=db,
                org_id=org_id,
                org_obj=org_obj,
                clean_phone=clean_phone,
                first_name=raw_f,
                last_name=raw_l,
                call_session_id=call_session_id,
                doctor_id=doctor_id,
            )
        elif capacity.get("reason") == "QUEUE_OVERLAP":
            return {
                "status": "unavailable",
                "reason": "QUEUE_OVERLAP",
                "message": "That time slot operates as a walk-in queue today. Would you like to register for today's queue instead, or pick another appointment date?",
            }
        elif capacity.get("availability") != "AVAILABLE":
            return {
                "status": "unavailable",
                "message": f"Requested slot at {slot_time_str} is unavailable. Next available slot is {capacity.get('next_available')}.",
                "next_available": capacity.get("next_available"),
            }

    start_dt = datetime.combine(s_date, parsed_requested_time, tzinfo=tz)
    end_dt = start_dt + timedelta(minutes=require_clinic_booking_integer(org_obj, "default_slot_duration_minutes"))

    await lock_daily_capacity(db, org_id, s_date)
    if org_obj:
        capacity = await get_future_capacity(db, org_obj, org_id, s_date, slot_time_str, doctor_id=doctor_id)
        if capacity["availability"] != "AVAILABLE":
            return {
                "status": "unavailable",
                "reason": "INSUFFICIENT_CAPACITY",
                "message": f"That future time is unavailable. The next available time is {capacity['next_available'] or 'not available'}.",
            }

    target_phone = _canonical_phone(clean_phone or arguments.get("phone") or arguments.get("patient_phone"))
    if not target_phone:
        return {"status": "validation_error", "message": "Please provide the patient's phone number."}
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"patient-intake:{org_id}:{target_phone}:{f'{raw_f} {raw_l}'.casefold()}"},
    )
    patient, ambiguous = await _find_named_patient(db, org_id, target_phone, raw_f, raw_l)
    if ambiguous:
        return {"status": "identity_ambiguous", "message": "Please ask reception to verify this patient's profile."}

    if not patient:
        patient = Patient(
            id=uuid.uuid4(),
            org_id=org_id,
            phone_number=target_phone,
            first_name=raw_f,
            last_name=raw_l,
        )
        db.add(patient)
        await db.flush()
    elif await has_active_visit(db, org_id, patient.id):
        return {
            "status": "duplicate_active_visit",
            "message": "This patient already has an active visit. Please use the existing visit or ask reception for help.",
        }

    doctor_name = doctor.full_name.strip() if doctor else "Attending Physician"
    if doctor and not re.match(r"^(?:dr\.?|doctor)\s+", doctor_name, re.IGNORECASE):
        doctor_name = f"Dr. {doctor_name}"
    appt_id = uuid.uuid4()
    appt_obj = Appointment(
        id=appt_id,
        org_id=org_id,
        appointment_timezone=require_clinic_timezone(org_obj),
        patient_id=patient.id,
        doctor_id=doctor_id,
        start_time=start_dt,
        end_time=end_dt,
        status="scheduled",
        token_number=None,
        token_prefix=None,
        display_token=None,
        chief_complaint=arguments.get("chief_complaint") or None,
        fee=org_obj.consultation_fee if org_obj else None,
        payment_status="pending",
        source="ai_voice",
        call_session_id=call_session_id,
        booking_metadata={
            "arrival_time": slot_time_str,
            "queue_policy": "service_order_is_set_when_the_patient_checks_in",
        },
    )
    from sqlalchemy.exc import IntegrityError
    try:
        db.add(appt_obj)
        await db.flush()
        await write_visit_event(
            db=db, visit_id=appt_obj.id, org_id=org_id,
            event_type="APPOINTMENT_BOOKED", actor_type="ai_voice",
            metadata={"start_time": start_dt.isoformat()},
        )
    except IntegrityError as exc:
        await db.rollback()
        sqlstate = getattr(exc.orig, "sqlstate", None)
        if sqlstate not in ("23505", "23P01"):
            raise
        org_obj = await db.get(Organization, org_id)
        capacity = await get_future_capacity(db, org_obj, org_id, s_date, slot_time_str, doctor_id=doctor_id)
        return {"status": "unavailable", "message": "That arrival window was just booked. Please choose another time.", "next_available": capacity.get("next_available")}

    clinic_name = org_obj.name if org_obj and org_obj.name else ""
    clinic_address = org_obj.address if org_obj and org_obj.address else ""
    spoken_date = _format_spoken_date(s_date, require_clinic_timezone(org_obj))

    result = {
        "status": "confirmed",
        "appointment_id": str(appt_id),
        "patient_name": f"{patient.first_name} {patient.last_name}".strip(),
        "doctor_name": doctor_name,
        "token_number": None,
        "clinic_name": clinic_name,
        "clinic_address": clinic_address,
        "date": s_date.isoformat(),
        "spoken_date": spoken_date,
        "time": slot_time_str,
        "message": f"Appointment confirmed with {doctor_name} for {spoken_date} around {slot_time_str}. Please check in at reception upon arrival to receive your queue token.",
    }
    call_log.booking_result = result
    call_log.call_outcome = "appointment_booked"
    call_log.patient_id = patient.id
    if op_key and hasattr(db, "flush"):
        await record_mutation_operation(db, org_id, call_session_id, op_key, "book_appointment", result)
    if hasattr(db, "add") and hasattr(db, "flush"):
        await enqueue_outbox_event(db, org_id, "APPOINTMENT_BOOKED", {"event": "APPOINTMENT_BOOKED", "appointment_id": result["appointment_id"], "patient_id": str(patient.id), "doctor_id": str(doctor_id) if doctor_id else None})
    await db.commit()
    from app.services.infra.websocket_manager import ws_manager
    try:
        await ws_manager.broadcast_to_org(str(org_id), {"event": "APPOINTMENT_BOOKED", "appointment_id": result["appointment_id"]})
    except Exception:
        logger.warning("Booking saved; dashboard notification unavailable")
    return result


async def _create_same_day_token(
    arguments: dict[str, Any],
    db: AsyncSession,
    org_id: UUID,
    org_obj: Organization | None,
    clean_phone: str | None,
    first_name: str,
    last_name: str,
    call_session_id: UUID | None = None,
    doctor_id: UUID | None = None,
) -> dict[str, Any]:

    from app.services.voice.booking_consent import authorize_booking
    details = {key: arguments.get(key, "appointment" if key == "booking_mode" else "") for key in
               ("first_name", "last_name", "slot_date", "slot_time", "doctor_name", "chief_complaint", "booking_mode")}
    call_log, refusal = await authorize_booking(db, org_id, call_session_id, details)
    if refusal:
        return refusal
    target_phone = _canonical_phone(clean_phone)
    target_date = datetime.now(ZoneInfo(require_clinic_timezone(org_obj))).date()
    op_key = arguments.get("operation_key")
    if op_key:
        existing_op = await get_mutation_operation(db, org_id, op_key)
        if existing_op and existing_op.status == "completed":
            return existing_op.response_payload

    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"clinic-token:{org_id}:{target_date}:W"},
    )
    patient, ambiguous = await _find_named_patient(db, org_id, target_phone, first_name, last_name)
    if ambiguous:
        return {"status": "identity_ambiguous", "message": "Please ask reception to verify this patient's profile."}
    if not patient:
        patient = Patient(
            id=uuid.uuid4(),
            org_id=org_id,
            phone_number=target_phone,
            first_name=first_name,
            last_name=last_name,
        )
        db.add(patient)
        await db.flush()
    elif await has_active_visit(db, org_id, patient.id):
        return {
            "status": "duplicate_active_visit",
            "message": "This patient already has an active visit. Please use the existing visit or ask reception for help.",
        }

    max_res = await db.execute(
        select(func.max(Appointment.token_number)).where(
            Appointment.org_id == org_id,
            Appointment.appointment_date == target_date,
            Appointment.display_token.like("W-%"),
        )
    )
    token_number = (max_res.scalar() or 0) + 1
    tz = ZoneInfo(require_clinic_timezone(org_obj))
    now = datetime.now(tz)
    interval = (require_clinic_booking_integer(org_obj, "default_slot_duration_minutes")) + (
        require_clinic_booking_integer(org_obj, "slot_buffer_minutes", allow_zero=True)
    )
    waiting_res = await db.execute(
        select(func.count(Appointment.id)).where(
            Appointment.org_id == org_id,
            Appointment.appointment_date == target_date,
            cast(Appointment.status, String).in_(["arrived"]),
        )
    )
    estimated = now + timedelta(minutes=(waiting_res.scalar() or 0) * interval)
    if doctor_id:
        doctor = await _select_doctor(db, org_id, str(doctor_id))
    else:
        doctor = await _select_doctor(db, org_id, arguments.get("doctor_id"), arguments.get("doctor_name"))
    appointment = Appointment(
        id=uuid.uuid4(),
        org_id=org_id,
        appointment_timezone=require_clinic_timezone(org_obj),
        patient_id=patient.id,
        doctor_id=doctor.id if doctor else None,
        start_time=now,
        end_time=now + timedelta(minutes=require_clinic_booking_integer(org_obj, "default_slot_duration_minutes")),
        status="scheduled",
        token_prefix="W",
        token_number=token_number,
        display_token=f"W-{token_number}",
        chief_complaint=arguments.get("chief_complaint") or None,
        fee=org_obj.consultation_fee if org_obj else None,
        payment_status="pending",
        source="ai_voice" if call_session_id else "walk_in",
        call_session_id=call_session_id,
    )
    db.add(appointment)
    await db.flush()
    await write_visit_event(
        db=db, visit_id=appointment.id, org_id=org_id,
        event_type="WALK_IN_REGISTERED", actor_type="ai_voice",
        metadata={"token": appointment.display_token},
    )
    result = {
        "status": "confirmed",
        "booking_mode": "queue",
        "requires_check_in": True,
        "appointment_id": str(appointment.id),
        "patient_name": f"{patient.first_name} {patient.last_name}".strip(),
        "token_number": token_number,
        "display_token": appointment.display_token,
        "estimated_turn_time": estimated.strftime("%I:%M %p").lstrip("0"),
        "spoken_date": "today",
        "message": f"Your visit registration is {appointment.display_token}. Check in at reception on arrival to join the queue. Waiting time may change.",
    }
    call_log.booking_result = result
    call_log.call_outcome = "appointment_booked"
    call_log.patient_id = patient.id
    if op_key and hasattr(db, "flush"):
        await record_mutation_operation(db, org_id, call_session_id, op_key, "book_appointment", result)
    if hasattr(db, "add") and hasattr(db, "flush"):
        await enqueue_outbox_event(db, org_id, "APPOINTMENT_BOOKED", {"event": "APPOINTMENT_BOOKED", "appointment_id": result["appointment_id"], "patient_id": str(patient.id), "display_token": appointment.display_token})
    await db.commit()
    from app.services.infra.websocket_manager import ws_manager
    try:
        await ws_manager.broadcast_to_org(str(org_id), {"event": "APPOINTMENT_BOOKED", "appointment_id": result["appointment_id"]})
    except Exception:
        logger.warning("Booking saved; dashboard notification unavailable")
    return result


async def _call_has_verified_patient(
    db: AsyncSession, org_id: UUID, call_session_id: UUID | None,
    patient_id: UUID, caller_phone: str | None,
) -> bool:
    if not call_session_id:
        return False
    call = await db.scalar(select(CallLog).where(
        CallLog.id == call_session_id, CallLog.org_id == org_id,
        CallLog.end_time.is_(None),
    ))
    return bool(call and call.patient_id == patient_id
                and _canonical_phone(call.caller_phone) == _canonical_phone(caller_phone))


async def _reschedule(
    arguments: dict[str, Any],
    db: AsyncSession,
    org_id: UUID,
    org_obj: Organization | None,
    clean_phone: str | None,
    call_session_id: UUID | None = None,
) -> dict[str, Any]:
    appt_id_str = arguments.get("appointment_id", "")
    new_date_str = arguments.get("new_date", "")
    new_time_str = arguments.get("new_time", "")

    try:
        new_date = date.fromisoformat(new_date_str)
    except Exception:
        return {"status": "error", "reason": "Invalid date format. Use YYYY-MM-DD."}

    try:
        parsed_id = appt_id_str if isinstance(appt_id_str, UUID) else UUID(str(appt_id_str))
        appt_res = await db.execute(
            select(Appointment).where(
                Appointment.id == parsed_id,
                Appointment.org_id == org_id,
            )
        )
        appt = appt_res.scalar_one_or_none()
    except Exception:
        return {"status": "error", "reason": f"Invalid appointment ID: {appt_id_str}"}

    if not appt:
        return {"status": "error", "reason": f"Appointment {appt_id_str} not found in clinic records."}

    op_key = arguments.get("operation_key")
    if op_key:
        existing_op = await get_mutation_operation(db, org_id, op_key)
        if existing_op and existing_op.status == "completed":
            return existing_op.response_payload

    if not await _call_has_verified_patient(db, org_id, call_session_id, appt.patient_id, clean_phone):
        return {"status": "verification_required", "message": "Verify the patient for this appointment first. A shared phone number is not sufficient."}

    if not org_obj or not org_obj.timezone or not str(org_obj.timezone).strip():
        return {"status": "error", "reason": "Clinic timezone is not configured."}
    tz = ZoneInfo(str(org_obj.timezone).strip())
    clinic_today = datetime.now(tz).date()
    patient_res = await db.execute(select(Patient).where(Patient.id == appt.patient_id))
    patient = patient_res.scalar_one_or_none()
    if not patient or _canonical_phone(patient.phone_number) != _canonical_phone(clean_phone):
        return {"status": "verification_required", "message": "Please verify the appointment with reception."}
    if new_date <= clinic_today:
        return {"status": "verification_required", "message": "For a same-day queue change, please speak with reception."}
    try:
        await reschedule_clinic_appointment(
            db, appt.id, ClinicRescheduleRequest(
                new_date=new_date, new_time=new_time_str,
                reason="Patient request via voice",
            ), org_id,
        )
    except Exception as exc:
        if getattr(exc, "status_code", None) in (400, 409):
            return {"status": "unavailable", "reason": getattr(exc, "detail", "The requested time is unavailable")}
        raise

    result = {
        "status": "success",
        "message": f"Appointment rescheduled to {new_date_str} at {new_time_str}.",
        "confirmed_date": new_date_str,
        "confirmed_time": new_time_str,
        "audit_recorded": True,
    }
    if op_key and hasattr(db, "flush"):
        await record_mutation_operation(db, org_id, call_session_id, op_key, "reschedule_appointment", result)
    if hasattr(db, "add") and hasattr(db, "flush"):
        await enqueue_outbox_event(db, org_id, "APPOINTMENT_RESCHEDULED", {"event": "APPOINTMENT_RESCHEDULED", "appointment_id": str(appt.id), "new_date": new_date_str, "new_time": new_time_str})
    await db.commit()
    return result


async def _cancel(
    arguments: dict[str, Any],
    db: AsyncSession,
    org_id: UUID,
    clean_phone: str | None,
    call_session_id: UUID | None = None,
) -> dict[str, Any]:
    appt_id_str = arguments.get("appointment_id", "")
    reason = arguments.get("cancellation_reason", "Patient request via voice")

    try:
        appt_res = await db.execute(
            select(Appointment).where(
                Appointment.id == UUID(appt_id_str),
                Appointment.org_id == org_id,
            )
        )
        appt = appt_res.scalar_one_or_none()
    except Exception:
        return {"status": "error", "reason": f"Invalid appointment ID: {appt_id_str}"}

    if not appt:
        return {"status": "error", "reason": f"Appointment {appt_id_str} not found in clinic records."}

    op_key = arguments.get("operation_key")
    if op_key:
        existing_op = await get_mutation_operation(db, org_id, op_key)
        if existing_op and existing_op.status == "completed":
            return existing_op.response_payload

    if not await _call_has_verified_patient(db, org_id, call_session_id, appt.patient_id, clean_phone):
        return {"status": "verification_required", "message": "Verify the patient for this appointment first. A shared phone number is not sufficient."}

    patient_res = await db.execute(select(Patient).where(Patient.id == appt.patient_id))
    patient = patient_res.scalar_one_or_none()
    if not patient or _canonical_phone(patient.phone_number) != _canonical_phone(clean_phone):
        return {"status": "verification_required", "message": "Please verify the appointment with reception."}
    if appt.status in ("in_progress", "completed"):
        return {"status": "error", "reason": "An active or completed consultation cannot be cancelled."}

    await cancel_clinic_appointment(db, appt.id, reason, org_id)

    result = {
        "status": "cancelled",
        "message": f"Appointment {appt_id_str} has been cancelled and logged in clinic records.",
        "audit_recorded": True,
    }
    if op_key and hasattr(db, "flush"):
        await record_mutation_operation(db, org_id, call_session_id, op_key, "cancel_appointment", result)
    if hasattr(db, "add") and hasattr(db, "flush"):
        await enqueue_outbox_event(db, org_id, "APPOINTMENT_CANCELLED", {"event": "APPOINTMENT_CANCELLED", "appointment_id": str(appt.id), "reason": reason})
    await db.commit()
    return result


async def _check_doctor_status(
    arguments: dict[str, Any],
    db: AsyncSession,
    org_id: UUID,
) -> dict[str, Any]:
    name_or_spec = arguments.get("doctor_name_or_specialty", "").strip().lower()

    res = await db.execute(
        select(User).where(
            User.org_id == org_id,
            cast(User.role, String) == "doctor",
            User.is_active == True,
        )
    )
    doctors = res.scalars().all()

    if not doctors:
        return {"status": "unavailable", "message": "No doctors are currently registered at this clinic."}

    matched = None
    for d in doctors:
        if name_or_spec in d.full_name.lower() or name_or_spec in (d.specialization or "").lower():
            matched = d
            break

    doctor = matched or doctors[0]
    in_progress_res = await db.execute(
        select(Appointment).where(
            Appointment.org_id == org_id,
            Appointment.doctor_id == doctor.id,
            Appointment.appointment_date == date.today(),
            cast(Appointment.status, String) == "in_progress",
        )
    )
    in_chamber = in_progress_res.scalar_one_or_none()

    waiting_res = await db.execute(
        select(Appointment).where(
            Appointment.org_id == org_id,
            Appointment.doctor_id == doctor.id,
            Appointment.appointment_date == date.today(),
            cast(Appointment.status, String) == "scheduled",
        )
    )
    waiting_count = len(waiting_res.scalars().all())

    doc_name = doctor.full_name.strip() if doctor else "Attending Physician"
    doctor_title = doc_name if doc_name.lower().startswith("dr.") else f"Dr. {doc_name}"

    if in_chamber:
        status_msg = f"Yes, {doctor_title} is currently sitting in the consultation chamber attending to patients. There are currently {waiting_count} patient(s) in the waiting queue."
    elif waiting_count > 0:
        status_msg = f"Yes, {doctor_title} is on duty at the clinic today with {waiting_count} upcoming scheduled patient(s)."
    else:
        status_msg = f"Yes, {doctor_title} is available at the clinic today with open consultation slots."

    return {
        "status": "available",
        "doctor_name": doctor_title,
        "specialization": doctor.specialization or "General Medicine",
        "is_in_chamber": bool(in_chamber),
        "waiting_queue_count": waiting_count,
        "message": status_msg,
    }


async def _lookup_faq(
    arguments: dict[str, Any],
    org_obj: Organization | None,
) -> dict[str, Any]:
    if not org_obj:
        return {"answer": "Clinic information is currently unavailable. Please call back during office hours."}

    query = arguments.get("query", "").lower()

    if any(k in query for k in ["hour", "time", "open", "close", "timing"]):
        schedule = org_obj.weekly_schedule or {}
        hours = []
        for day, config in schedule.items():
            if not isinstance(config, dict):
                continue
            if not config.get("isOpen", True):
                hours.append(f"{day.capitalize()}: Closed")
                continue
            windows = config.get("windows") or [
                {"start": config.get(start), "end": config.get(end)}
                for start, end in (("morningStart", "morningEnd"), ("eveningStart", "eveningEnd"))
            ]
            ranges = [f"{window['start']}–{window['end']}" for window in windows if window.get("start") and window.get("end")]
            if ranges:
                hours.append(f"{day.capitalize()}: {', '.join(ranges)}")
        answer = "Clinic hours: " + "; ".join(hours) if hours else "Please contact the clinic for its operating hours."
    elif any(k in query for k in ["location", "address", "where", "direction"]):
        answer = org_obj.address or "Please contact the clinic directly for directions."
    elif any(k in query for k in ["phone", "contact", "number", "call"]):
        answer = f"You can reach us at {org_obj.hotline or org_obj.phone or 'our main line'}."
    elif any(k in query for k in ["fee", "cost", "charge", "price", "consult"]):
        fee = org_obj.consultation_fee if org_obj else None
        currency = org_obj.currency_symbol or "₹" if org_obj else ""
        answer = f"Our consultation fee is {currency}{fee}. Payment can be made at the clinic." if fee else "Please check with the clinic desk for consultation fee details."
    elif any(k in query for k in ["doctor", "specialist", "specialty"]):
        lead = f" Lead practitioner: {org_obj.lead_doctor_name}." if org_obj and org_obj.lead_doctor_name else ""
        spec = f"Our clinic specializes in {org_obj.clinic_specialty}." if org_obj and org_obj.clinic_specialty else "Please inquire for specialist schedules."
        answer = f"{spec}{lead}"
    elif any(k in query for k in ["emergency", "urgent", "ambulance"]):
        deflect = org_obj.emergency_deflection_phone if org_obj and org_obj.emergency_deflection_phone else "local emergency services"
        answer = f"We are an outpatient clinic and do not handle emergencies. For emergencies please call {deflect} or go to the nearest hospital."
    else:
        spec = f", specializing in {org_obj.clinic_specialty}" if org_obj and org_obj.clinic_specialty else ""
        answer = f"We are {org_obj.name if org_obj else 'the clinic'}{spec}. For appointments, please stay on the line."

    return {"answer": answer, "clinic_name": org_obj.name if org_obj else ""}


async def _transfer_to_human(
    arguments: dict[str, Any],
    org_obj: Organization | None,
) -> dict[str, Any]:
    reason = arguments.get("reason", "Caller request")
    return {
        "status": "transfer_initiated",
        "spoken_message": "I am connecting you to our clinic receptionist now. Please hold on for a moment.",
        "reason": reason,
        "hotline": org_obj.hotline if org_obj else None,
    }
