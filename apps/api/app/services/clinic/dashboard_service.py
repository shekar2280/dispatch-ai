from app.core.clinic_config import require_clinic_booking_integer
from app.core.clinic_config import require_clinic_timezone
from app.services.patients.notes_service import update_clinic_doctor_notes
from app.services.billing.payment_service import get_clinic_revenue_data, list_visit_payment_receipts_service
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
from uuid import UUID
import zoneinfo
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, desc, or_, and_, exists
from sqlalchemy.orm.attributes import flag_modified
from fastapi import HTTPException, status
from sqlalchemy import case, cast, Integer, String, Numeric

from app.models.organization import Organization
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.user import User
from app.models.clinic_membership import ClinicMembership
from app.models.call_session import VoiceCallSession
from app.models.payment_receipt import PaymentReceipt


async def get_clinic_live_dashboard(db: AsyncSession, org_id: UUID) -> Dict[str, Any]:
    clinic_org = await db.get(Organization, org_id)
    if not clinic_org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic organization not found",
        )

    tz_str = require_clinic_timezone(clinic_org)
    tz = zoneinfo.ZoneInfo(tz_str)
    today_local = datetime.now(tz).date()

    appts_query = (
        select(Appointment, Patient)
        .outerjoin(Patient, Appointment.patient_id == Patient.id)
        .where(
            Appointment.org_id == org_id,
            Appointment.appointment_date == today_local,
            Appointment.status != "cancelled",
        )
        .order_by(Appointment.start_time.asc())
    )
    res = await db.execute(appts_query)
    rows = res.all()

    all_today: List[Dict[str, Any]] = []
    active_patient: Optional[Dict[str, Any]] = None
    next_patient: Optional[Dict[str, Any]] = None
    waiting_queue: List[Dict[str, Any]] = []

    completed_count = 0
    no_show_count = 0
    today_revenue_collected = 0
    today_revenue_pending = 0
    for appt, patient in rows:
        p_name = f"{patient.first_name} {patient.last_name}".strip() if patient else ""
        if (
            not p_name
            and appt.booking_metadata
            and isinstance(appt.booking_metadata, dict)
        ):
            p_name = (
                appt.booking_metadata.get("patient_name")
                or appt.booking_metadata.get("caller_name")
                or ""
            )
        if not p_name:
            p_name = f"Patient {appt.display_token or appt.token_number or ''}".strip()
        p_phone = (patient.phone_number if patient else "") or (
            appt.booking_metadata.get("caller_phone")
            if appt.booking_metadata and isinstance(appt.booking_metadata, dict)
            else ""
        )
        med_hist = (
            patient.medical_history
            if patient and isinstance(patient.medical_history, dict)
            else {}
        )
        allergies = med_hist.get("allergies", [])
        chronic = med_hist.get("chronic_conditions", [])

        fee_val = appt.fee or (clinic_org.consultation_fee if clinic_org else 0) or 0
        if appt.payment_status == "paid":
            today_revenue_collected += fee_val
        else:
            today_revenue_pending += fee_val

        if appt.status == "completed":
            completed_count += 1
        elif appt.status in ("no_show", "cancelled"):
            no_show_count += 1

        start_time_iso = appt.start_time.isoformat() if appt.start_time else ""
        end_time_iso = appt.end_time.isoformat() if appt.end_time else ""

        item = {
            "appointment_id": str(appt.id),
            "patient_id": str(appt.patient_id) if appt.patient_id else "",
            "patient_name": p_name,
            "patient_phone": p_phone,
            "appointment_time": appt.appointment_time
            or (
                appt.start_time.strftime("%I:%M %p")
                if appt.start_time
                else appt.display_token or "Walk-in"
            ),
            "start_time": start_time_iso,
            "end_time": end_time_iso,
            "status": appt.status,
            "chief_complaint": appt.chief_complaint or "General Consultation",
            "doctor_notes": appt.doctor_notes or "",
            "fee": fee_val,
            "payment_status": appt.payment_status or "pending",
            "source": appt.source or "walk_in",
            "gender": patient.gender if patient and patient.gender else "N/A",
            "blood_group": (
                patient.blood_group if patient and patient.blood_group else "N/A"
            ),
            "display_token": appt.display_token
            or (f"T-{appt.token_number}" if appt.token_number else ""),
            "age": (
                f"{today_local.year - patient.dob.year - ((today_local.month, today_local.day) < (patient.dob.month, patient.dob.day))} yrs"
                if patient and patient.dob
                else ""
            ),
            "dob": patient.dob.isoformat() if patient and patient.dob else "",
            "recent_diagnosis": patient.recent_diagnosis if patient else "",
            "allergies": allergies,
            "chronic_conditions": chronic,
        }
        all_today.append(item)

        if appt.status == "in_progress" and active_patient is None:
            active_patient = item
        elif appt.status in ("arrived", "waiting"):
            waiting_queue.append(item)

    if active_patient is None and len(waiting_queue) > 0:
        active_patient = waiting_queue[0]
        next_patient = waiting_queue[1] if len(waiting_queue) > 1 else None
    elif active_patient is not None:
        next_patient = waiting_queue[0] if len(waiting_queue) > 0 else None

    if active_patient:
        active_patient["previous_visits"] = []

    emergencies_query = (
        select(VoiceCallSession)
        .where(
            VoiceCallSession.org_id == org_id,
            func.lower(VoiceCallSession.triage_status) == "emergency",
            VoiceCallSession.call_outcome != "resolved",
        )
        .order_by(VoiceCallSession.start_time.desc())
        .limit(15)
    )
    emerg_res = await db.execute(emergencies_query)
    emerg_rows = emerg_res.scalars().all()

    emergency_callbacks = []
    for call in emerg_rows:
        emergency_callbacks.append(
            {
                "session_id": str(call.id),
                "caller_phone": call.caller_phone or "",
                "caller_name": call.caller_name or "Emergency Caller",
                "chief_complaint": call.chief_complaint
                or "Acute emergency reported to Voice Assistant",
                "full_transcript": "",
                "start_time": call.start_time.isoformat() if call.start_time else "",
                "duration_seconds": call.duration_seconds or 0,
                "audio_recording_url": call.audio_recording_url,
                "call_outcome": call.call_outcome or "emergency",
            }
        )

    return {
        "doctor_name": clinic_org.lead_doctor_name or "",
        "clinic_name": clinic_org.name,
        "specialty": clinic_org.clinic_specialty or "",
        "today_date": today_local.isoformat(),
        "today_date_label": today_local.strftime("%A, %d %B"),
        "summary": {
            "total_today": len(all_today),
            "completed_count": completed_count,
            "in_room_count": (
                1
                if (active_patient and active_patient.get("status") == "in_progress")
                else 0
            ),
            "waiting_count": len(waiting_queue),
            "no_show_count": no_show_count,
            "revenue_collected": today_revenue_collected,
            "revenue_pending": today_revenue_pending,
        },
        "active_patient": active_patient,
        "next_patient": next_patient,
        "waiting_queue": waiting_queue,
        "emergency_callbacks": emergency_callbacks,
    }



