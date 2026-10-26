from app.core.clinic_config import require_clinic_timezone
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.organization import Organization
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.payment_receipt import PaymentReceipt
from app.models.user import User
from app.schemas.appointment import AppointmentResponse


async def build_single_appointment_response(
    db: AsyncSession,
    clinic_appt: Appointment,
    org_id: UUID,
    patient: Optional[Patient] = None,
    doctor: Optional[User] = None,
    org: Optional[Organization] = None,
    receipts: Optional[list] = None,
) -> AppointmentResponse:
    if patient is None and clinic_appt.patient_id:
        patient = await db.get(Patient, clinic_appt.patient_id)
    if doctor is None and clinic_appt.doctor_id:
        doctor = await db.get(User, clinic_appt.doctor_id)
    if org is None:
        org = await db.get(Organization, org_id)

    p_name = (
        f"{patient.first_name} {patient.last_name}".strip()
        if patient
        else "Caller / Patient"
    )
    doc_name = (
        doctor.full_name
        if doctor
        else (org.lead_doctor_name if org else "Attending Doctor")
    )
    doc_spec = (
        doctor.specialization
        if doctor
        else (org.clinic_specialty if org else "General Medicine")
    )
    meta = clinic_appt.booking_metadata or {}
    bill_items = meta.get("bill_items", [])

    if receipts is None:
        receipts = list((await db.execute(select(PaymentReceipt).where(
        PaymentReceipt.org_id == org_id, PaymentReceipt.visit_id == clinic_appt.id,
        PaymentReceipt.status == "paid",
    ).order_by(PaymentReceipt.received_at))).scalars().all())
    amount_paid = sum(float(r.amount) for r in receipts)
    balance_due = max(float(clinic_appt.fee or 0) - amount_paid, 0)

    return AppointmentResponse(
        id=clinic_appt.id,
        org_id=clinic_appt.org_id,
        patient_id=clinic_appt.patient_id,
        doctor_id=clinic_appt.doctor_id,
        start_time=clinic_appt.start_time,
        end_time=clinic_appt.end_time,
        status=clinic_appt.status,
        chief_complaint=clinic_appt.chief_complaint,
        doctor_notes=clinic_appt.doctor_notes,
        booked_by_type="VOICE_AI" if clinic_appt.source == "ai_voice" else "walk_in",
        booked_by_name=(
            "AI Voice Receptionist"
            if clinic_appt.source == "ai_voice"
            else "Front Desk"
        ),
        verification_status="verified",
        created_at=clinic_appt.created_at or clinic_appt.start_time,
        patient_name=p_name,
        patient_phone=patient.phone_number if patient else "",
        dob=patient.dob if patient else None,
        gender=patient.gender if patient else None,
        blood_group=patient.blood_group if patient else None,
        address=patient.address if patient else None,
        reported_age=((patient.medical_history or {}).get("reported_age") or {}).get("value") if patient else None,
        age_unit=((patient.medical_history or {}).get("reported_age") or {}).get("unit") if patient else None,
        bill_finalized_at=meta.get("bill_finalized_at"),
        previous_visit_id=meta.get("previous_visit_id"),
        urgency_reason=meta.get("urgent_reason"),
        doctor_name=doc_name,
        specialization=doc_spec,
        token_number=clinic_appt.token_number,
        display_token=clinic_appt.display_token,
        token_prefix=clinic_appt.token_prefix,
        appointment_date=clinic_appt.start_time.astimezone(ZoneInfo(require_clinic_timezone(org))).date(),
        appointment_time=clinic_appt.start_time.astimezone(ZoneInfo(require_clinic_timezone(org))).strftime("%I:%M %p"),
        fee=clinic_appt.fee,
        payment_status=clinic_appt.payment_status or "pending",
        payment_method=clinic_appt.payment_method,
        amount_paid=amount_paid,
        payment_receipts=[{"id": str(r.id), "amount": float(r.amount), "method": r.method, "reference": r.reference, "received_at": r.received_at.isoformat()} for r in receipts],
        balance_due=balance_due,
        source=clinic_appt.source or "walk_in",
        bill_items=bill_items,
        checked_in_at=clinic_appt.checked_in_at,
        called_at=clinic_appt.called_at,
        queue_state=clinic_appt.queue_state,
        encounter_state=clinic_appt.encounter_state,
        consultation_started_at=clinic_appt.consultation_started_at,
        consultation_ended_at=clinic_appt.consultation_ended_at,
        actual_duration_seconds=clinic_appt.actual_duration_seconds,
    )


async def build_appointment_list_response(
    db: AsyncSession,
    appointments: List[Appointment],
    org_id: UUID,
) -> List[AppointmentResponse]:
    if not appointments:
        return []
    receipts_by_visit = {}
    receipt_rows = (await db.execute(select(PaymentReceipt).where(PaymentReceipt.org_id == org_id, PaymentReceipt.visit_id.in_([a.id for a in appointments]), PaymentReceipt.status == "paid").order_by(PaymentReceipt.received_at))).scalars().all()
    for receipt in receipt_rows:
        receipts_by_visit.setdefault(receipt.visit_id, []).append(receipt)

    org = await db.get(Organization, org_id)

    patient_ids = {appt.patient_id for appt in appointments if appt.patient_id}
    doctor_ids = {appt.doctor_id for appt in appointments if appt.doctor_id}

    patients_by_id = {}
    if patient_ids:
        p_res = await db.execute(select(Patient).where(Patient.id.in_(patient_ids)))
        patients_by_id = {p.id: p for p in p_res.scalars().all()}

    doctors_by_id = {}
    if doctor_ids:
        d_res = await db.execute(select(User).where(User.id.in_(doctor_ids)))
        doctors_by_id = {d.id: d for d in d_res.scalars().all()}

    return [
        await build_single_appointment_response(
            db=db,
            clinic_appt=appt,
            org_id=org_id,
            patient=patients_by_id.get(appt.patient_id),
            doctor=doctors_by_id.get(appt.doctor_id),
            org=org,
            receipts=receipts_by_visit.get(appt.id, []),
        )
        for appt in appointments
    ]
