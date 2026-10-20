from fastapi import APIRouter
from app.api.v1 import (
    organization,
    calls,
    clinic_ws,
    telephony_webhook,
    appointments,
    patients,
    team,
    triage,
    clinic_dashboard,
)

api_router = APIRouter()

api_router.include_router(
    appointments.router, prefix="/appointments", tags=["appointments"]
)
api_router.include_router(clinic_dashboard.router, prefix="/clinic", tags=["clinic"])
api_router.include_router(patients.router, prefix="/patients", tags=["patients"])
api_router.include_router(team.router, prefix="/team", tags=["team"])
api_router.include_router(triage.router, prefix="/triage", tags=["triage"])
api_router.include_router(organization.router, prefix="/org", tags=["organization"])
api_router.include_router(calls.router, prefix="/calls", tags=["calls"])
api_router.include_router(calls.router, prefix="/voice", tags=["voice-alias"])
api_router.include_router(
    calls.router, prefix="/telephony", tags=["telephony-controls"]
)
api_router.include_router(
    telephony_webhook.router, prefix="/telephony", tags=["telephony-pstn-twilio"]
)
api_router.include_router(clinic_ws.router, tags=["clinic-websocket"])