async def get_clinic_patients_service(
    db: AsyncSession, org_id: UUID, limit: int = 50, offset: int = 0, search: str = "", patient_id: Optional[UUID] = None,
    include_clinical_search: bool = False,
) -> List[Dict[str, Any]]:
    query = select(Patient).where(Patient.org_id == org_id)
    if patient_id:
        query = query.where(Patient.id == patient_id)
    for token in search.split():
        terms = [
            func.concat(Patient.first_name, " ", Patient.last_name).icontains(token, autoescape=True),
            Patient.phone_number.icontains(token, autoescape=True),
        ]
        if include_clinical_search:
            terms.append(func.coalesce(Patient.recent_diagnosis, "").icontains(token, autoescape=True))
        query = query.where(or_(*terms))
    patients = (await db.execute(query.order_by(Patient.created_at.desc(), Patient.id).limit(limit).offset(offset))).scalars().all()
    if not patients:
        return []
    all_appts = (await db.execute(
        select(Appointment).where(Appointment.org_id == org_id, Appointment.patient_id.in_([patient.id for patient in patients]))
        .order_by(Appointment.start_time.desc())
    )).scalars().all()

    appts_by_patient: Dict[UUID, List[Appointment]] = {}
    for a in all_appts:
        appts_by_patient.setdefault(a.patient_id, []).append(a)

    result = []
    for p in patients:
        p_appts = appts_by_patient.get(p.id, [])
        total_visits = len(p_appts)
        last_visit = "Never"
        if p_appts:
            latest = p_appts[0]
            if latest.appointment_date:
                last_visit = latest.appointment_date.strftime("%d %b %Y")
            elif latest.start_time:
                last_visit = latest.start_time.strftime("%d %b %Y")

        hist = p.medical_history if isinstance(p.medical_history, dict) else {}
        allergies = hist.get("allergies", "")
        chronic_conditions = hist.get("chronic_conditions", "")

        notes = []
        for a in p_appts:
            if (
                a.doctor_notes
                and a.doctor_notes.strip()
                and a.doctor_notes.strip() not in notes
            ):
                notes.append(a.doctor_notes.strip())
        for n in hist.get("notes", []):
            if n and str(n).strip() and str(n).strip() not in notes:
                notes.append(str(n).strip())

        age_gender = "Adult"
        if p.dob:
            age = (datetime.utcnow().date() - p.dob).days // 365
            gender_letter = (p.gender or "M")[0].upper()
            age_gender = f"{age} / {gender_letter}"
        elif p.gender:
            age_gender = p.gender

        result.append(
            {
                "id": str(p.id),
                "name": f"{p.first_name} {p.last_name}".strip(),
                "phone": p.phone_number,
                "dob": p.dob.isoformat() if p.dob else None,
                "gender": p.gender or "",
                "blood_group": p.blood_group or "",
                "age_gender": age_gender,
                "last_visit": last_visit,
                "total_visits": total_visits,
                "allergies": allergies,
                "chronic_conditions": chronic_conditions,
                "recent_diagnosis": p.recent_diagnosis or "",
                "notes": notes,
            }
        )
    return result


