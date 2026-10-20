from datetime import date, datetime, timedelta, time
from typing import Dict, Any, List, Optional
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import phonenumbers
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import cast, String, func, or_

from app.models.organization import Organization
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.user import User
from app.models.schedule_override import ScheduleOverride
from app.schemas.appointment import AppointmentStatusUpdate
from app.core.phone_utils import normalize_phone_e164


DEFAULT_WEEKLY_SCHEDULE = {
    day: {"isOpen": False, "morningStart": "", "morningEnd": "", "eveningStart": "", "eveningEnd": ""}
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
}

def clinic_timezone(value: Optional[str]) -> ZoneInfo:
    if not value:
        raise HTTPException(422, "Clinic timezone is not configured")
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError:
        raise HTTPException(422, "Clinic timezone is invalid")


def resolve_org_timezone(org: Any) -> str:
    if not org:
        raise HTTPException(404, "Organization not found")
    tz = getattr(org, "timezone", None)
    if tz and str(tz).strip():
        return str(tz).strip()
    raise HTTPException(422, "Clinic timezone is not configured")


def resolve_org_emergency_phone(org: Any) -> str:
    if not org:
        return ""
    phone = getattr(org, "emergency_deflection_phone", None)
    if phone and str(phone).strip():
        return str(phone).strip()
    ai_settings = getattr(org, "voice_ai_settings", None)
    if isinstance(ai_settings, dict):
        val = ai_settings.get("emergency_deflection_phone")
        if val and str(val).strip():
            return str(val).strip()
    return ""


async def get_org_timezone(db: AsyncSession, org_id: UUID) -> str:
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    return resolve_org_timezone(org)


async def get_org_timezone_for_doctor(db: AsyncSession, doctor_id: UUID) -> str:
    result = await db.execute(select(User).where(User.id == doctor_id))
    user = result.scalar_one_or_none()
    if user and user.org_id:
        return await get_org_timezone(db, user.org_id)
    raise HTTPException(422, "Doctor is not assigned to a clinic")


