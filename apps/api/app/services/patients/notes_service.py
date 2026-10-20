from typing import Optional, List, Dict, Any
from uuid import UUID
from uuid import uuid4
from datetime import datetime, timezone
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm.attributes import flag_modified

from app.models.patient import Patient
from app.models.appointment import Appointment


async def save_patient_ehr_note_service(
    db: AsyncSession,
    org_id: UUID,
    patient_id: UUID,
    note: str,
    author_id: Optional[UUID] = None,
    author_name: Optional[str] = None,
) -> Dict[str, Any]:
    patient = await db.scalar(select(Patient).where(
        Patient.id == patient_id, Patient.org_id == org_id,
    ).with_for_update())
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic patient not found",
        )

    clean_note = note.strip()
    if not clean_note or len(clean_note) > 5000:
        raise HTTPException(422, "Write a note between 1 and 5,000 characters.")
    if clean_note:
        hist = dict(patient.medical_history or {})
        existing = list(hist.get("notes") or [])
        if clean_note not in existing:
            existing.insert(0, clean_note)
            hist["notes"] = existing
            hist["latest_doctor_notes"] = clean_note
            entries = list(hist.get("note_entries") or [])
            entries.insert(0, {
                "id": str(uuid4()), "text": clean_note,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "author_id": str(author_id) if author_id else None,
                "author_name": author_name or "Clinician",
            })
            hist["note_entries"] = entries
            patient.medical_history = hist

        await db.commit()
        await db.refresh(patient)

    return {"status": "saved", "patient_id": str(patient.id), "note": clean_note}


async def update_clinic_doctor_notes(
    db: AsyncSession,
    org_id: UUID,
    appointment_id: UUID,
    doctor_notes: str,
    recent_diagnosis: Optional[str] = None,
    bill_items: Optional[List[dict]] = None,
    fee: Optional[float] = None,
) -> Dict[str, Any]:
    appt = await db.scalar(select(Appointment).where(Appointment.id == appointment_id).with_for_update())
    if not appt or appt.org_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic appointment not found",
        )

    if (appt.booking_metadata or {}).get("bill_finalized_at") and (fee is not None or bill_items is not None):
        raise HTTPException(409, "Use billing adjustments to change a finalized bill")
    clean_notes = doctor_notes.strip()
    appt.doctor_notes = clean_notes

    meta = dict(appt.booking_metadata or {})
    if recent_diagnosis is not None:
        meta["diagnosis"] = recent_diagnosis.strip()
        meta["recent_diagnosis"] = recent_diagnosis.strip()
    appt.booking_metadata = meta
    flag_modified(appt, "booking_metadata")
    if bill_items is not None:
        meta["bill_items"] = bill_items
        flag_modified(appt, "booking_metadata")
    if fee is not None:
        appt.fee = fee

    patient = await db.get(Patient, appt.patient_id)
    if patient:
        if recent_diagnosis is not None:
            patient.recent_diagnosis = recent_diagnosis.strip()
        if clean_notes:
            hist = dict(patient.medical_history or {})
            existing_notes = list(hist.get("notes") or [])
            if clean_notes not in existing_notes:
                existing_notes.insert(0, clean_notes)
                hist["notes"] = existing_notes
                hist["latest_doctor_notes"] = clean_notes
                patient.medical_history = hist
                flag_modified(patient, "medical_history")

    await db.commit()
    await db.refresh(appt)

    return {
        "appointment_id": str(appt.id),
        "doctor_notes": appt.doctor_notes,
        "status": appt.status,
    }