async def save_patient_ehr_note_service(
    db: AsyncSession,
    org_id: UUID,
    patient_id: UUID,
    note: str,
) -> Dict[str, Any]:
    patient = await db.get(Patient, patient_id)
    if not patient or patient.org_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic patient not found",
        )

    clean_note = note.strip()
    if clean_note:
        hist = dict(patient.medical_history or {})
        existing = list(hist.get("notes") or [])
        if clean_note not in existing:
            existing.insert(0, clean_note)
            hist["notes"] = existing
            hist["latest_doctor_notes"] = clean_note
            patient.medical_history = hist

        latest_appt_res = await db.execute(
            select(Appointment)
            .where(Appointment.org_id == org_id, Appointment.patient_id == patient_id)
            .order_by(Appointment.start_time.desc())
            .limit(1)
        )
        latest_appt = latest_appt_res.scalar_one_or_none()
        if latest_appt and not latest_appt.doctor_notes:
            latest_appt.doctor_notes = clean_note

        await db.commit()
        await db.refresh(patient)

    return {"status": "saved", "patient_id": str(patient.id), "note": clean_note}


async def resolve_clinic_emergency_callback(
    db: AsyncSession,
    org_id: UUID,
    session_id: UUID,
) -> Dict[str, Any]:
    call = await db.get(VoiceCallSession, session_id)
    if not call or call.org_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voice call session not found",
        )

    call.call_outcome = "resolved"
    await db.commit()
    return {"session_id": str(call.id), "status": "resolved"}


