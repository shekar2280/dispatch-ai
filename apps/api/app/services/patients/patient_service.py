import logging
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_, text
from fastapi import HTTPException

from app.models.patient import Patient
from app.models.appointment import Appointment
from app.schemas.patient import PatientCreate, PatientUpdate
from app.core.phone_utils import normalize_phone_e164
from app.services.infra.redis_cache import hot_cache_service
from app.services.infra.audit import write_audit_event

logger = logging.getLogger("app.services.patient_service")


async def get_patient_by_name_and_phone(
    db: AsyncSession,
    org_id: UUID,
    phone_number: str,
    first_name: str,
    last_name: Optional[str] = None,
) -> Optional[Patient]:
    norm = normalize_phone_e164(phone_number)
    target_phone = norm.e164_phone if norm.is_valid else phone_number.strip()
    clean_f_name = first_name.strip().lower()

    conditions = [
        Patient.org_id == org_id,
        Patient.phone_number == target_phone,
        Patient.deleted_at.is_(None),
        func.lower(Patient.first_name) == clean_f_name,
    ]
    if last_name is not None:
        conditions.append(func.lower(Patient.last_name) == last_name.strip().lower())
    stmt = (
        select(Patient)
        .where(and_(*conditions))
        .order_by(Patient.created_at.asc())
    )

    res = await db.execute(stmt)
    matches = res.scalars().all()
    if len(matches) > 1:
        raise HTTPException(status_code=409, detail="Multiple patient profiles match. Verify a patient ID.")
    return matches[0] if len(matches) == 1 else None


async def get_all_patients_for_phone(
    db: AsyncSession,
    org_id: UUID,
    phone_number: str,
) -> List[Patient]:
    norm = normalize_phone_e164(phone_number)
    target_phone = norm.e164_phone if norm.is_valid else phone_number.strip()

    stmt = (
        select(Patient)
        .where(
            and_(
                Patient.org_id == org_id,
                Patient.phone_number == target_phone,
                Patient.deleted_at.is_(None),
            )
        )
        .order_by(Patient.created_at.asc())
    )

    res = await db.execute(stmt)
    return list(res.scalars().all())


async def get_or_create_patient_profile(
    db: AsyncSession,
    org_id: UUID,
    phone_number: str,
    first_name: str,
    last_name: str,
    created_by_type: str = "VOICE_AI",
    created_by_user_id: Optional[UUID] = None,
) -> Patient:
    norm = normalize_phone_e164(phone_number)
    target_phone = norm.e164_phone if norm.is_valid else phone_number.strip()
    clean_f = first_name.strip()
    clean_l = last_name.strip()
    existing_patient = await get_patient_by_name_and_phone(
        db=db,
        org_id=org_id,
        phone_number=target_phone,
        first_name=clean_f,
        last_name=clean_l,
    )

    if existing_patient:
        try:
            await db.execute(
                text(
                    """
                    INSERT INTO public.clinic_patients (id, org_id, phone_number, first_name, last_name)
                    SELECT :p_id, :org_id, :phone, :f_name, :l_name
                    WHERE EXISTS (SELECT 1 FROM public.organizations WHERE id = :org_id)
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {
                    "p_id": existing_patient.id,
                    "org_id": org_id,
                    "phone": target_phone,
                    "f_name": existing_patient.first_name,
                    "l_name": existing_patient.last_name,
                },
            )
        except Exception:
            pass
        logger.info("Resolved existing patient profile in org='%s'", org_id)
        return existing_patient

    new_patient = Patient(
        org_id=org_id,
        phone_number=target_phone,
        first_name=clean_f,
        last_name=clean_l,
        created_by_type=created_by_type,
        created_by=created_by_user_id,
    )

    db.add(new_patient)
    await db.flush()

    try:
        await db.execute(
            text(
                """
                INSERT INTO public.clinic_patients (id, org_id, phone_number, first_name, last_name)
                SELECT :p_id, :org_id, :phone, :f_name, :l_name
                WHERE EXISTS (SELECT 1 FROM public.organizations WHERE id = :org_id)
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "p_id": new_patient.id,
                "org_id": org_id,
                "phone": target_phone,
                "f_name": clean_f,
                "l_name": clean_l,
            },
        )
    except Exception:
        pass
    logger.info("Provisioned new patient profile in org='%s'", org_id)

    cache_eval = await hot_cache_service.evaluate_hot_cache_promotion(
        org_id=org_id,
        e164_phone=target_phone,
        is_live_call=True,
    )

    if cache_eval.should_cache:
        await hot_cache_service.cache_patient_profile(
            org_id=org_id,
            e164_phone=target_phone,
            patient_data={
                "id": str(new_patient.id),
                "first_name": new_patient.first_name,
                "last_name": new_patient.last_name,
                "phone_number": new_patient.phone_number,
            },
            ttl_seconds=cache_eval.cache_ttl_seconds,
        )

    return new_patient


