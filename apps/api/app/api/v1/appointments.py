from datetime import date
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_tenant_org, get_current_user
from app.models.organization import Organization
from app.models.user import User
from app.schemas.appointment import (
    UrgencyUpdate,
    AppointmentResponse,
    AppointmentStatusUpdate,
    ClinicWalkinBookingRequest,
    ClinicDoctorNotesUpdate,
    ClinicPaymentUpdate,
    ClinicPatientNoteRequest,
    ClinicScheduledBookingRequest,
    ClinicRescheduleRequest,
    ClinicCheckInRequest,
    VisitEventResponse,
)
from app.services.appointments import (
    get_clinic_daily_slots,
    get_hourly_capacity_ledger,
    list_clinic_appointments,
    book_clinic_walkin_appointment,
    book_clinic_scheduled_appointment,
    get_clinic_queue,
    rollover_clinic_queue,
    batch_reconcile_clinic_queue,
    execute_end_of_day_action,
    expire_rollover_priority as service_expire_rollover_priority,
    ClinicBatchReconciliationRequest,
    update_appointment_status as service_update_appointment_status,
    mark_appointment_arrived as service_mark_appointment_arrived,
    call_appointment_patient as service_call_appointment_patient,
    start_consultation as service_start_consultation,
    complete_consultation as service_complete_consultation,
    skip_appointment_patient as service_skip_appointment_patient,
    reinsert_skipped_patient as service_reinsert_skipped_patient,
    move_appointment_to_tomorrow as service_move_appointment_to_tomorrow,
    mark_clinic_late_arrival as service_mark_clinic_late_arrival,
    reschedule_clinic_appointment as service_reschedule_clinic_appointment,
    cancel_clinic_appointment as service_cancel_clinic_appointment,
    get_appointment_visit_events as service_get_appointment_visit_events,
    update_appointment_doctor_notes,
    save_patient_clinical_note,
    resolve_emergency_callback as service_resolve_emergency_callback,
    collect_appointment_fee,
)
from app.api.v1.clinic_dashboard import router as dashboard_router
from app.services.appointments.schedule_service import lookup_patients, count_leave_collisions

router = APIRouter()
router.include_router(dashboard_router)


def _visible_appointment(item: AppointmentResponse, user: User) -> AppointmentResponse:
    # Clinical fields are never sent to a non-clinician, including an admin.
    if user.role != "doctor":
        return item.model_copy(update={"doctor_notes": None})
    return item


def _visible_appointments(items: List[AppointmentResponse], user: User) -> List[AppointmentResponse]:
    return [_visible_appointment(item, user) for item in items]


@router.get("/patient-lookup")
async def patient_lookup(
    phone: str = Query(min_length=5, max_length=32),
    name: str = Query(default="", max_length=120),
    org_id: UUID = Depends(get_current_tenant_org),
    db: AsyncSession = Depends(get_db),
):
    return await lookup_patients(db, org_id, phone, name)


@router.get("/leave-collisions")
async def leave_collisions(
    start_date: date,
    end_date: date,
    org_id: UUID = Depends(get_current_tenant_org),
    db: AsyncSession = Depends(get_db),
):
    return await count_leave_collisions(db, org_id, start_date, end_date)


@router.get("/slots")
async def list_available_slots(
    target_date: date,
    doctor_id: Optional[UUID] = None,
    org_id: UUID = Depends(get_current_tenant_org),
    db: AsyncSession = Depends(get_db),
):
    return await get_clinic_daily_slots(db, org_id, target_date, doctor_id)


@router.get("/capacity-ledger")
async def get_capacity_ledger(
    target_date: date,
    org_id: UUID = Depends(get_current_tenant_org),
    db: AsyncSession = Depends(get_db),
):
    clinic_org = await db.get(Organization, org_id)
    if not clinic_org:
        raise HTTPException(status_code=404, detail="Clinic organization not found")
    return await get_hourly_capacity_ledger(db, clinic_org, org_id, target_date)