async def get_clinic_analytics_data(
    db: AsyncSession, org_id: UUID, period: str = "month"
) -> Dict[str, Any]:
    clinic_org = await db.get(Organization, org_id)
    if not clinic_org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic organization not found",
        )
    tz_str = require_clinic_timezone(clinic_org)
    tz = zoneinfo.ZoneInfo(tz_str)
    now_local = datetime.now(tz)
    today = now_local.date()
    if period == "week":
        start_date = today - timedelta(days=7)
    elif period == "year":
        start_date = today - timedelta(days=365)
    else:
        period = "month"
        start_date = today - timedelta(days=30)

    stats_query = select(
        func.count(Appointment.id).label("total"),
        func.sum(cast(Appointment.status == "completed", Integer)).label("completed"),
        func.sum(cast(Appointment.status.in_(["no_show", "cancelled"]), Integer)).label(
            "no_shows"
        ),
        func.sum(cast(Appointment.source == "ai_voice", Integer)).label("voice_ai"),
        func.sum(cast(Appointment.source == "walk_in", Integer)).label("walk_in"),
        func.sum(
            case(
                (
                    Appointment.booking_metadata["payment_status"].astext == "paid",
                    cast(
                        func.coalesce(
                            Appointment.booking_metadata["fee"].astext,
                            str(clinic_org.consultation_fee or 0),
                        ),
                        Numeric,
                    ),
                ),
                else_=0,
            )
        ).label("revenue"),
    ).where(Appointment.org_id == org_id, Appointment.appointment_date >= start_date)

    stats_res = await db.execute(stats_query)
    stats_row = stats_res.first()

    total_period = stats_row.total or 0
    completed_period = stats_row.completed or 0
    no_show_period = stats_row.no_shows or 0
    voice_ai_period = stats_row.voice_ai or 0
    walkin_period = stats_row.walk_in or 0
    total_revenue = float(stats_row.revenue or 0)
    evaluated = completed_period + no_show_period
    no_show_rate = (
        round((no_show_period / evaluated * 100), 1) if evaluated > 0 else 0.0
    )
    completion_rate = (
        round((completed_period / total_period * 100), 1) if total_period > 0 else 0.0
    )
    pat_query = select(func.count(Patient.id)).where(Patient.org_id == org_id)
    total_patients_registered = (await db.execute(pat_query)).scalar() or 0
    trends = []
    if period in ("week", "month"):
        days_back = 6 if period == "week" else 29
        trend_query = (
            select(
                Appointment.appointment_date.label("appointment_date"),
                func.count(Appointment.id).label("total"),
                func.sum(cast(Appointment.status == "completed", Integer)).label(
                    "completed"
                ),
                func.sum(
                    cast(Appointment.status.in_(["no_show", "cancelled"]), Integer)
                ).label("no_shows"),
            )
            .where(
                Appointment.org_id == org_id,
                Appointment.appointment_date >= today - timedelta(days=days_back),
            )
            .group_by(Appointment.appointment_date)
        )

        trend_res = await db.execute(trend_query)
        trend_map = {row.appointment_date: row for row in trend_res.all()}

        for day_i in range(days_back, -1, -1):
            d = today - timedelta(days=day_i)
            row = trend_map.get(d)
            trends.append(
                {
                    "date": d.isoformat(),
                    "day_label": (
                        d.strftime("%a")
                        if period == "week"
                        else (
                            d.strftime("%d %b") if day_i % 4 == 0 or day_i == 0 else ""
                        )
                    ),
                    "total": row.total if row else 0,
                    "completed": row.completed if row else 0,
                    "no_show": row.no_shows if row else 0,
                }
            )
    else:
        appts_query = select(Appointment.appointment_date.label("appointment_date"), Appointment.status).where(
            Appointment.org_id == org_id, Appointment.appointment_date >= start_date
        )
        appts = (await db.execute(appts_query)).all()
        for month_i in range(11, -1, -1):
            m_year = today.year
            m_month = today.month - month_i
            while m_month <= 0:
                m_month += 12
                m_year -= 1
            month_appts = [
                a
                for a in appts
                if a.appointment_date
                and a.appointment_date.year == m_year
                and a.appointment_date.month == m_month
            ]
            m_date = date(m_year, m_month, 1)
            trends.append(
                {
                    "date": m_date.isoformat(),
                    "day_label": m_date.strftime("%b"),
                    "total": len(month_appts),
                    "completed": sum(1 for a in month_appts if a.status == "completed"),
                    "no_show": sum(
                        1 for a in month_appts if a.status in ("no_show", "cancelled")
                    ),
                }
            )
    max_daily = require_clinic_booking_integer(clinic_org, "max_daily_patients")
    distinct_days = len([t for t in trends if t["total"] > 0]) or 1
    avg_daily_booked = round(total_period / distinct_days, 1)
    utilization_pct = min(100.0, round((avg_daily_booked / max_daily * 100), 1))
    return {
        "org_id": str(org_id),
        "clinic_name": clinic_org.name,
        "lead_doctor_name": clinic_org.lead_doctor_name,
        "period": period,
        "total_appointments": total_period,
        "completed_count": completed_period,
        "completion_rate_pct": completion_rate,
        "no_show_rate_pct": no_show_rate,
        "slot_utilization_pct": utilization_pct,
        "total_patients_registered": total_patients_registered,
        "total_revenue": total_revenue,
        "upi_revenue": 0,  # Stubs for brevity, can be aggregated later if needed
        "cash_revenue": 0,
        "source_breakdown": {
            "ai_voice": voice_ai_period,
            "walk_in": walkin_period,
            "manual": max(0, total_period - voice_ai_period - walkin_period),
        },
        "daily_trends": trends,
        "total_appointments_30d": total_period,
        "completed_count_30d": completed_period,
    }