def get_effective_weekly_schedule(raw_schedule: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    raw = raw_schedule or {}
    normalized: Dict[str, Dict[str, Any]] = {}
    for day, fallback in DEFAULT_WEEKLY_SCHEDULE.items():
        source = raw.get(day) or raw.get(day.capitalize()) or raw.get(day.upper()) or {}
        if isinstance(source, list):
            windows = source
            normalized[day] = {
                "isOpen": len(windows) > 0,
                "morningStart": fallback["morningStart"],
                "morningEnd": fallback["morningEnd"],
                "eveningStart": fallback["eveningStart"],
                "eveningEnd": fallback["eveningEnd"],
                "windows": windows,
            }
            continue

        if not isinstance(source, dict):
            source = {}

        windows = source.get("windows")
        if windows is None:
            windows = []
            m_s = source.get("morningStart", source.get("morning", {}).get("start", fallback["morningStart"]))
            m_e = source.get("morningEnd", source.get("morning", {}).get("end", fallback["morningEnd"]))
            if m_s and m_e:
                windows.append({"name": "Morning", "start": m_s, "end": m_e})
            e_s = source.get("eveningStart", source.get("evening", {}).get("start", fallback["eveningStart"]))
            e_e = source.get("eveningEnd", source.get("evening", {}).get("end", fallback["eveningEnd"]))
            if e_s and e_e:
                windows.append({"name": "Evening", "start": e_s, "end": e_e})
        normalized[day] = {
            "isOpen": source.get("isOpen", fallback["isOpen"]),
            "morningStart": source.get("morningStart", source.get("morning", {}).get("start", fallback["morningStart"])),
            "morningEnd": source.get("morningEnd", source.get("morning", {}).get("end", fallback["morningEnd"])),
            "eveningStart": source.get("eveningStart", source.get("evening", {}).get("start", fallback["eveningStart"])),
            "eveningEnd": source.get("eveningEnd", source.get("evening", {}).get("end", fallback["eveningEnd"])),
            "windows": windows,
        }
    return normalized


def parse_time_str(time_str: str) -> Optional[time]:
    if not time_str:
        return None
    time_str = time_str.strip().upper()
    for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M"):
        try:
            return datetime.strptime(time_str, fmt).time()
        except ValueError:
            pass
    return None


def format_time_label(t: time) -> str:
    h = t.hour
    m = t.minute
    h12 = h % 12 or 12
    ampm = "AM" if h < 12 else "PM"
    return f"{h12:02d}:{m:02d} {ampm}"


async def auto_mark_clinic_expired_no_shows(
    db: AsyncSession, org_id: Optional[UUID] = None, tz_name: Optional[str] = None
) -> int:
    resolved_tz = tz_name
    if not resolved_tz and org_id:
        org = await db.get(Organization, org_id)
        resolved_tz = resolve_org_timezone(org)
    if not resolved_tz:
        raise HTTPException(status_code=422, detail="Clinic timezone is not configured")
    tz = clinic_timezone(resolved_tz)
    now_local = datetime.now(tz)
    start_of_today = datetime.combine(now_local.date(), time(0, 0), tzinfo=tz)
    query = select(Appointment).where(
        cast(Appointment.status, String) == "scheduled",
        Appointment.start_time < start_of_today,
    )
    if org_id:
        query = query.where(Appointment.org_id == org_id)
    res = await db.execute(query)
    appts = res.scalars().all()

    marked_count = 0
    if appts:
        from app.services.appointments.encounter_service import write_visit_event
    for appt in appts:
        appt.status = "no_show"
        appt.queue_state = "not_checked_in"
        await write_visit_event(
            db=db,
            visit_id=appt.id,
            org_id=appt.org_id,
            event_type="NO_SHOW",
            notes="Auto-marked as expired",
        )
        marked_count += 1

    if marked_count > 0:
        await db.flush()

    return marked_count


async def auto_mark_expired_no_shows(db: AsyncSession, tz_name: Optional[str] = None) -> int:
    return await auto_mark_clinic_expired_no_shows(db, tz_name=tz_name)


async def get_clinic_daily_slots(
    db: AsyncSession, org_id: UUID, target_date: date, doctor_id: Optional[UUID] = None
) -> Dict[str, Any]:
    org = await db.get(Organization, org_id)
    if not org:
        return {
            "org_id": str(org_id),
            "target_date": target_date.isoformat(),
            "is_open": False,
            "reason": "Organization not found",
            "slots": [],
        }

    tz_name = resolve_org_timezone(org)
    tz = ZoneInfo(tz_name)
    now_local = datetime.now(tz)

    await auto_mark_clinic_expired_no_shows(db, org_id, tz_name)

    slot_duration = org.default_slot_duration_minutes
    slot_buffer = org.slot_buffer_minutes
    max_daily = org.max_daily_patients
    if slot_duration is None or slot_buffer is None or max_daily is None:
        return {
            "org_id": str(org_id),
            "target_date": target_date.isoformat(),
            "is_open": False,
            "reason": "Clinic scheduling settings are incomplete",
            "slots": [],
        }
    interval_minutes = slot_duration + slot_buffer

    weekly_schedule = get_effective_weekly_schedule(org.weekly_schedule)
    day_name = target_date.strftime("%A").lower()
    day_cfg = weekly_schedule.get(day_name, {})
    is_open = day_cfg.get("isOpen", False)

    default_emergency = resolve_org_emergency_phone(org)

    closure = None
    try:
        closure_res = await db.execute(
            select(ScheduleOverride).where(
                ScheduleOverride.org_id == org_id,
                or_(ScheduleOverride.doctor_id.is_(None), ScheduleOverride.doctor_id == doctor_id),
                ScheduleOverride.start_date <= target_date,
                ScheduleOverride.end_date >= target_date,
            )
        )
        closure = closure_res.scalars().first()
    except Exception:
        closure = None
    if closure:
        if closure.override_type == "special_hours" and closure.custom_hours:
            is_open = True
            day_cfg = {"isOpen": True, "windows": closure.custom_hours}
        else:
            return {
                "org_id": str(org_id),
                "target_date": target_date.isoformat(),
                "is_open": False,
                "reason": f"Closed for {closure.title}",
                "closure": {
                    "id": str(closure.id),
                    "title": closure.title,
                    "override_type": closure.override_type,
                    "start_date": closure.start_date.isoformat(),
                    "end_date": closure.end_date.isoformat(),
                    "reason": closure.reason,
                    "emergency_phone": closure.emergency_phone or default_emergency,
                },
                "emergency_phone": closure.emergency_phone or default_emergency,
                "slot_duration_minutes": slot_duration,
                "slot_buffer_minutes": slot_buffer,
                "max_daily_patients": max_daily,
                "total_booked": 0,
                "slots": [],
            }

    if not is_open:
        return {
            "org_id": str(org_id),
            "target_date": target_date.isoformat(),
            "is_open": False,
            "reason": f"Clinic is closed on {day_name.capitalize()}",
            "emergency_phone": default_emergency,
            "slot_duration_minutes": slot_duration,
            "slot_buffer_minutes": slot_buffer,
            "max_daily_patients": max_daily,
            "total_booked": 0,
            "slots": [],
        }

    start_of_target = datetime.combine(target_date, time(0, 0), tzinfo=tz)
    end_of_target = start_of_target + timedelta(days=1)
    appts_query = (
        select(Appointment, Patient)
        .join(Patient, Appointment.patient_id == Patient.id, isouter=True)
        .where(
            Appointment.org_id == org_id,
            *([Appointment.doctor_id == doctor_id] if doctor_id else []),
            Appointment.start_time >= start_of_target,
            Appointment.start_time < end_of_target,
        )
    )
    appts_res = await db.execute(appts_query)
    appts_data = appts_res.all()

    parsed_appts = []
    for appt, patient in appts_data:
        if appt.start_time:
            appt_start = (
                appt.start_time.astimezone(tz)
                if appt.start_time.tzinfo
                else appt.start_time.replace(tzinfo=tz)
            )
        elif appt.appointment_time and parse_time_str(appt.appointment_time):
            t = parse_time_str(appt.appointment_time)
            appt_start = datetime.combine(appt.appointment_date or target_date, t or time(9, 0), tzinfo=tz)
        else:
            appt_start = datetime.combine(appt.appointment_date or target_date, time(9, 0), tzinfo=tz)

        if appt.end_time:
            appt_end = (
                appt.end_time.astimezone(tz)
                if appt.end_time.tzinfo
                else appt.end_time.replace(tzinfo=tz)
            )
        else:
            appt_end = appt_start + timedelta(minutes=slot_duration)
        parsed_appts.append({
            "appointment_id": str(appt.id),
            "status": appt.status,
            "chief_complaint": appt.chief_complaint or "",
            "source": appt.source,
            "payment_status": appt.payment_status,
            "fee": appt.fee,
            "start_dt": appt_start,
            "end_dt": appt_end,
            "appointment_time": appt.appointment_time.strip().upper() if appt.appointment_time and parse_time_str(appt.appointment_time) else "",
            "token_prefix": appt.token_prefix,
            "patient_name": f"{patient.first_name} {patient.last_name}".strip() if patient else "Patient",
            "patient_phone": patient.phone_number if patient else "",
        })

    window_duration = int((org.booking_settings or {}).get("window_duration_minutes", 30))
    booking_quota = int((org.booking_settings or {}).get("booking_quota_per_window", 2))
    theoretical_capacity = int((org.booking_settings or {}).get("window_theoretical_capacity", 3))

    sessions: List[Dict[str, Any]] = []
    win_list = day_cfg.get("windows") or []
    if win_list:
        for w in win_list:
            w_start = parse_time_str(w.get("start"))
            w_end = parse_time_str(w.get("end"))
            if w_start and w_end:
                sessions.append({"session_type": w.get("name", "session").lower(), "start": w_start, "end": w_end})
    else:
        m_start = parse_time_str(day_cfg.get("morningStart", "10:00 AM"))
        m_end = parse_time_str(day_cfg.get("morningEnd", "01:30 PM"))
        if m_start and m_end:
            sessions.append({"session_type": "morning", "start": m_start, "end": m_end})

        e_start = parse_time_str(day_cfg.get("eveningStart", "05:30 PM"))
        e_end = parse_time_str(day_cfg.get("eveningEnd", "08:30 PM"))
        if e_start and e_end:
            sessions.append({"session_type": "evening", "start": e_start, "end": e_end})

    from app.services.appointments.booking_service import get_future_capacity
    capacity = await get_future_capacity(db, org, org_id, target_date, doctor_id=doctor_id)
    available_labels = set(capacity.get("available_slots", []))

    slots: List[Dict[str, Any]] = []
    total_booked_count = 0
    assigned_appt_ids = set()

    for sess in sessions:
        sess_name = sess["session_type"]
        current_time = sess["start"]
        end_time = sess["end"]

        current_dt = datetime.combine(target_date, current_time).replace(tzinfo=tz)
        session_end_dt = datetime.combine(target_date, end_time).replace(tzinfo=tz)

        while current_dt + timedelta(minutes=window_duration) <= session_end_dt:
            slot_start_dt = current_dt
            slot_end_dt = slot_start_dt + timedelta(minutes=window_duration)
            time_label = format_time_label(slot_start_dt.time())
            end_label = format_time_label(slot_end_dt.time())
            window_label = f"{time_label} – {end_label}"

            window_appts: List[Dict[str, Any]] = []
            for p_appt in parsed_appts:
                if p_appt["appointment_id"] in assigned_appt_ids:
                    continue
                if p_appt["source"] == "walk_in":
                    continue
                is_match = slot_start_dt <= p_appt["start_dt"] < slot_end_dt

                if is_match:
                    window_appts.append(p_appt)
                    assigned_appt_ids.add(p_appt["appointment_id"])

            active_appts = [a for a in window_appts if a["status"] not in ("cancelled", "no_show")]
            booked_in_window = len(active_appts)
            total_booked_count += booked_in_window

            is_past = slot_start_dt < now_local
            is_full = booked_in_window >= booking_quota

            if is_past:
                window_state = "PAST"
            elif is_full:
                window_state = "CLOSED"
            elif booked_in_window == booking_quota - 1:
                window_state = "LIMITED"
            else:
                window_state = "OPEN"

            is_available = time_label in available_labels
            if not is_available and not is_past:
                window_state = "CLOSED"

            if is_past:
                status_type = "CLOSED"
            elif not is_available:
                status_type = "BOOKED"
            else:
                status_type = "AVAILABLE"

            stagger_minutes = min(booked_in_window * 10, 20)
            recommended_dt = slot_start_dt + timedelta(minutes=stagger_minutes)
            recommended_arrival = format_time_label(recommended_dt.time())

            lead_appt = active_appts[0] if active_appts else (window_appts[0] if window_appts else None)

            slots.append({
                "time_label": time_label,
                "window_label": window_label,
                "recommended_arrival": recommended_arrival,
                "session": sess_name,
                "start_time": slot_start_dt.isoformat(),
                "end_time": slot_end_dt.isoformat(),
                "is_available": is_available,
                "status_type": status_type,
                "window_state": window_state,
                "is_past": is_past,
                "booking_quota": booking_quota,
                "theoretical_capacity": theoretical_capacity,
                "booked_count": booked_in_window,
                "booked_patients": [
                    {
                        "appointment_id": a["appointment_id"],
                        "patient_name": a["patient_name"],
                        "patient_phone": a["patient_phone"],
                        "chief_complaint": a["chief_complaint"],
                        "status": a["status"],
                        "source": a["source"],
                        "payment_status": a["payment_status"],
                        "appointment_time": a["appointment_time"],
                    }
                    for a in active_appts
                ],
                "appointment_id": lead_appt["appointment_id"] if lead_appt else None,
                "patient_name": lead_appt["patient_name"] if lead_appt else None,
                "patient_phone": lead_appt["patient_phone"] if lead_appt else None,
                "chief_complaint": lead_appt["chief_complaint"] if lead_appt else None,
                "source": lead_appt["source"] if lead_appt else None,
                "payment_status": lead_appt["payment_status"] if lead_appt else None,
            })

            current_dt += timedelta(minutes=window_duration)

    for p_appt in parsed_appts:
        if p_appt["appointment_id"] in assigned_appt_ids:
            continue
        if p_appt["source"] == "walk_in":
            continue
        assigned_appt_ids.add(p_appt["appointment_id"])
        time_label = p_appt["appointment_time"] or format_time_label(p_appt["start_dt"].time())
        existing_slot = next((s for s in slots if s["time_label"] == time_label), None)
        if existing_slot:
            existing_slot["booked_count"] = (existing_slot.get("booked_count") or 0) + 1
            existing_slot["booked_patients"].append({
                "appointment_id": p_appt["appointment_id"],
                "patient_name": p_appt["patient_name"],
                "patient_phone": p_appt["patient_phone"],
                "chief_complaint": p_appt["chief_complaint"],
                "status": p_appt["status"],
                "source": p_appt["source"],
                "payment_status": p_appt["payment_status"],
                "appointment_time": p_appt["appointment_time"],
            })
            if existing_slot["booked_count"] >= (existing_slot.get("booking_quota") or 2):
                existing_slot["window_state"] = "CLOSED"
                existing_slot["status_type"] = "BOOKED"
            continue

        end_time_calc = p_appt["end_dt"]
        window_label = f"{time_label} – {format_time_label(end_time_calc.time())}"
        status = p_appt["status"]
        is_available = status in ("cancelled", "no_show")
        if not is_available:
            total_booked_count += 1
        status_type = (
            "COMPLETED" if status == "completed" else (
                "IN_PROGRESS" if status == "in_progress" else (
                    "CANCELLED" if status == "cancelled" else "BOOKED"
                )
            )
        )
        appt_time = p_appt["start_dt"].time()
        sess = "overtime"
        for s_item in sessions:
            if s_item["start"] <= appt_time <= s_item["end"]:
                sess = s_item["session_type"]
                break

        is_appt_past = p_appt["start_dt"] < now_local
        slots.append({
            "time_label": time_label,
            "window_label": window_label,
            "recommended_arrival": time_label,
            "session": sess,
            "start_time": p_appt["start_dt"].isoformat(),
            "end_time": p_appt["end_dt"].isoformat(),
            "is_available": is_available,
            "status_type": status_type,
            "window_state": "PAST" if is_appt_past else "CLOSED",
            "is_past": is_appt_past,
            "booking_quota": booking_quota,
            "theoretical_capacity": theoretical_capacity,
            "booked_count": 1,
            "booked_patients": [
                {
                    "appointment_id": p_appt["appointment_id"],
                    "patient_name": p_appt["patient_name"],
                    "patient_phone": p_appt["patient_phone"],
                    "chief_complaint": p_appt["chief_complaint"],
                    "status": p_appt["status"],
                    "source": p_appt["source"],
                    "payment_status": p_appt["payment_status"],
                    "appointment_time": p_appt["appointment_time"],
                }
            ],
            "appointment_id": p_appt["appointment_id"],
            "patient_name": p_appt["patient_name"],
            "patient_phone": p_appt["patient_phone"],
            "chief_complaint": p_appt["chief_complaint"],
            "source": p_appt["source"],
            "payment_status": p_appt["payment_status"],
            "is_overtime": True,
        })

    slots.sort(key=lambda s: s["start_time"])

    return {
        "org_id": str(org_id),
        "target_date": target_date.isoformat(),
        "is_open": True,
        "slot_duration_minutes": slot_duration,
        "slot_buffer_minutes": slot_buffer,
        "window_duration_minutes": window_duration,
        "booking_quota_per_window": booking_quota,
        "max_daily_patients": max_daily,
        "total_booked": total_booked_count,
        "is_capacity_reached": total_booked_count >= max_daily,
        "slots": slots,
    }


async def lookup_patients(db: AsyncSession, org_id: UUID, phone: str, name: str):
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Clinic organization not found")
    normalized = normalize_phone_e164(phone, getattr(org, "country_code", None) or "IN")
    if not normalized.is_valid:
        return []
    parsed = phonenumbers.parse(normalized.e164_phone, None)
    national = phonenumbers.national_significant_number(parsed)
    candidates = {normalized.e164_phone.lstrip("+"), national, f"0{national}"}
    escaped_name = name.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    rows = (await db.execute(
        select(Patient.id, Patient.first_name, Patient.last_name, Patient.phone_number, Patient.dob, Patient.medical_history)
        .where(
            Patient.org_id == org_id,
            func.regexp_replace(Patient.phone_number, "[^0-9]", "", "g").in_(candidates),
            func.concat(Patient.first_name, " ", Patient.last_name).ilike(f"%{escaped_name}%", escape="\\"),
        )
        .order_by(Patient.created_at.desc(), Patient.id)
        .limit(10)
    )).all()
    if not rows:
        return []
    latest = (await db.execute(
        select(Appointment.patient_id, Appointment.status, Appointment.display_token, Appointment.chief_complaint)
        .where(Appointment.org_id == org_id, Appointment.patient_id.in_([row.id for row in rows]))
        .distinct(Appointment.patient_id)
        .order_by(Appointment.patient_id, Appointment.start_time.desc(), Appointment.id.desc())
    )).all()
    latest_by_patient = {row.patient_id: row for row in latest}
    result = []
    for patient in rows:
        visit = latest_by_patient.get(patient.id)
        priority_reason = None
        if visit and visit.status == "skipped":
            priority_reason = "Stepped Out for Tests"
        elif visit and ((visit.display_token or "").startswith("R") or "report" in (visit.chief_complaint or "").lower()):
            priority_reason = "Comeback for Lab Reports"
        dob = getattr(patient, "dob", None)
        history = getattr(patient, "medical_history", None) or {}
        reported = history.get("reported_age") or {}
        result.append({"id": str(patient.id), "name": f"{patient.first_name} {patient.last_name}".strip(), "phone": patient.phone_number, "priority_reason": priority_reason, "dob": dob.isoformat() if dob else None, "gender": getattr(patient, "gender", None), "blood_group": getattr(patient, "blood_group", None), "address": getattr(patient, "address", None), "reported_age": reported.get("value"), "age_unit": reported.get("unit")})
    return result


async def count_leave_collisions(db: AsyncSession, org_id: UUID, start_date: date, end_date: date):
    if end_date < start_date or (end_date - start_date).days >= 366:
        raise HTTPException(422, "Choose an ordered date range of no more than 366 days")
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Clinic organization not found")
    tz = clinic_timezone(org.timezone)
    start = datetime.combine(start_date, time.min, tzinfo=tz)
    end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)
    count = await db.scalar(select(func.count()).select_from(Appointment).where(
        Appointment.org_id == org_id,
        Appointment.start_time >= start,
        Appointment.start_time < end,
        Appointment.status.in_(("scheduled", "arrived", "in_progress", "skipped")),
    ))
    return {"count": count or 0}


