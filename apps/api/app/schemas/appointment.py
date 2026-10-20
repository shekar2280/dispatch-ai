from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID
from datetime import datetime, date, time
from typing import Optional, Literal, List


class AppointmentBase(BaseModel):
    source: Optional[str] = None
    patient_id: UUID
    doctor_id: Optional[UUID] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: str = "scheduled"
    chief_complaint: Optional[str] = None
    doctor_notes: Optional[str] = None
    booked_by_type: Optional[str] = None
    booked_by_name: Optional[str] = None
    verification_status: Optional[str] = None
    auto_confirm_deadline: Optional[datetime] = None
    audio_recording_url: Optional[str] = None
    cancellation_reason: Optional[str] = None


class AppointmentCreate(AppointmentBase):
    org_id: UUID


class AppointmentStatusUpdate(BaseModel):
    status: str
    chief_complaint: Optional[str] = None
    doctor_notes: Optional[str] = None
    prescriptions: Optional[List[str]] = None


class AppointmentResponse(AppointmentBase):
    id: UUID
    org_id: UUID
    appointment_date: Optional[date] = None
    appointment_time: Optional[str] = None
    patient_name: Optional[str] = None
    patient_phone: Optional[str] = None
    dob: Optional[date] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    address: Optional[str] = None
    reported_age: Optional[int] = None
    age_unit: Optional[str] = None
    bill_finalized_at: Optional[str] = None
    previous_visit_id: Optional[str] = None
    urgency_reason: Optional[str] = None
    doctor_name: Optional[str] = None
    specialization: Optional[str] = None
    created_at: datetime
    token_number: Optional[int] = None
    display_token: Optional[str] = None
    token_prefix: Optional[str] = None
    shift_type: Optional[str] = None
    payment_status: Optional[str] = None
    fee: Optional[float] = None
    payment_method: Optional[str] = None
    bill_items: Optional[List[dict]] = None
    amount_paid: Optional[float] = 0
    balance_due: Optional[float] = None
    payment_receipts: Optional[List[dict]] = None
    checked_in_at: Optional[datetime] = None
    called_at: Optional[datetime] = None
    queue_state: Optional[str] = None
    encounter_state: Optional[str] = None
    consultation_started_at: Optional[datetime] = None
    consultation_ended_at: Optional[datetime] = None
    actual_duration_seconds: Optional[int] = None
    call_count: Optional[int] = 0

    model_config = ConfigDict(from_attributes=True)


class ClinicWalkinBookingRequest(BaseModel):
    doctor_id: Optional[UUID] = None
    patient_name: str = Field(min_length=1, max_length=120)
    patient_phone: str = Field(min_length=5, max_length=32)
    patient_id: Optional[UUID] = None
    dob: Optional[date] = None
    gender: Optional[str] = Field(default=None, max_length=40)
    blood_group: Optional[str] = Field(default=None, max_length=10)
    address: Optional[str] = Field(default=None, max_length=500)
    reported_age: Optional[int] = Field(default=None, ge=0, le=1560)
    age_unit: Literal["years", "months"] = "years"
    appointment_date: date
    chief_complaint: Optional[str] = None
    fee: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    is_walkin: bool = True
    appointment_time: Optional[str] = None
    is_arrived: bool = True
    payment_status: Optional[str] = None
    payment_method: Optional[str] = None
    token_prefix: Optional[str] = None


class ClinicScheduledBookingRequest(BaseModel):
    previous_visit_id: Optional[UUID] = None
    patient_name: str = Field(min_length=1, max_length=120)
    patient_phone: str = Field(min_length=5, max_length=32)
    patient_id: Optional[UUID] = None
    dob: Optional[date] = None
    reported_age: Optional[int] = Field(default=None, ge=0, le=1560)
    age_unit: Literal["years", "months"] = "years"
    doctor_id: Optional[UUID] = None
    appointment_date: date
    appointment_time: str = Field(min_length=1, max_length=30)
    chief_complaint: Optional[str] = None
    fee: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)


class ClinicDoctorNotesUpdate(BaseModel):
    doctor_notes: str
    recent_diagnosis: Optional[str] = None
    bill_items: Optional[List[dict]] = None
    fee: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)


class BillItem(BaseModel):
    id: Optional[str] = None
    name: str = Field(min_length=1, max_length=120)
    amount: float = Field(ge=0, allow_inf_nan=False)
    category: Optional[str] = "consultation"
    quantity: Optional[float] = Field(default=1, gt=0, allow_inf_nan=False)
    unit_price: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)


class ClinicPaymentUpdate(BaseModel):
    idempotency_key: str = Field(min_length=16, max_length=80)
    adjustment_reason: Optional[str] = None
    payment_status: Literal["paid", "pending"]
    payment_method: Optional[str] = None
    fee: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    bill_items: Optional[List[BillItem]] = None
    amount_received: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    reference: Optional[str] = None


class ClinicPatientNoteRequest(BaseModel):
    note: str = Field(min_length=1, max_length=5000)


class ClinicRescheduleRequest(BaseModel):
    new_date: date
    new_time: str = Field(min_length=1, max_length=30)
    reason: Optional[str] = None


class ClinicCheckInRequest(BaseModel):
    doctor_id: Optional[UUID] = None
    patient_phone: Optional[str] = None
    patient_name: Optional[str] = None
    dob: Optional[date] = None
    reported_age: Optional[int] = Field(default=None, ge=0, le=1560)
    age_unit: Literal["years", "months"] = "years"
    gender: Optional[str] = None
    blood_group: Optional[str] = Field(default=None, max_length=10)
    address: Optional[str] = Field(default=None, max_length=500)
    chief_complaint: Optional[str] = None
    payment_status: Optional[str] = None
    payment_method: Optional[str] = None
    fee: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    bill_items: Optional[List[BillItem]] = None


class VisitEventResponse(BaseModel):
    id: UUID
    visit_id: UUID
    org_id: UUID
    event_type: str
    occurred_at: datetime
    actor_id: Optional[UUID] = None
    actor_type: str = "staff"
    notes: Optional[str] = None
    metadata: Optional[dict] = Field(default_factory=dict, validation_alias="event_metadata")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class UrgencyUpdate(BaseModel):
    reason: str = Field(min_length=5, max_length=500)
