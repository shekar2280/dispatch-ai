from datetime import date, datetime
from typing import Optional, Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from datetime import datetime as DateTime


class ScheduleOverrideCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    override_type: Optional[str] = "vacation"
    doctor_id: Optional[UUID] = None
    is_available: Optional[bool] = None
    start_date: date
    end_date: date
    custom_hours: Optional[Any] = None
    reason: Optional[str] = None
    emergency_phone: Optional[str] = None

    @model_validator(mode="after")
    def validate_schedule(self):
        if self.end_date < self.start_date:
            raise ValueError("End date cannot be before start date")
        if not self.title.strip():
            raise ValueError("Description is required")
        if self.override_type != "special_hours":
            return self
        if not isinstance(self.custom_hours, list) or not self.custom_hours:
            raise ValueError("Special hours require an opening session")
        sessions = []
        for session in self.custom_hours:
            if not isinstance(session, dict):
                raise ValueError("Invalid opening session")
            times = []
            for key in ("start", "end"):
                value = str(session.get(key, "")).strip().upper()
                try:
                    parsed = DateTime.strptime(value, "%I:%M %p" if value.endswith(("AM", "PM")) else "%H:%M")
                except ValueError:
                    raise ValueError("Invalid session time")
                times.append(parsed.hour * 60 + parsed.minute)
            if times[1] <= times[0]:
                raise ValueError("Closing time must follow opening time")
            sessions.append(times)
        sessions.sort()
        if any(current[0] < previous[1] for previous, current in zip(sessions, sessions[1:])):
            raise ValueError("Opening sessions must not overlap")
        return self


class ScheduleOverrideResponse(BaseModel):
    id: UUID
    org_id: UUID
    doctor_id: Optional[UUID] = None
    title: str
    override_type: str = "vacation"
    is_available: bool = False
    start_date: date
    end_date: date
    custom_hours: Optional[Any] = None
    reason: Optional[str] = None
    emergency_phone: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