@router.post("/{appointment_id}/urgency")
async def record_urgency(appointment_id: UUID, req: UrgencyUpdate, org_id: UUID = Depends(get_current_tenant_org), current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from app.models.appointment import Appointment
    from app.services.appointments.encounter_service import write_visit_event
    if current_user.role not in {"doctor", "receptionist", "admin"}:
        raise HTTPException(403, "Clinic staff confirmation is required")
    visit = await db.scalar(select(Appointment).where(Appointment.id == appointment_id, Appointment.org_id == org_id).with_for_update())
    if not visit or visit.status != "arrived":
        raise HTTPException(409, "Urgency can be recorded for a checked-in waiting patient")
    visit.booking_metadata = {**(visit.booking_metadata or {}), "urgent_reason": req.reason.strip()}
    await write_visit_event(db, visit.id, org_id, "URGENCY_CONFIRMED", actor_id=current_user.id, notes=req.reason.strip())
    await db.commit()
    return {"status": "recorded"}


@router.get("/arrival-options")
async def arrival_options(target_date: date, doctor_id: UUID, org_id: UUID = Depends(get_current_tenant_org), db: AsyncSession = Depends(get_db)):
    from app.models.organization import Organization
    from app.services.appointments.booking_service import get_future_capacity
    doctor = await db.get(User, doctor_id)
    if not doctor or doctor.org_id != org_id or doctor.role != "doctor":
        raise HTTPException(404, "Doctor not found")
    org = await db.get(Organization, org_id)
    return await get_future_capacity(db, org, org_id, target_date, doctor_id=doctor_id)


@router.get("/doctors")
async def list_booking_doctors(org_id: UUID = Depends(get_current_tenant_org), db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    rows = (await db.execute(select(User).where(User.org_id == org_id, User.role == "doctor", User.is_active == True))).scalars().all()
    return [{"id": str(user.id), "name": user.full_name} for user in rows]


@router.get("/billing", response_model=List[AppointmentResponse])
async def list_billing_visits(org_id: UUID = Depends(get_current_tenant_org), current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from app.models.appointment import Appointment
    from app.services.appointments.serializers import build_appointment_list_response
    rows = (await db.execute(select(Appointment).where(Appointment.org_id == org_id, Appointment.status == "completed").order_by(Appointment.start_time.desc()))).scalars().all()
    return _visible_appointments(await build_appointment_list_response(db, list(rows), org_id), current_user)


@router.get("/", response_model=List[AppointmentResponse])
async def list_appointments(
    target_date: Optional[date] = None,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return _visible_appointments(await list_clinic_appointments(db, org_id, target_date), current_user)


@router.post("/walkin", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
async def create_walkin(
    req: ClinicWalkinBookingRequest,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return _visible_appointment(await book_clinic_walkin_appointment(db, req, org_id), current_user)


@router.post("/book", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
async def book_appointment(
    req: ClinicScheduledBookingRequest,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return _visible_appointment(await book_clinic_scheduled_appointment(db, req, org_id), current_user)


@router.get("/queue", response_model=List[AppointmentResponse])
async def get_active_queue(
    doctor_id: Optional[UUID] = None,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return _visible_appointments(await get_clinic_queue(db, org_id, doctor_id), current_user)


@router.post("/rollover-queue")
async def rollover_queue(
    org_id: UUID = Depends(get_current_tenant_org),
    db: AsyncSession = Depends(get_db),
):
    return await rollover_clinic_queue(db, org_id)


@router.post("/batch-reconciliation")
async def batch_reconcile_queue(
    payload: ClinicBatchReconciliationRequest,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await batch_reconcile_clinic_queue(db, org_id, payload, current_user.id)


@router.post("/end-of-day-action")
async def apply_end_of_day_action(
    payload: dict = Body(...),
    org_id: UUID = Depends(get_current_tenant_org),
    db: AsyncSession = Depends(get_db),
):
    return await execute_end_of_day_action(db, org_id, payload)


@router.post("/expire-rollover-priority")
async def expire_rollover_priority(
    org_id: UUID = Depends(get_current_tenant_org),
    db: AsyncSession = Depends(get_db),
):
    return await service_expire_rollover_priority(db, org_id)


@router.post("/{appointment_id}/late-arrival", response_model=AppointmentResponse)
async def mark_late_arrival(
    appointment_id: UUID,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return _visible_appointment(await service_mark_clinic_late_arrival(db, appointment_id, org_id), current_user)


@router.patch("/{appointment_id}/status", response_model=AppointmentResponse)
async def update_status(
    appointment_id: UUID,
    status_update: AppointmentStatusUpdate,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if status_update.doctor_notes is not None and current_user.role != "doctor":
        raise HTTPException(status_code=403, detail="Only a clinician may edit clinical notes")
    if status_update.status in ("in_progress", "completed") and current_user.role != "doctor":
        raise HTTPException(status_code=403, detail="Only a clinician may manage consultations")
    return _visible_appointment(await service_update_appointment_status(db, appointment_id, status_update, org_id), current_user)


@router.post("/{appointment_id}/arrive", response_model=AppointmentResponse)
async def check_in_patient(
    appointment_id: UUID,
    req: Optional[ClinicCheckInRequest] = Body(None),
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return _visible_appointment(await service_mark_appointment_arrived(db, appointment_id, req, org_id, current_user.id), current_user)


@router.post("/{appointment_id}/call", response_model=AppointmentResponse)
async def call_patient(
    appointment_id: UUID,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "doctor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only attending doctors can start or complete consultations.",
        )
    return _visible_appointment(await service_call_appointment_patient(db, appointment_id, org_id), current_user)


@router.post("/{appointment_id}/start-consultation", response_model=AppointmentResponse)
async def start_consultation(
    appointment_id: UUID,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "doctor":
        raise HTTPException(status_code=403, detail="Only a clinician may start a consultation")
    return _visible_appointment(await service_start_consultation(db, appointment_id, org_id), current_user)


@router.post("/{appointment_id}/complete", response_model=AppointmentResponse)
@router.post("/{appointment_id}/complete-consultation", response_model=AppointmentResponse)
async def complete_visit(
    appointment_id: UUID,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "doctor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only attending doctors can start or complete consultations.",
        )
    return _visible_appointment(await service_complete_consultation(db, appointment_id, org_id), current_user)


@router.post("/{appointment_id}/skip", response_model=AppointmentResponse)
async def skip_patient(
    appointment_id: UUID,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return _visible_appointment(await service_skip_appointment_patient(db, appointment_id, org_id), current_user)


@router.post("/{appointment_id}/reinsert", response_model=AppointmentResponse)
async def reinsert_patient(
    appointment_id: UUID,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return _visible_appointment(await service_reinsert_skipped_patient(db, appointment_id, org_id), current_user)


@router.patch("/{appointment_id}/reschedule", response_model=AppointmentResponse)
@router.post("/{appointment_id}/reschedule", response_model=AppointmentResponse)
async def reschedule_appointment(
    appointment_id: UUID,
    req: ClinicRescheduleRequest,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return _visible_appointment(await service_reschedule_clinic_appointment(db, appointment_id, req, org_id), current_user)


@router.post("/{appointment_id}/cancel", response_model=AppointmentResponse)
async def cancel_appointment(
    appointment_id: UUID,
    payload: dict = Body(default={}),
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    reason = payload.get("reason", "Cancelled by clinic desk")
    return _visible_appointment(await service_cancel_clinic_appointment(db, appointment_id, reason, org_id), current_user)


@router.post("/{appointment_id}/move-tomorrow", response_model=AppointmentResponse)
async def move_to_tomorrow(
    appointment_id: UUID,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return _visible_appointment(await service_move_appointment_to_tomorrow(db, appointment_id, org_id), current_user)


@router.get("/{appointment_id}/events", response_model=List[VisitEventResponse])
async def list_visit_events(
    appointment_id: UUID,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    events = await service_get_appointment_visit_events(db, appointment_id, org_id)
    if current_user.role == "doctor":
        return events
    return [event.model_copy(update={"notes": None, "metadata": {}}) for event in events]


@router.patch("/{appointment_id}/notes")
@router.post("/{appointment_id}/notes")
async def update_notes(
    appointment_id: UUID,
    req: ClinicDoctorNotesUpdate,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "doctor":
        raise HTTPException(status_code=403, detail="Only a clinician may edit clinical notes")
    return await update_appointment_doctor_notes(db, appointment_id, req, org_id)


@router.post("/patients/{patient_id}/notes")
async def add_patient_note(
    patient_id: UUID,
    req: ClinicPatientNoteRequest,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "doctor":
        raise HTTPException(status_code=403, detail="Only a clinician may edit clinical notes")
    return await save_patient_clinical_note(db, patient_id, req, org_id)


@router.post("/emergency-callbacks/{session_id}/resolve")
async def resolve_emergency_callback(
    session_id: UUID,
    org_id: UUID = Depends(get_current_tenant_org),
    db: AsyncSession = Depends(get_db),
):
    return await service_resolve_emergency_callback(db, session_id, org_id)


@router.patch("/{appointment_id}/collect-fee")
@router.post("/{appointment_id}/collect-fee")
async def collect_fee(
    appointment_id: UUID,
    req: ClinicPaymentUpdate,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await collect_appointment_fee(db, appointment_id, req, org_id, current_user.id)