async def update_appointment_status_and_notes(
    db: AsyncSession,
    appointment_id: UUID,
    status_update: AppointmentStatusUpdate
) -> Optional[Appointment]:
    query = select(Appointment).where(Appointment.id == appointment_id)
    result = await db.execute(query)
    appt = result.scalar_one_or_none()
    if not appt:
        return None

    appt.status = status_update.status
    if status_update.chief_complaint is not None:
        appt.chief_complaint = status_update.chief_complaint
    if status_update.doctor_notes is not None:
        appt.doctor_notes = status_update.doctor_notes

    if status_update.prescriptions and appt.patient_id:
        p_query = select(Patient).where(Patient.id == appt.patient_id)
        p_res = await db.execute(p_query)
        patient = p_res.scalar_one_or_none()

        if patient:
            tz_name = await get_org_timezone(db, appt.org_id)
            tz = ZoneInfo(tz_name)
            today_str = datetime.now(tz).strftime("%Y-%m-%d")
            med_hist = dict(patient.medical_history or {})
            existing_rx = list(med_hist.get("prescriptions", []))

            for rx_str in status_update.prescriptions:
                rx_item = {
                    "drug": rx_str,
                    "prescribedOn": today_str,
                    "courseDuration": "As prescribed"
                }
                if not any(x.get("drug") == rx_str for x in existing_rx if isinstance(x, dict)):
                    existing_rx.append(rx_item)

            med_hist["prescriptions"] = existing_rx
            med_hist["last_visit_date"] = appt.start_time.strftime("%Y-%m-%d")
            patient.medical_history = med_hist

    await db.flush()
    return appt


async def get_appointments_by_org(
    db: AsyncSession, org_id: UUID
) -> List[Appointment]:
    org = await db.get(Organization, org_id)
    tz_name = resolve_org_timezone(org)
    await auto_mark_clinic_expired_no_shows(db, org_id=org_id, tz_name=tz_name)

    query = (
        select(Appointment)
        .where(Appointment.org_id == org_id)
        .order_by(Appointment.start_time.asc())
    )
    result = await db.execute(query)
    return list(result.scalars().all())