async def get_patient_by_phone(
    db: AsyncSession,
    phone_number: str,
    org_id: Optional[UUID] = None,
) -> Optional[Patient]:
    norm = normalize_phone_e164(phone_number)
    target_phone = norm.e164_phone if norm.is_valid else phone_number.strip()
    stmt = select(Patient).where(Patient.phone_number == target_phone, Patient.deleted_at.is_(None))
    if org_id:
        stmt = stmt.where(Patient.org_id == org_id)
    stmt = stmt.order_by(Patient.created_at.asc())
    res = await db.execute(stmt)
    matches = res.scalars().all()
    if len(matches) > 1:
        raise HTTPException(409, "Multiple patients share this phone. Select a verified patient ID.")
    return matches[0] if matches else None


async def get_patient_by_id(
    db: AsyncSession,
    patient_id: UUID,
    org_id: Optional[UUID] = None, include_archived: bool = False,
) -> Optional[Patient]:
    stmt = select(Patient).where(Patient.id == patient_id)
    if org_id:
        stmt = stmt.where(Patient.org_id == org_id)
    if not include_archived:
        stmt = stmt.where(Patient.deleted_at.is_(None))
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def get_all_patients(
    db: AsyncSession,
    org_id: UUID,
) -> List[Patient]:
    stmt = select(Patient).where(Patient.org_id == org_id, Patient.deleted_at.is_(None)).order_by(Patient.created_at.desc())
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def create_patient(
    db: AsyncSession,
    patient_in: PatientCreate,
    org_id: Optional[UUID] = None,
) -> Patient:
    norm = normalize_phone_e164(patient_in.phone_number)
    target_phone = norm.e164_phone if norm.is_valid else patient_in.phone_number.strip()
    mapped_fields = {
        "phone_number", "first_name", "last_name", "dob", "gender", "blood_group",
        "email", "address", "medical_history", "created_by_type",
    }
    patient_data = patient_in.model_dump(include=mapped_fields)
    patient_data["phone_number"] = target_phone
    if org_id:
        patient_data["org_id"] = org_id
    new_patient = Patient(**patient_data)
    db.add(new_patient)
    await db.commit()
    await db.refresh(new_patient)
    return new_patient


async def update_patient(
    db: AsyncSession,
    patient_id: UUID,
    patient_in: PatientUpdate,
    org_id: Optional[UUID] = None,
) -> Optional[Patient]:
    patient = await get_patient_by_id(db, patient_id, org_id)
    if not patient:
        return None
    mapped_fields = {
        "phone_number", "first_name", "last_name", "dob", "gender", "blood_group",
        "email", "address", "medical_history",
    }
    update_data = patient_in.model_dump(exclude_unset=True, include=mapped_fields)
    if "phone_number" in update_data and update_data["phone_number"]:
        norm = normalize_phone_e164(update_data["phone_number"])
        update_data["phone_number"] = norm.e164_phone if norm.is_valid else update_data["phone_number"].strip()
    for field, value in update_data.items():
        setattr(patient, field, value)
    await db.commit()
    await db.refresh(patient)
    return patient


async def delete_patient(
    db: AsyncSession,
    patient_id: UUID,
    org_id: Optional[UUID] = None,
    actor_id: Optional[UUID] = None,
) -> bool:
    patient = await get_patient_by_id(db, patient_id, org_id)
    if not patient:
        return False
    patient.deleted_at = datetime.now(timezone.utc)
    patient.deleted_by = actor_id
    await write_audit_event(db, org_id=org_id, action_type="PATIENT_ARCHIVED", target_id=patient.id, target_name="patient", actor_id=actor_id, new_state={"archived": True})
    await db.commit()
    return True


async def restore_patient(db: AsyncSession, patient_id: UUID, org_id: UUID, actor_id: Optional[UUID] = None) -> Optional[Patient]:
    patient = await get_patient_by_id(db, patient_id, org_id, include_archived=True)
    if not patient or not patient.deleted_at:
        return None
    patient.deleted_at = None
    patient.deleted_by = None
    await write_audit_event(db, org_id=org_id, action_type="PATIENT_RESTORED", target_id=patient.id, target_name="patient", actor_id=actor_id, new_state={"archived": False})
    await db.commit(); await db.refresh(patient)
    return patient


async def get_clinic_patients_service(
    db: AsyncSession,
    org_id: UUID,
    limit: int = 50,
    offset: int = 0,
    search: str = "",
    patient_id: Optional[UUID] = None,
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
                "note_entries": hist.get("note_entries") or [],
                "visit_history": [{
                    "id": str(a.id),
                    "date": a.start_time.isoformat() if a.start_time else None,
                    "status": str(getattr(a.status, "value", a.status)),
                    "doctor_notes": a.doctor_notes or "",
                    "diagnosis": (a.booking_metadata or {}).get("diagnosis") or "",
                } for a in p_appts],
            }
        )
    return result
