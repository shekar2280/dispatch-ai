from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from app.models.patient import Patient
from app.models.appointment import Appointment
from app.models.user import User


async def evaluate_returning_patient_context(
    db: AsyncSession,
    org_id: UUID,
    caller_phone: str,
    session_known_name: Optional[str] = None,
    session_known_dob: Optional[date] = None,
    locked_patient_id: Optional[str] = None,
) -> Dict[str, Any]:
    clean_phone = caller_phone.strip()

    if locked_patient_id:
        try:
            p_lock_query = select(Patient).where(
                Patient.id == UUID(locked_patient_id)
            )
            p_lock_res = await db.execute(p_lock_query)
            locked_patient = p_lock_res.scalars().first()
            if locked_patient:
                appt_q = select(Appointment).where(
                    Appointment.patient_id == locked_patient.id,
                    Appointment.status.in_(["scheduled", "in_progress"]),
                )
                appt_res = await db.execute(appt_q)
                active_appts = appt_res.scalars().all()
                return {
                    "status": "RETURNING_PATIENT",
                    "patient": locked_patient,
                    "patients": [locked_patient],
                    "active_appointments": active_appts,
                    "active_appointment": active_appts[0] if active_appts else None,
                    "has_multiple_active": len(active_appts) > 1,
                    "disambiguation_prompt": None,
                }
        except Exception:
            pass

    p_query = select(Patient).where(
        Patient.org_id == org_id,
        Patient.phone_number == clean_phone
    )
    p_res = await db.execute(p_query)
    patients = p_res.scalars().all()

    if not patients:
        matched_patient_by_name = None
        if session_known_name:
            name_parts = session_known_name.strip().split(" ", 1)
            first_n = name_parts[0].strip()
            last_n = name_parts[1].strip() if len(name_parts) > 1 else ""

            query_filters = [
                Patient.org_id == org_id,
                func.lower(Patient.first_name) == first_n.lower()
            ]
            if last_n:
                query_filters.append(func.lower(Patient.last_name) == last_n.lower())
            if session_known_dob:
                query_filters.append(Patient.dob == session_known_dob)

            name_query = select(Patient).where(*query_filters)
            name_res = await db.execute(name_query)
            matched_patient_by_name = name_res.scalars().first()

        if matched_patient_by_name:
            patient = matched_patient_by_name
            patients = [patient]
        else:
            return {
                "status": "NEW_PATIENT",
                "patient": None,
                "patients": [],
                "active_appointments": [],
                "active_appointment": None,
                "has_multiple_active": False,
                "disambiguation_prompt": None,
            }
    else:
        patient = None
        if len(patients) > 1:
            if session_known_name:
                name_lower = session_known_name.lower()
                for p in patients:
                    full_p = f"{p.first_name} {p.last_name}".lower()
                    if p.first_name.lower() in name_lower or full_p in name_lower:
                        if session_known_dob and p.dob and p.dob != session_known_dob:
                            continue
                        patient = p
                        break
            if not patient:
                return {
                    "status": "MULTIPLE_PATIENTS_ON_PHONE",
                    "patient": None,
                    "patients": patients,
                    "active_appointments": [],
                    "active_appointment": None,
                    "has_multiple_active": False,
                    "disambiguation_prompt": "Welcome to our clinic! To access your record, may I have your full name and date of birth please?",
                }
        else:
            patient = patients[0]

    active_query = (
        select(Appointment, User)
        .outerjoin(User, Appointment.doctor_id == User.id)
        .where(
            Appointment.org_id == org_id,
            Appointment.patient_id == patient.id,
            Appointment.status.in_(["scheduled", "in_progress"])
        )
        .order_by(Appointment.start_time.asc())
    )
    active_res = await db.execute(active_query)
    rows = active_res.all()

    active_appts = []
    for appt, doc in rows:
        active_appts.append({
            "appointment": appt,
            "doctor": doc,
            "doctor_name": doc.full_name if doc else "Doctor",
            "start_time_str": appt.start_time.strftime("%b %d at %I:%M %p"),
            "date_str": appt.start_time.strftime("%b %d"),
            "time_str": appt.start_time.strftime("%I:%M %p"),
            "chief_complaint": appt.chief_complaint,
        })

    if len(active_appts) > 1:
        items = [f"{item['date_str']} at {item['time_str']} with {item['doctor_name']}" for item in active_appts]
        prompt = f"I see {len(active_appts)} upcoming visits for {patient.first_name}: " + " & ".join(items) + ". Which one would you like to update?"
        return {
            "status": "MULTIPLE_ACTIVE_APPOINTMENTS",
            "patient": patient,
            "patients": patients,
            "active_appointments": active_appts,
            "active_appointment": active_appts[0]["appointment"],
            "has_multiple_active": True,
            "disambiguation_prompt": prompt,
        }
    elif len(active_appts) == 1:
        first = active_appts[0]
        return {
            "status": "HAS_ACTIVE_APPOINTMENT",
            "patient": patient,
            "patients": patients,
            "active_appointments": active_appts,
            "active_appointment": first["appointment"],
            "doctor": first["doctor"],
            "has_multiple_active": False,
            "disambiguation_prompt": None,
        }

    return {
        "status": "PATIENT_FOUND_NO_ACTIVE_APPTS",
        "patient": patient,
        "patients": patients,
        "active_appointments": [],
        "active_appointment": None,
        "has_multiple_active": False,
        "disambiguation_prompt": None,
    }


def resolve_target_appointment(
    active_appts: list, speech_text: str, target_date=None, target_time=None
):
    if not active_appts:
        return None
    if len(active_appts) == 1:
        return active_appts[0]["appointment"]

    speech_lower = speech_text.lower()
    for item in active_appts:
        appt = item["appointment"]
        doc_name = item["doctor_name"].lower()
        date_str = item["date_str"].lower()
        time_str = item["time_str"].lower()

        if target_date and appt.start_time.date() == target_date:
            return appt
        if doc_name in speech_lower or date_str in speech_lower or time_str in speech_lower:
            return appt

    return active_appts[0]["appointment"]