async def list_clinic_staff_service(db: AsyncSession, org_id: UUID) -> List[Dict[str, Any]]:
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic organization not found",
        )

    users_res = await db.execute(
        select(User).where(User.org_id == org_id, User.is_active == True)
    )
    active_users = users_res.scalars().all()
    user_map = {u.id: u for u in active_users}

    memberships_res = await db.execute(
        select(ClinicMembership).where(ClinicMembership.org_id == org_id)
    )
    memberships = memberships_res.scalars().all()
    membership_user_ids = {m.user_id for m in memberships}

    seen_emails = set()
    staff_list: List[Dict[str, Any]] = []

    for m in memberships:
        u = user_map.get(m.user_id)
        if not u:
            u_res = await db.get(User, m.user_id)
            if u_res:
                u = u_res
        if not u:
            if m.invited_email:
                seen_emails.add(m.invited_email.lower().strip())
                staff_list.append({
                    "id": None, "email": m.invited_email,
                    "full_name": m.display_name or "Receptionist", "role": m.role,
                    "status": m.status,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                    "revoked_at": m.revoked_at.isoformat() if m.revoked_at else None,
                })
            continue

        u_email = u.email.lower().strip()
        seen_emails.add(u_email)

        staff_list.append({
            "id": str(u.id),
            "email": u.email,
            "full_name": m.display_name or u.full_name,
            "role": m.role,
            "status": m.status,
            "total_consultations": m.total_consultations,
            "total_minutes_worked": m.total_minutes_worked,
            "total_walkins_triaged": m.total_walkins_triaged,
            "total_revenue_collected": float(m.total_revenue_collected or 0),
            "joined_at": m.joined_at.isoformat() if m.joined_at else None,
            "revoked_at": m.revoked_at.isoformat() if m.revoked_at else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        })

    for pending in org.authorized_staff:
        p_email = pending.get("email", "").lower().strip()
        if p_email and p_email not in seen_emails:
            staff_list.append({
                "id": None,
                "email": pending.get("email"),
                "full_name": pending.get("full_name") or "Invited Staff",
                "role": pending.get("role", "receptionist"),
                "status": "invited",
                "total_consultations": 0,
                "total_minutes_worked": 0,
                "total_walkins_triaged": 0,
                "total_revenue_collected": 0.0,
                "joined_at": None,
                "revoked_at": None,
                "created_at": pending.get("added_at"),
            })

    return staff_list


async def add_clinic_staff_service(
    db: AsyncSession,
    org_id: UUID,
    email: str,
    full_name: str,
    role: str = "receptionist",
) -> Dict[str, Any]:
    if role != "receptionist":
        raise HTTPException(status_code=400, detail="Only receptionist invitations are supported for this clinic.")
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic organization not found",
        )

    clean_email = email.lower().strip()
    if not clean_email or "@" not in clean_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A valid email address is required.",
        )

    existing_user_res = await db.execute(
        select(User).where(func.lower(User.email) == clean_email)
    )
    existing_user = existing_user_res.scalar_one_or_none()
    if existing_user and existing_user.role in ("admin", "doctor"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This email belongs to a clinic doctor or administrator and cannot be registered as front desk staff.",
        )

    authorized = list(org.authorized_staff)
    existing = [s for s in authorized if s.get("email", "").lower().strip() == clean_email]
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This email is already on your staff whitelist.",
        )

    target_user_id = existing_user.id if existing_user else None
    membership = await db.scalar(
        select(ClinicMembership).where(
            ClinicMembership.org_id == org_id,
            or_(
                ClinicMembership.user_id == target_user_id if target_user_id else False,
                func.lower(ClinicMembership.invited_email) == clean_email,
            ),
        )
    )
    if not membership:
        membership = ClinicMembership(
            org_id=org_id,
            user_id=target_user_id,
            invited_email=clean_email,
            role=role or "receptionist",
            display_name=full_name.strip() or "Front Desk Staff",
            status="active" if target_user_id else "invited",
        )
        db.add(membership)
    else:
        membership.role = role or "receptionist"
        membership.display_name = full_name.strip() or membership.display_name
        membership.status = "active" if target_user_id else "invited"
        membership.revoked_at = None
        db.add(membership)

    authorized.append({
        "email": clean_email,
        "full_name": full_name.strip() or "Front Desk Staff",
        "role": role or "receptionist",
        "added_at": datetime.utcnow().isoformat(),
    })
    org.authorized_staff = authorized
    await db.commit()

    return {
        "success": True,
        "email": clean_email,
        "full_name": full_name.strip() or "Front Desk Staff",
        "role": role or "receptionist",
        "status": membership.status,
    }


