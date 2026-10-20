from typing import Literal
from pydantic import BaseModel, Field, ConfigDict
from datetime import date
import uuid
from uuid import UUID
from fastapi import APIRouter, Query, HTTPException, Depends, Request
from sqlalchemy.future import select

from app.core.database import AsyncSessionLocal
from app.core.security import get_current_tenant_org, get_current_user, is_clinic_administrator
from app.core.voice_admission import limit_voice_token_requests
from app.models.user import User
from app.models.call_session import CallLog
from app.services.infra.redis_cache import redis_service
from app.services.telephony import (
    generate_livekit_token,
    check_telephony_health,
    TokenRequest,
    TokenResponse,
    accept_telephony_call,
    hangup_telephony_call,
    end_simulator_call as service_end_simulator_call,
    trigger_ai_takeover_notice,
    resolve_dropped_call_session,
    get_daily_call_logs as service_get_daily_call_logs,
    CallAcceptRequest,
    CallHangupRequest,
    SimulatorEndRequest,
)

router = APIRouter()


ALLOWED_STAFF_ROLES = {"admin", "doctor", "receptionist"}


class SimulatorStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    caller_name: str = Field(default="Test Caller", min_length=1, max_length=120)
    caller_phone: str = Field(min_length=7, max_length=32)



@router.get("/{session_id}/recording")
@router.get("/call-sessions/{session_id}/recording")
async def get_call_recording(session_id: UUID, org_id: UUID = Depends(get_current_tenant_org)):
    from app.services.infra.storage import sign_call_recording
    async with AsyncSessionLocal() as db:
        call = await db.scalar(select(CallLog).where(CallLog.id == session_id, CallLog.org_id == org_id))
        if not call or call.recording_status not in {"ready", "partial"} or not call.recording_storage_path:
            raise HTTPException(404, "Recording not available")
        try:
            url = await sign_call_recording(call.recording_storage_path, org_id, session_id)
        except (ValueError, RuntimeError):
            raise HTTPException(503, "Recording playback unavailable") from None
    return {"url": url, "expires_in_seconds": 300}


@router.get("/allowance")
@router.get("/calls/allowance")
@router.get("/voice/allowance")
async def get_voice_allowance(
    org_id: UUID = Depends(get_current_tenant_org),
):
    async with AsyncSessionLocal() as db:
        from app.services.billing.voice_quota import allowance_snapshot
        return await allowance_snapshot(db, org_id)


@router.post("/simulator/start", response_model=TokenResponse)
@router.post("/calls/simulator/start", response_model=TokenResponse)
@router.post("/voice/simulator/start", response_model=TokenResponse)
async def start_simulator_session(
    req: SimulatorStartRequest,
    request: Request,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
):
    new_call_id = uuid.uuid4()
    server_call_id = str(new_call_id)
    server_room_name = f"call_{new_call_id.hex}"
    server_participant = f"caller_{uuid.uuid4().hex}"

    async with AsyncSessionLocal() as admission_db:
        await limit_voice_token_requests(request, admission_db)
    from app.services.voice.provider_budget import reserve_budget
    await reserve_budget(f"simulator-user:{current_user.id}", rpm=6)
    await reserve_budget(f"simulator-clinic:{org_id}", rpm=3)
    return await generate_livekit_token(
        call_id=server_call_id,
        room_name=server_room_name,
        participant_name=server_participant,
        caller_name=req.caller_name or "Web Simulator Caller",
        phone_number=req.caller_phone,
        override_closed=True,
        org_id=str(org_id),
    )


@router.post("/{room_name}/join", response_model=TokenResponse)
@router.post("/calls/{room_name}/join", response_model=TokenResponse)
@router.post("/voice/calls/{room_name}/join", response_model=TokenResponse)
async def join_active_call(
    room_name: str,
    request: Request,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
):
    user_role = (getattr(current_user, "role", "") or "").lower()
    if user_role not in ALLOWED_STAFF_ROLES:
        raise HTTPException(status_code=403, detail="Unauthorized staff role to join call")

    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(CallLog).where(
                CallLog.room_name == room_name,
                CallLog.org_id == org_id,
                CallLog.end_time.is_(None),
            )
        )
        existing_call = res.scalars().first()
        if not existing_call:
            raise HTTPException(status_code=404, detail="Active call session not found for this organization")

    return await generate_livekit_token(
        call_id=str(existing_call.id),
        room_name=existing_call.room_name,
        participant_name=f"staff_{current_user.id}",
        caller_name=getattr(current_user, "name", None) or f"Staff Member {current_user.id}",
        org_id=str(org_id),
    )


