from pydantic import BaseModel, ConfigDict, Field, EmailStr
from uuid import UUID
from datetime import date, datetime
from typing import Optional, Dict, Any, List

class PhoneNormalizationResult(BaseModel):
    raw_phone: str
    e164_phone: str
    country_code: str
    country_calling_code: int
    is_valid: bool
    error_message: Optional[str] = None

class PatientBase(BaseModel):
    phone_number: str = Field(min_length=5, max_length=32)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    dob: Optional[date] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    hipaa_consent_given: Optional[bool] = None
    medical_history: Dict[str, Any] = Field(default_factory=dict)

class PatientCreate(PatientBase):
    org_id: UUID
    created_by_type: str = "VOICE_AI"

class PatientUpdate(BaseModel):
    phone_number: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    dob: Optional[date] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    hipaa_consent_given: Optional[bool] = None
    medical_history: Optional[Dict[str, Any]] = None

class PatientResponse(PatientBase):
    id: UUID
    org_id: UUID
    created_at: datetime
    age: Optional[int] = None
    last_visit_date: Optional[str] = None
    symptoms: Optional[List[str]] = None
    chronic_conditions: Optional[List[str]] = None
    allergies: Optional[List[str]] = None
    prescriptions: Optional[List[Dict[str, Any]]] = None

    model_config = ConfigDict(from_attributes=True)

class PatientProfileResponse(PatientBase):
    id: UUID
    org_id: UUID
    phone_number: str
    is_primary_account: bool = True
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class HotCacheEvaluationResult(BaseModel):
    phone_number: str
    org_id: UUID
    should_cache: bool
    cache_ttl_seconds: int
    promotion_reason: str
