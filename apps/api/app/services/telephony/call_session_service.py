import json
import logging
import time
from typing import Optional
from uuid import UUID as PyUUID
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.future import select
from sqlalchemy import or_

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.call_session import VoiceCallSession
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.services.telephony.call_query_service import load_call_page
from app.services.voice.call_session import clear_call_session
from app.services.infra.redis_cache import redis_service, presence_service
from app.services.infra.websocket_manager import ws_manager

try:
    from livekit.api import (
        AccessToken,
        VideoGrants,
        LiveKitAPI,
        DeleteRoomRequest,
    )
    LIVEKIT_SDK_AVAILABLE = True
except Exception:
    LIVEKIT_SDK_AVAILABLE = False
    AccessToken = None
    VideoGrants = None


class CallAcceptRequest(BaseModel):
    staff_id: str
    staff_name: str
    role: str = "dispatcher"
    org_id: str


class CallHangupRequest(BaseModel):
    staff_id: str
    org_id: str


class SimulatorEndRequest(BaseModel):
    org_id: str
    caller_phone: Optional[str] = None
    caller_name: Optional[str] = None
    call_outcome: str = "caller_abandoned"


async def accept_telephony_call(room_name: str, req: CallAcceptRequest):
    if not LIVEKIT_SDK_AVAILABLE:
        raise HTTPException(status_code=500, detail="LiveKit SDK unavailable")

    locked = await redis_service.acquire_call_lock(
        room_name, req.staff_id, ttl_seconds=300
    )
    if not locked:
        owner = await redis_service.get_call_owner(room_name)
        if owner and owner != req.staff_id:
            raise HTTPException(
                status_code=409,
                detail=f"Call already claimed by another operator ({owner}).",
            )

    presence_service.set_staff_busy(
        org_id=req.org_id,
        staff_id=req.staff_id,
        room_name=room_name,
    )

    await ws_manager.broadcast_to_org(
        req.org_id,
        {
            "event": "CALL_ANSWERED",
            "room_name": room_name,
            "staff_id": req.staff_id,
            "staff_name": req.staff_name,
            "role": req.role,
            "timestamp": time.time(),
        },
    )

    grant = VideoGrants(
        room_join=True,
        room=room_name,
        can_publish=True,
        can_subscribe=True,
        can_publish_data=True,
    )

    token = AccessToken(
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET,
    )
    token.with_identity(f"staff_{req.staff_id}")
    token.with_name(req.staff_name)
    token.with_metadata(
        json.dumps({"role": req.role, "staff_id": req.staff_id, "name": req.staff_name})
    )
    token.with_grants(grant)

    return {
        "server_url": settings.LIVEKIT_URL,
        "room_name": room_name,
        "token": token.to_jwt(),
        "staff_id": req.staff_id,
        "role": req.role,
        "status": "connected",
    }


async def hangup_telephony_call(room_name: str, req: CallHangupRequest):
    async with AsyncSessionLocal() as db:
        call = await db.scalar(select(VoiceCallSession).where(
            VoiceCallSession.org_id == PyUUID(req.org_id), VoiceCallSession.room_name == room_name))
        if not call:
            raise HTTPException(404, "Call session not found")
    from app.services.voice.lifecycle import terminate_call
    await terminate_call(call.id, call.org_id, "staff_hangup")
    presence_service.set_staff_available(
        org_id=req.org_id,
        staff_id=req.staff_id,
    )
    await redis_service.release_call_lock(room_name)

    await ws_manager.broadcast_to_org(
        req.org_id,
        {
            "event": "CALL_ENDED",
            "room_name": room_name,
            "staff_id": req.staff_id,
            "timestamp": time.time(),
        },
    )
    return {"status": "hung_up", "room_name": room_name, "staff_id": req.staff_id}