async def delete_supabase_auth_user(user_id: Optional[str], email: Optional[str] = None):
    import httpx
    from app.core.config import settings
    supabase_url = settings.SUPABASE_URL or settings.NEXT_PUBLIC_SUPABASE_URL
    service_key = settings.SUPABASE_SERVICE_ROLE_KEY
    if not supabase_url or not service_key:
        return
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
    }
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            if user_id:
                await client.delete(f"{supabase_url.rstrip('/')}/auth/v1/admin/users/{user_id}", headers=headers)
            elif email:
                res = await client.get(f"{supabase_url.rstrip('/')}/auth/v1/admin/users", headers=headers, params={"page": 1, "per_page": 50})
                if res.status_code == 200:
                    users_data = res.json().get("users", [])
                    for u in users_data:
                        if u.get("email", "").lower().strip() == email.lower().strip():
                            await client.delete(f"{supabase_url.rstrip('/')}/auth/v1/admin/users/{u['id']}", headers=headers)
                            break
        except Exception:
            pass


async def update_clinic_staff_service(
    db: AsyncSession, org_id: UUID, email: str,
    full_name: Optional[str] = None, role: Optional[str] = "receptionist",
) -> Dict[str, Any]:
    if role not in (None, "receptionist"):
        raise HTTPException(status_code=400, detail="Only receptionist access is supported.")
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Clinic organization not found")
    clean_email = email.lower().strip()
    user = await db.scalar(select(User).where(func.lower(User.email) == clean_email))
    memberships = list((await db.execute(select(ClinicMembership).where(
        ClinicMembership.org_id == org_id,
        or_(ClinicMembership.user_id == user.id if user else False,
            func.lower(ClinicMembership.invited_email) == clean_email),
    ))).scalars().all())
    if any(m.role != "receptionist" for m in memberships):
        raise HTTPException(status_code=400, detail="Only receptionist details can be edited here.")
    authorized = [dict(entry) for entry in org.authorized_staff]
    entries = [entry for entry in authorized if entry.get("email", "").lower().strip() == clean_email]
    if not memberships and not entries:
        raise HTTPException(status_code=404, detail="Receptionist not found in this clinic")
    new_name = (full_name or "").strip()
    if new_name:
        for membership in memberships:
            membership.display_name = new_name
        for entry in entries:
            entry["full_name"] = new_name
    org.authorized_staff = authorized
    await db.commit()
    return {"success": True, "email": clean_email, "full_name": new_name, "role": "receptionist"}


async def remove_clinic_staff_service(
    db: AsyncSession, org_id: UUID, email: str,
) -> Dict[str, Any]:
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Clinic organization not found")
    clean_email = email.lower().strip()
    user = await db.scalar(select(User).where(func.lower(User.email) == clean_email))
    memberships = list((await db.execute(select(ClinicMembership).where(
        ClinicMembership.org_id == org_id,
        or_(ClinicMembership.user_id == user.id if user else False,
            func.lower(ClinicMembership.invited_email) == clean_email),
    ))).scalars().all())
    if any(m.role in ("admin", "doctor") for m in memberships) or (
        user and user.org_id == org_id and user.role in ("admin", "doctor")
    ):
        raise HTTPException(status_code=400, detail="Cannot revoke the clinic owner's access.")
    authorized = list(org.authorized_staff)
    matching = [entry for entry in authorized if entry.get("email", "").lower().strip() == clean_email]
    if not memberships and not matching:
        raise HTTPException(status_code=404, detail="Receptionist not found in this clinic")
    org.authorized_staff = [entry for entry in authorized if entry not in matching]
    for membership in memberships:
        membership.status = "revoked"
        membership.revoked_at = datetime.now(zoneinfo.ZoneInfo("UTC"))
    # The Google identity and other clinic memberships remain intact.
    if user and user.org_id == org_id:
        user.org_id = None
    await db.commit()
    return {"success": True, "email": clean_email}


