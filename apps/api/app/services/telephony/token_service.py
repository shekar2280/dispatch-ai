import asyncio
import json
import logging
import os
import time
import uuid
from typing import Optional
from uuid import UUID as PyUUID

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.future import select
from sqlalchemy import or_

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.organization import Organization
from app.models.call_session import VoiceCallSession
from app.services.billing.voice_quota import enforce_voice_demo_allowance
from app.services.infra.websocket_manager import ws_manager
from datetime import datetime, timezone, timedelta

try:
    from livekit.api import (
        AccessToken,
        VideoGrants,
        LiveKitAPI,
        ListRoomsRequest,
    )
    LIVEKIT_SDK_AVAILABLE = True
except Exception:
    LIVEKIT_SDK_AVAILABLE = False
    AccessToken = None
    VideoGrants = None

logger = logging.getLogger(__name__)


def get_livekit_url() -> str:
    return settings.LIVEKIT_URL or ""


class TokenRequest(BaseModel):
    call_id: Optional[str] = None
    room_name: Optional[str] = None
    participant_name: Optional[str] = None
    caller_name: Optional[str] = None
    phone_number: Optional[str] = None
    caller_phone: Optional[str] = None
    llm_provider: Optional[str] = "gemini"
    stt_provider: Optional[str] = "deepgram"
    tts_provider: Optional[str] = "deepgram"
    override_closed: Optional[bool] = True
    org_id: Optional[str] = None


class TokenResponse(BaseModel):
    server_url: str
    room_name: str
    participant_name: str
    token: str
    status: str = "open"
    closure_notice: Optional[str] = None
    call_id: Optional[str] = None
    call_budget_seconds: Optional[int] = None
    clinic_name: Optional[str] = None
    called_phone: Optional[str] = None