@router.post("/token", response_model=TokenResponse)
async def generate_token(
    req: TokenRequest,
    request: Request,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
):
    if req.org_id:
        try:
            requested_org = UUID(str(req.org_id))
            if requested_org != org_id:
                raise HTTPException(status_code=403, detail="Cross-tenant token generation forbidden")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid org_id format") from None

    if req.room_name:
        return await join_active_call(
            room_name=req.room_name,
            request=request,
            org_id=org_id,
            current_user=current_user,
        )

    return await start_simulator_session(
        req=SimulatorStartRequest(caller_name=req.caller_name or "Test Caller",
                                  caller_phone=req.caller_phone or req.phone_number or "Web Simulator"),
        request=request,
        org_id=org_id,
        current_user=current_user,
    )


@router.post("/{room_name}/accept")
@router.post("/calls/{room_name}/accept")
@router.post("/telephony/calls/{room_name}/accept")
@router.post("/{room_name}/takeover")
@router.post("/calls/{room_name}/takeover")
@router.post("/telephony/calls/{room_name}/takeover")
async def accept_call(
    room_name: str,
    req: CallAcceptRequest,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
):
    user_role = (getattr(current_user, "role", "") or "").lower()
    if user_role not in ALLOWED_STAFF_ROLES:
        raise HTTPException(status_code=403, detail="Unauthorized staff role to accept call")

    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(CallLog).where(
                CallLog.room_name == room_name,
                CallLog.org_id == org_id,
                    CallLog.end_time.is_(None),
            )
        )
        call_log = res.scalars().first()
        if not call_log:
            raise HTTPException(status_code=404, detail="Call session not found for this organization")

    staff_name = getattr(current_user, "full_name", None) or getattr(current_user, "name", None) or "Staff Operator"
    secured_req = CallAcceptRequest(
        staff_id=str(current_user.id),
        staff_name=staff_name,
        role=user_role,
        org_id=str(org_id),
    )
    return await accept_telephony_call(room_name, secured_req)


@router.get("/daily-call-logs")
@router.get("/telephony/daily-call-logs")
async def get_daily_call_logs(
    limit: int = Query(50, ge=1, le=150),
    offset: int = Query(0, ge=0),
    search: str = Query("", max_length=120),
    target_date: date | None = None,
    category: Literal['all', 'missed', 'ai', 'emergency'] = 'all',
    org_id: UUID = Depends(get_current_tenant_org),
):
    return await service_get_daily_call_logs(str(org_id), session_factory=AsyncSessionLocal, limit=limit, offset=offset, search=search, target_date=target_date, category=category)


@router.post("/{room_name}/ai-takeover")
@router.post("/calls/{room_name}/ai-takeover")
async def trigger_ai_takeover(
    room_name: str,
    org_id: UUID = Depends(get_current_tenant_org),
):
    return await trigger_ai_takeover_notice(room_name, str(org_id))


@router.post("/{room_name}/simulator-end")
@router.post("/calls/{room_name}/simulator-end")
async def end_simulator_call(
    room_name: str,
    req: SimulatorEndRequest,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
):
    if str(req.org_id) != str(org_id):
        raise HTTPException(status_code=403, detail="Cross-tenant simulator update forbidden")
    return await service_end_simulator_call(room_name, req)


@router.post("/{room_name}/hangup")
@router.post("/calls/{room_name}/hangup")
@router.post("/telephony/calls/{room_name}/hangup")
async def hangup_call(
    room_name: str,
    req: CallHangupRequest,
    org_id: UUID = Depends(get_current_tenant_org),
    current_user: User = Depends(get_current_user),
):
    user_role = (getattr(current_user, "role", "") or "").lower()
    if user_role not in ALLOWED_STAFF_ROLES:
        raise HTTPException(status_code=403, detail="Unauthorized staff role to hang up call")

    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(CallLog).where(
                CallLog.room_name == room_name,
                CallLog.org_id == org_id,
            )
        )
        call_log = res.scalars().first()
        if not call_log:
            raise HTTPException(status_code=404, detail="Call session not found for this organization")

    call_owner = await redis_service.get_call_owner(room_name)
    if call_owner and str(current_user.id) != str(call_owner):
        async with AsyncSessionLocal() as db:
            if not await is_clinic_administrator(db, org_id, current_user.id):
                raise HTTPException(status_code=403, detail="Only the call owner or clinic administrator can hang up this call")

    secured_req = CallHangupRequest(
        staff_id=str(current_user.id),
        org_id=str(org_id),
    )
    return await hangup_telephony_call(room_name, secured_req)


@router.patch("/call-sessions/{session_id}/resolve")
@router.patch("/telephony/call-sessions/{session_id}/resolve")
@router.patch("/calls/{session_id}/resolve")
async def resolve_dropped_call(
    session_id: str,
    caller_phone: str | None = Query(None),
    org_id: UUID = Depends(get_current_tenant_org),
):
    return await resolve_dropped_call_session(session_id, str(org_id), caller_phone)


@router.get("/health")
async def get_health_status(simulate_down: bool | None = Query(False)):
    return await check_telephony_health(simulate_down=simulate_down or False)
