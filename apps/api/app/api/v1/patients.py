from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_tenant_org, get_current_user
from app.models.user import User
from app.schemas.patient import PatientCreate, PatientUpdate, PatientResponse
from app.services.patients.patient_service import (
    get_patient_by_phone,
    get_patient_by_id,
    create_patient,
    update_patient,
    delete_patient,
    get_all_patients,
    get_all_patients_for_phone,
)

router = APIRouter()


def _visible_patient(patient, user: User) -> PatientResponse:
    data = PatientResponse.model_validate(patient)
    if user.role == "doctor":
        return data
    return data.model_copy(update={
        "medical_history": {}, "symptoms": None, "chronic_conditions": None,
        "allergies": None, "prescriptions": None,
    })


@router.get("/lookup", response_model=PatientResponse)
async def lookup_patient(
    phone_number: str,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patients = await get_all_patients_for_phone(db, org_id, phone_number)
    if not patients:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found in EHR database",
        )
    if len(patients) > 1:
        raise HTTPException(status_code=409, detail="Multiple patients share this phone. Select a verified patient ID.")
    return _visible_patient(patients[0], current_user)


@router.get("/", response_model=List[PatientResponse])
async def list_patients(
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return [_visible_patient(patient, current_user) for patient in await get_all_patients(db, org_id)]


@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(
    patient_id: UUID,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await get_patient_by_id(db, patient_id, org_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient record not found",
        )
    return _visible_patient(patient, current_user)


@router.post("/", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
async def register_patient(
    patient_in: PatientCreate,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing_profiles = await get_all_patients_for_phone(db, org_id, patient_in.phone_number)
    if any(
        patient.first_name.strip().casefold() == patient_in.first_name.strip().casefold()
        and patient.last_name.strip().casefold() == patient_in.last_name.strip().casefold()
        and patient.dob == patient_in.dob
        for patient in existing_profiles
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This patient profile already exists under the phone number",
        )
    if current_user.role != "doctor" and patient_in.medical_history:
        raise HTTPException(status_code=403, detail="Only a clinician may create clinical history")
    return _visible_patient(await create_patient(db, patient_in, org_id), current_user)


@router.put("/{patient_id}", response_model=PatientResponse)
async def update_patient_record(
    patient_id: UUID,
    patient_in: PatientUpdate,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if patient_in.medical_history is not None and current_user.role != "doctor":
        raise HTTPException(status_code=403, detail="Only a clinician may edit clinical history")
    updated = await update_patient(db, patient_id, patient_in, org_id)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient record not found for update",
        )
    return _visible_patient(updated, current_user)


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_patient_record(
    patient_id: UUID,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.core.security import is_clinic_administrator
    if not await is_clinic_administrator(db, org_id, current_user.id):
        raise HTTPException(status_code=403, detail="Only a clinic administrator may delete a patient profile")
    success = await delete_patient(db, patient_id, org_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient record not found for deletion",
        )
    return None