async def generate_livekit_token(
    call_id: Optional[str] = None,
    room_name: Optional[str] = None,
    participant_name: Optional[str] = None,
    caller_name: Optional[str] = None,
    phone_number: Optional[str] = None,
    llm_provider: Optional[str] = "gemini",
    stt_provider: Optional[str] = "deepgram",
    tts_provider: Optional[str] = "deepgram",
    override_closed: Optional[bool] = False,
    org_id: Optional[str] = None,
) -> TokenResponse:
    if not LIVEKIT_SDK_AVAILABLE:
        raise HTTPException(
            status_code=500,
            detail="livekit-api package is not installed.",
        )
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        raise HTTPException(status_code=503, detail="Voice service credentials are not configured")

    org_closure_notice = None
    is_closed = False
    org = None
    reserved_room_name: Optional[str] = None
    assigned_call_id: Optional[uuid.UUID] = None
    call_budget = None

    if call_id:
        try:
            assigned_call_id = PyUUID(call_id)
        except Exception:
            assigned_call_id = uuid.uuid4()
    else:
        assigned_call_id = uuid.uuid4()

    async with AsyncSessionLocal() as db:
        if org_id:
            try:
                org_uuid = PyUUID(org_id)
                res = await db.execute(
                    select(Organization).where(Organization.id == org_uuid)
                )
                org = res.scalar_one_or_none()
            except Exception:
                org = None

        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")

        if org:
            resolved_org_id = str(org.id)
            reserved_room_name = room_name or f"call_{assigned_call_id.hex}"
            identity_for_quota = participant_name or f"caller_{uuid.uuid4().hex[:6]}"
            if identity_for_quota.startswith("staff_") and room_name:
                call_match = await db.execute(
                    select(VoiceCallSession.id).where(
                        VoiceCallSession.room_name == room_name,
                        VoiceCallSession.org_id == org.id,
                        VoiceCallSession.end_time.is_(None),
                    ).limit(1)
                )
                if call_match.scalar_one_or_none() is None:
                    raise HTTPException(status_code=404, detail="Call session not found for this organization")

            if not identity_for_quota.startswith("staff_"):
                call_budget = await enforce_voice_demo_allowance(db, org.id)
                if call_budget < 1:
                    raise HTTPException(402, "Voice demo allowance exhausted")
                from app.core.voice_admission import check_voice_call_admission
                await check_voice_call_admission(db, org.id)
                existing = await db.execute(
                    select(VoiceCallSession.id)
                    .where(
                        or_(
                            VoiceCallSession.id == assigned_call_id,
                            VoiceCallSession.room_name == reserved_room_name,
                        )
                    )
                    .limit(1)
                )
                if existing.scalar_one_or_none() is None:
                    db.add(VoiceCallSession(
                        id=assigned_call_id,
                        org_id=org.id,
                        caller_phone=phone_number or "Web Simulator",
                        caller_name=caller_name or participant_name or "Incoming Caller",
                        session_type="voice_simulator",
                        room_name=reserved_room_name,
                        start_time=datetime.now(timezone.utc),
                        triage_status="ringing",
                        call_outcome="inquiry",
                        attended_by="Unattended / Missed",
                        chief_complaint="Call disconnected before receptionist answered.",
                        call_budget_seconds=call_budget,
                        caller_identity=identity_for_quota,
                        admission_expires_at=datetime.now(timezone.utc) + timedelta(seconds=settings.VOICE_ADMISSION_TTL_SECONDS),
                    ))
                    await db.commit()

        if org and org.closure_notice:
            org_closure_notice = org.closure_notice
            if (
                "CLOSED" in org.closure_notice.upper()
                or "SHUT" in org.closure_notice.upper()
            ):
                is_closed = True

    if is_closed and not override_closed:
        return TokenResponse(
            server_url=settings.LIVEKIT_URL or "",
            room_name=room_name or f"closed-{uuid.uuid4().hex[:8]}",
            participant_name=participant_name or "",
            token="",
            status="closed",
            closure_notice=org_closure_notice or "Clinic is currently closed.",
            call_id=str(assigned_call_id),
        )

    if org:
        resolved_org_id = str(org.id)
    elif org_id:
        resolved_org_id = str(org_id)
    else:
        raise HTTPException(status_code=400, detail="Organization ID is required.")

    target_room = reserved_room_name or room_name or f"room_{resolved_org_id[:8]}_{uuid.uuid4().hex[:8]}"
    identity = participant_name or f"caller_{uuid.uuid4().hex[:6]}"

    try:
        grant = VideoGrants(
            room_join=True,
            room=target_room,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
        )

        token_builder = AccessToken(
            api_key=settings.LIVEKIT_API_KEY,
            api_secret=settings.LIVEKIT_API_SECRET,
        )
        token_builder.with_identity(identity)
        token_builder.with_name(identity)
        token_builder.with_grants(grant)
        token_builder.with_ttl(timedelta(seconds=settings.VOICE_ADMISSION_TTL_SECONDS))

        meta_dict = {
            "call_id": str(assigned_call_id),
            "phone_number": phone_number or "",
            "caller_phone": phone_number or "",
            "participant_name": participant_name or "",
            "caller_name": caller_name or participant_name or "",
            "llm_provider": "gemini",
            "stt_provider": "deepgram",
            "tts_provider": "deepgram",
            "org_id": resolved_org_id,
            "created_at": time.time(),
        }
        token_builder.with_metadata(json.dumps(meta_dict))
        jwt_token = token_builder.to_jwt()

        is_staff = identity.startswith("staff_")
        if not is_staff:
            await ws_manager.broadcast_to_org(
                resolved_org_id,
                {
                    "event": "CALL_CONNECTING",
                    "room_name": target_room,
                    "caller_phone": phone_number or "",
                    "caller_name": caller_name or participant_name or "",
                    "chief_complaint": "Incoming Patient Voice Call",
                    "timestamp": time.time(),
                },
            )

        return TokenResponse(
            server_url=get_livekit_url(),
            room_name=target_room,
            participant_name=identity,
            token=jwt_token,
            status="open",
            call_id=str(assigned_call_id),
            call_budget_seconds=call_budget,
            clinic_name=org.name,
            called_phone=org.phone,
        )
    except Exception as e:
        if not identity.startswith("staff_"):
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(VoiceCallSession).where(
                        VoiceCallSession.org_id == PyUUID(resolved_org_id),
                        VoiceCallSession.room_name == target_room,
                        VoiceCallSession.end_time.is_(None),
                    )
                )
                failed_session = result.scalars().first()
                if failed_session:
                    failed_session.end_time = datetime.now(timezone.utc)
                    failed_session.duration_seconds = 0
                    failed_session.call_outcome = "service_unavailable"
                    failed_session.triage_status = "MISSED"
                    await db.commit()
        logger.error(f"Token generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def check_telephony_health(simulate_down: bool = False):
    if simulate_down:
        return {
            "status": "down",
            "livekit": False,
            "latency_ms": None,
            "server_url": get_livekit_url(),
            "message": "LiveKit Edge Media Server is restarting or unreachable (simulated).",
        }

    current_url = get_livekit_url()
    if not current_url:
        return {
            "status": "down",
            "livekit": False,
            "latency_ms": None,
            "server_url": "",
            "message": "LiveKit media server URL not configured.",
        }

    start_time = time.time()
    api_url = (
        current_url.replace("wss://", "https://")
        .replace("ws://", "http://")
        .rstrip("/")
    )

    try:
        api = LiveKitAPI(
            api_url,
            settings.LIVEKIT_API_KEY,
            settings.LIVEKIT_API_SECRET,
        )
        try:
            req = ListRoomsRequest()
            await asyncio.wait_for(api.room.list_rooms(req), timeout=2.0)
            latency = round((time.time() - start_time) * 1000, 1)
            return {
                "status": "healthy",
                "livekit": True,
                "latency_ms": latency,
                "server_url": current_url,
                "message": "LiveKit Edge Media Server Operational",
            }
        finally:
            await api.aclose()
    except Exception as e:
        return {
            "status": "down",
            "livekit": False,
            "latency_ms": None,
            "server_url": current_url,
            "message": "LiveKit Edge Media Server is restarting or unreachable.",
            "error": str(e),
        }
