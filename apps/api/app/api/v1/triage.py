from fastapi import APIRouter
from app.schemas.triage import TriageRequest, TriageResponse
from app.services.voice.triage_service import classify_triage_intent

router = APIRouter()


@router.post("", response_model=TriageResponse)
@router.post("/triage", response_model=TriageResponse)
async def process_triage(request: TriageRequest):
    return await classify_triage_intent(request)
