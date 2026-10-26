from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID
from datetime import datetime
from typing import Optional, Literal

class DispatchBase(BaseModel):
    location_address: str = Field(min_length=1, max_length=500)
    priority: int = 1
    caller_name: Optional[str] = None
    caller_phone: Optional[str] = None
    chief_complaint: Optional[str] = None
    audio_snippet_url: Optional[str] = None
    status: Literal["unverified", "en_route", "on_scene", "resolved"] = "unverified"
    escalation_deadline: Optional[datetime] = None
    dispatch_source: Optional[str] = "human_dispatcher"

class DispatchCreate(DispatchBase):
    org_id: UUID
    patient_id: Optional[UUID] = None
    dispatcher_id: Optional[UUID] = None
    driver_id: Optional[UUID] = None

class DispatchResponse(DispatchBase):
    id: UUID
    org_id: UUID
    patient_id: Optional[UUID] = None
    dispatcher_id: Optional[UUID] = None
    driver_id: Optional[UUID] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

