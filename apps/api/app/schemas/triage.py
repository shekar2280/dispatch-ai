from pydantic import BaseModel, Field
from typing import Optional, Literal


class TriageRequest(BaseModel):
    speech_text: str = Field(min_length=1, max_length=2000)
    phone_number: Optional[str] = None


class TriageResponse(TriageRequest):
    intent: Literal["EMERGENCY", "ADMINISTRATIVE"]
    urgency_score: int
    reason: str