async def claim_staff_account_service(
    db: AsyncSession,
    user_id: UUID,
    email: str,
    full_name: str,
) -> Dict[str, Any]:
    clean_email = email.lower().strip()

    existing_user = await db.get(User, user_id)
    if not existing_user:
        user_by_email = await db.execute(
            select(User).where(func.lower(User.email) == clean_email)
        )
        existing_user = user_by_email.scalar_one_or_none()
        if existing_user and existing_user.id != user_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This email is already linked to another account.",
            )

    if existing_user and not existing_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated.",
        )

    if existing_user and existing_user.role in ("doctor", "admin") and existing_user.org_id:
        membership = await db.scalar(
            select(ClinicMembership).where(
                ClinicMembership.org_id == existing_user.org_id,
                ClinicMembership.user_id == existing_user.id,
            )
        )
        if membership and membership.status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This clinic membership is not active.",
            )
        if not membership:
            membership = ClinicMembership(
                org_id=existing_user.org_id,
                user_id=existing_user.id,
                role=existing_user.role,
                display_name=existing_user.full_name or full_name,
                status="active",
            )
            db.add(membership)
            await db.commit()
        org = await db.get(Organization, existing_user.org_id)
        return {
            "org_id": str(existing_user.org_id),
            "role": existing_user.role,
            "clinic_name": org.name if org else "Private Practice",
            "full_name": existing_user.full_name,
        }

    active_membership = await db.scalar(
        select(ClinicMembership).where(
            ClinicMembership.user_id == (existing_user.id if existing_user else user_id),
            ClinicMembership.status == "active",
        )
    )
    if active_membership:
        org = await db.get(Organization, active_membership.org_id)
        return {
            "org_id": str(active_membership.org_id),
            "role": active_membership.role,
            "clinic_name": org.name if org else "Clinic Practice",
            "full_name": (existing_user.full_name if existing_user else full_name) or "Staff Member",
        }

    membership_invite = await db.scalar(
        select(ClinicMembership).where(
            func.lower(ClinicMembership.invited_email) == clean_email,
            ClinicMembership.status == "invited",
        )
    )

    matched_org = None
    matched_role = "receptionist"
    matched_name = full_name

    if membership_invite:
        matched_org = await db.get(Organization, membership_invite.org_id)
        matched_role = membership_invite.role or "receptionist"
        matched_name = membership_invite.display_name or full_name
    else:
        orgs_res = await db.execute(select(Organization))
        all_orgs = orgs_res.scalars().all()
        matches = []
        for org in all_orgs:
            for s in org.authorized_staff:
                if s.get("email", "").lower().strip() == clean_email:
                    matches.append((org, s))

        if not matches:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your email is not on any clinic's authorized team list. Please contact your doctor.",
            )
        if len(matches) > 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This email has invitations from multiple clinics. Ask the clinics to resolve the duplicate invitation.",
            )
        matched_org, invitation = matches[0]
        matched_role = invitation.get("role", "receptionist")
        matched_name = invitation.get("full_name") or full_name

    if not matched_org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic organization not found for invitation.",
        )

    target_user = existing_user
    if target_user:
        target_user.org_id = matched_org.id
        target_user.role = matched_role
        target_user.full_name = matched_name or target_user.full_name
        target_user.is_active = True
        db.add(target_user)
    else:
        target_user = User(
            id=user_id,
            org_id=matched_org.id,
            email=clean_email,
            full_name=matched_name or "Front Desk Staff",
            role=matched_role,
            is_active=True,
        )
        db.add(target_user)

    membership = await db.scalar(
        select(ClinicMembership).where(
            ClinicMembership.org_id == matched_org.id,
            ClinicMembership.user_id == target_user.id,
        )
    )
    if not membership and membership_invite:
        membership = membership_invite
        membership.user_id = target_user.id
    if not membership:
        membership = ClinicMembership(
            org_id=matched_org.id,
            user_id=target_user.id,
            role=matched_role,
            display_name=matched_name or target_user.full_name,
            status="active",
        )
        db.add(membership)
    else:
        membership.role = matched_role
        membership.display_name = matched_name or membership.display_name
        membership.status = "active"
        membership.revoked_at = None
        db.add(membership)

    await db.commit()

    return {
        "org_id": str(matched_org.id),
        "role": matched_role,
        "clinic_name": matched_org.name,
        "full_name": target_user.full_name,
    }
