from pydantic import BaseModel
from typing import Optional, Literal
from datetime import date


class ExtractedCallIntent(BaseModel):
    intent: str
    action: str
    target_date: Optional[date] = None
    target_time: Optional[str] = None
    time_context: Optional[Literal[
        "morning", "afternoon", "evening", "earliest", "last_slot", "exact"
    ]] = None
    specialty_or_complaint: Optional[str] = None
    specialty_matched: Optional[str] = None
    specialty_confidence: float = 1.0
    extracted_name: Optional[str] = None
    booking_for: Optional[str] = None
    requested_doctor_name: Optional[str] = None
    dob: Optional[date] = None
    is_followup: bool = False
    is_correction: bool = False
    is_silent: bool = False
    clinic_category: Optional[str] = None
    reason: Optional[str] = None
