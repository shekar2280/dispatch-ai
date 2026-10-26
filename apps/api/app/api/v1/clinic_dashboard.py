from uuid import UUID
from typing import Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_tenant_org, get_current_user, get_verified_auth_identity, require_clinic_administrator
from app.models.user import User
from app.schemas.appointment import (
    ClinicDoctorNotesUpdate,
    ClinicPaymentUpdate,
    ClinicPatientNoteRequest,
)
from app.services.clinic.dashboard_service import (
    get_clinic_live_dashboard,
    get_clinic_analytics_data,
    get_clinic_revenue_data,
    get_clinic_patients_service,
    update_clinic_doctor_notes,
    save_patient_ehr_note_service,
    resolve_clinic_emergency_callback,
    list_visit_payment_receipts_service,
)
from app.services.billing.payment_service import collect_appointment_fee

router = APIRouter()

CLINICAL_RESPONSE_FIELDS = {
    "doctor_notes", "recent_diagnosis", "allergies", "chronic_conditions", "notes",
    "medical_history", "previous_visits", "note_entries", "diagnosis",
}


def _redact_clinical(value):
    if isinstance(value, list):
        return [_redact_clinical(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_clinical(item) for key, item in value.items()
                if key not in CLINICAL_RESPONSE_FIELDS}
    return value


@router.get("/{appointment_id}/payments")
async def list_visit_payments(
    appointment_id: UUID,
    org_id: UUID = Depends(get_current_tenant_org),
    db: AsyncSession = Depends(get_db),
):
    return await list_visit_payment_receipts_service(db, org_id, appointment_id)


@router.get("/dashboard/live")
async def get_live_dashboard(
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await get_clinic_live_dashboard(db, org_id)
    return data if current_user.role == "doctor" else _redact_clinical(data)


@router.patch("/{appointment_id}/notes")
async def update_doctor_notes(
    appointment_id: UUID,
    req: ClinicDoctorNotesUpdate,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "doctor":
        raise HTTPException(status_code=403, detail="Only a clinician may edit clinical notes")
    return await update_clinic_doctor_notes(
        db=db,
        org_id=org_id,
        appointment_id=appointment_id,
        doctor_notes=req.doctor_notes,
        recent_diagnosis=req.recent_diagnosis,
        bill_items=req.bill_items,
        fee=req.fee,
    )


@router.get("/patients")
async def list_clinic_patients(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: str = Query("", max_length=120),
    patient_id: Optional[UUID] = None,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await get_clinic_patients_service(
        db, org_id, limit, offset, search, patient_id,
        include_clinical_search=current_user.role == "doctor",
    )
    return data if current_user.role == "doctor" else _redact_clinical(data)


@router.post("/patients/{patient_id}/notes")
async def save_patient_note(
    patient_id: UUID,
    req: ClinicPatientNoteRequest,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "doctor":
        raise HTTPException(status_code=403, detail="Only a clinician may edit clinical notes")
    return await save_patient_ehr_note_service(
        db, org_id, patient_id, req.note,
        author_id=current_user.id, author_name=current_user.full_name,
    )


@router.post("/emergency-callbacks/{session_id}/resolve")
async def resolve_emergency_callback(
    session_id: UUID,
    org_id: UUID = Depends(get_current_tenant_org),
    db: AsyncSession = Depends(get_db),
):
    return await resolve_clinic_emergency_callback(db, org_id, session_id)


@router.get("/analytics/data")
@router.get("/analytics")
async def get_analytics(
    period: str = "month",
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == "receptionist":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Receptionists are not authorized to view financial or clinic analytics.",
        )
    return await get_clinic_analytics_data(db, org_id, period)


@router.get("/revenue/data")
@router.get("/revenue")
async def get_revenue(
    period: str = "today",
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == "receptionist":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Receptionists are not authorized to view financial or clinic analytics.",
        )
    return await get_clinic_revenue_data(db, org_id, period)


@router.patch("/{appointment_id}/collect-fee")
async def collect_visit_fee(
    appointment_id: UUID,
    req: ClinicPaymentUpdate,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await collect_appointment_fee(
        db=db,
        appointment_id=appointment_id,
        req=req,
        org_id=org_id,
        received_by_id=current_user.id,
    )


class ClinicStaffInviteRequest(BaseModel):
    email: str
    full_name: str
    role: Literal["receptionist"] = "receptionist"


class ClinicStaffClaimRequest(BaseModel):
    full_name: str | None = None


@router.get("/staff")
async def get_clinic_staff(
    org_id: UUID = Depends(require_clinic_administrator),
    db: AsyncSession = Depends(get_db),
):
    from app.services.clinic.dashboard_service import list_clinic_staff_service
    return await list_clinic_staff_service(db, org_id)


@router.post("/staff")
async def add_clinic_staff(
    req: ClinicStaffInviteRequest,
    org_id: UUID = Depends(require_clinic_administrator),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == "receptionist":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only clinic doctors and administrators can manage team members.",
        )
    from app.services.clinic.dashboard_service import add_clinic_staff_service
    return await add_clinic_staff_service(db, org_id, req.email, req.full_name, req.role)


class ClinicStaffUpdateRequest(BaseModel):
    full_name: str | None = None
    role: Literal["receptionist"] | None = "receptionist"


@router.patch("/staff/{email}")
async def update_clinic_staff(
    email: str,
    req: ClinicStaffUpdateRequest,
    org_id: UUID = Depends(require_clinic_administrator),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == "receptionist":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only clinic doctors and administrators can manage team members.",
        )
    from app.services.clinic.dashboard_service import update_clinic_staff_service
    return await update_clinic_staff_service(db, org_id, email, req.full_name, req.role)


@router.delete("/staff/{email}")
async def remove_clinic_staff(
    email: str,
    org_id: UUID = Depends(require_clinic_administrator),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == "receptionist":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only clinic doctors and administrators can manage team members.",
        )
    from app.services.clinic.dashboard_service import remove_clinic_staff_service
    return await remove_clinic_staff_service(db, org_id, email)


@router.post("/staff/claim")
async def claim_staff_account(
    req: ClinicStaffClaimRequest,
    identity: dict = Depends(get_verified_auth_identity),
    db: AsyncSession = Depends(get_db),
):
    from app.services.clinic.dashboard_service import claim_staff_account_service
    full_name = req.full_name or identity["full_name"] or "Front Desk Staff"
    return await claim_staff_account_service(db, identity["id"], identity["email"], full_name)