async def end_simulator_call(room_name: str, req: SimulatorEndRequest):
    try:
        org_uuid = PyUUID(req.org_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid org_id UUID format")

    async with AsyncSessionLocal() as db:
        session = await db.scalar(select(VoiceCallSession).where(
            VoiceCallSession.org_id == org_uuid, VoiceCallSession.room_name == room_name,
            VoiceCallSession.session_type == "voice_simulator"))
        if not session:
            raise HTTPException(404, "Call session not found")
        call_id = session.id
    from app.services.voice.lifecycle import terminate_call
    await terminate_call(call_id, org_uuid, req.call_outcome if req.call_outcome in {"caller_abandoned", "service_unavailable", "line_busy"} else "caller_abandoned")
    return {"status": "recorded", "room_name": room_name}


async def trigger_ai_takeover_notice(room_name: str, org_id: str):
    await ws_manager.broadcast_to_org(
        org_id,
        {
            "event": "AI_TAKEOVER_ACTIVE",
            "room_name": room_name,
            "timestamp": time.time(),
        },
    )
    return {"status": "ai_takeover_broadcasted", "room_name": room_name}


async def resolve_dropped_call_session(
    session_id: str,
    org_id: Optional[str] = None,
    caller_phone: Optional[str] = None,
):
    try:
        org_uuid = PyUUID(str(org_id))
    except (ValueError, TypeError):
        raise HTTPException(400, "Valid organization required")
    try:
        call_uuid = PyUUID(session_id)
        identity_filter = VoiceCallSession.id == call_uuid
    except ValueError:
        identity_filter = VoiceCallSession.room_name == session_id
    async with AsyncSessionLocal() as db:
        call = await db.scalar(select(VoiceCallSession).where(
            VoiceCallSession.org_id == org_uuid, identity_filter).with_for_update())
        if not call:
            raise HTTPException(404, "Call session not found")
        call.call_outcome = "resolved"
        await db.commit()
    await ws_manager.broadcast_to_org(str(org_uuid), {
        "event": "CALL_RESOLVED", "session_id": str(call.id), "room_name": call.room_name})
    return {"status": "resolved", "resolved_count": 1}


async def get_daily_call_logs(org_id: Optional[str], session_factory=None, *, limit=50, offset=0, search="", target_date=None, category="all"):
    if not org_id:
        raise HTTPException(status_code=400, detail="org_id parameter is required")
    try:
        org_uuid = PyUUID(org_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid org_id UUID format")

    maker = session_factory if session_factory is not None else AsyncSessionLocal
    async with maker() as db:
        sessions, booked_session_ids, metrics, counts = await load_call_page(db, org_uuid, limit, offset, search, target_date, category)
        patient_ids = {session.patient_id for session in sessions if session.patient_id}
        linked_patients = (await db.execute(select(Patient).where(
            Patient.org_id == org_uuid, Patient.id.in_(patient_ids),
        ))).scalars().all() if patient_ids else []
        patient_names = {patient.id: f"{patient.first_name} {patient.last_name}".strip() for patient in linked_patients}

    def _check_missed(sess: VoiceCallSession) -> bool:
        if sess.id in booked_session_ids:
            return False
        ts = (sess.triage_status or "").lower()
        co = (sess.call_outcome or "").lower()
        ab = (sess.attended_by or "").lower()
        if co in {"caller_abandoned", "no_answer", "line_busy", "service_unavailable", "caller_silent", "missed"}:
            return True
        if "unattended" in ab or "missed" in ab:
            return True
        if (
            (sess.duration_seconds or 0) == 0
            and not (sess.full_transcript or "").strip()
            and (
                sess.end_time is not None
                or ts in ["ringing", "admin", "unclassified", "missed"]
                or co in ["ringing", "caller_abandoned", "missed"]
            )
        ):
            return True
        return ts == "missed"

    logs = []
    for s in sessions:
        is_miss = _check_missed(s)
        is_booked = s.id in booked_session_ids
        is_emergency = not is_miss and not is_booked and (
            (s.triage_status or "").lower() == "emergency"
            or (s.call_outcome or "").lower() == "emergency_deflected"
            or "emergency" in (s.chief_complaint or "").lower()
            or "108" in (s.chief_complaint or "").lower()
            or "chest pain" in (s.chief_complaint or "").lower()
        )
        att = (s.attended_by or "").lower()
        is_human = not is_miss and "ai" not in att and any(
            role in att
            for role in ["dispatcher", "officer", "human", "nurse", "doctor", "receptionist", "staff"]
        )

        outcome = (
            "appointment_booked"
            if is_booked
            else "emergency_deflected"
            if is_emergency
            else (s.call_outcome or "inquiry").lower()
        )
        missed_reason = {
            "caller_silent": "Caller did not speak",
            "speech_unrecognized": "Caller speech could not be transcribed",
            "caller_abandoned": "Caller ended the call before connection",
            "no_answer": "Call was not answered",
            "line_busy": "Reception lines were busy",
            "service_unavailable": "Reception service unavailable",
            "missed": "Call was missed",
            "ringing": "Call ended while ringing",
        }.get(outcome, "Call ended before connection" if is_miss else None)

        triage_status = (
            "MISSED"
            if is_miss
            else "EMERGENCY"
            if is_emergency
            else "APPOINTMENT"
            if is_booked
            else "HUMAN_TAKEOVER"
            if is_human
            else (s.triage_status or "INQUIRY").upper()
        )

        handled_by = (
            "Unattended / Missed"
            if is_miss
            else "Front Desk Receptionist"
            if is_human
            else "Handled by Tulsi (AI)"
        )

        summary_text = (
            "Appointment booked during this call."
            if is_booked
            else "Emergency medical distress detected. Caller advised to seek local emergency care."
            if is_emergency
            else s.chief_complaint
            or s.full_transcript
            or (
                missed_reason
                or ("Call disconnected before connection." if is_miss else "General inquiry addressed.")
            )
        )

        recording_url = s.audio_recording_url
        if s.recording_status in {"ready", "partial"} and s.recording_storage_path:
            from app.services.infra.storage import sign_call_recording
            try:
                recording_url = await sign_call_recording(s.recording_storage_path, s.org_id, s.id)
            except Exception:
                logging.getLogger(__name__).exception("Unable to sign call recording playback")
                recording_url = None
        logs.append(
            {
                "id": str(s.id),
                "caller_phone": s.caller_phone,
                "patient_id": str(s.patient_id) if s.patient_id else None,
                "patient_name": patient_names.get(s.patient_id),
                "caller_name": s.caller_name or "Anonymous Caller",
                "start_time": s.start_time.isoformat() if s.start_time else "",
                "duration_seconds": s.duration_seconds or 0,
                "triage_status": triage_status,
                "call_outcome": outcome,
                "missed_reason": missed_reason,
                "handled_by": handled_by,
                "is_missed": is_miss,
                "summary": summary_text,
                "full_transcript": s.full_transcript or "",
                "total_turns": s.total_turns or 0,
                "turns": s.turns or [],
                "telemetry_summary": s.telemetry_summary or {},
                "recording_status": getattr(s, "recording_status", "disabled") or "disabled",
                "audio_recording_url": recording_url,
                "room_name": s.room_name,
            }
        )

    return {
        "metrics": metrics,
        "counts": counts,
        "total": counts[category],
        "has_more": offset + len(logs) < counts[category],
        "logs": logs,
    }
