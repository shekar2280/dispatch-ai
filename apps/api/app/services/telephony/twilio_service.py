import logging
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import HTTPException, Response
from sqlalchemy.future import select
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from urllib.parse import urlencode
from xml.sax.saxutils import escape

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.phone_utils import normalize_phone_e164
from app.models.organization import Organization
from app.models.call_session import VoiceCallSession
from app.services.infra.websocket_manager import ws_manager
from app.services.billing.voice_quota import enforce_voice_demo_allowance

logger = logging.getLogger(__name__)


async def handle_twilio_inbound(
    From: Optional[str] = None,
    To: Optional[str] = None,
    CallSid: Optional[str] = None,
    CallerName: Optional[str] = None,
    session_factory=None,
) -> Response:
    raw_called = (To or "").strip()
    raw_caller = (From or "").strip()
    call_sid = CallSid or f"call_{int(time.time())}"
    caller_name = CallerName or "Incoming Caller"

    if not raw_called:
        return Response(
            content="""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Reject reason="unallocated-number"/>
</Response>""",
            media_type="application/xml",
        )

    called_norm = normalize_phone_e164(raw_called)
    called_e164 = called_norm.e164_phone if called_norm.is_valid else raw_called

    caller_norm = normalize_phone_e164(raw_caller)
    caller_phone = caller_norm.e164_phone if caller_norm.is_valid else (raw_caller or "Unknown")

    if CallSid:
        canonical_call_id = uuid.uuid5(uuid.NAMESPACE_OID, call_sid)
    else:
        canonical_call_id = uuid.uuid4()
    room_name = f"call_{canonical_call_id.hex}_{call_sid}"

    maker = session_factory if session_factory is not None else AsyncSessionLocal
    async with maker() as db:
        query = select(Organization).where(Organization.inbound_voice_number == called_e164)
        res = await db.execute(query)
        orgs = res.scalars().all()

        if not orgs:
            logger.warning(f"Rejecting inbound call: number {raw_called} ({called_e164}) not mapped to any organization")
            reject_twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>This number is not registered with any medical facility on this platform. Please verify the number and try again. Goodbye.</Say>
    <Hangup/>
</Response>"""
            return Response(content=reject_twiml, media_type="application/xml")

        if len(orgs) > 1:
            logger.error(f"Ambiguous hotline configuration: number {called_e164} matches multiple organizations")
            return Response(
                content="""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Reject reason="unallocated-number"/>
</Response>""",
                media_type="application/xml",
                status_code=500,
            )

        org = orgs[0]
        org_id = str(org.id)

        existing_res = await db.execute(
            select(VoiceCallSession).where(
                VoiceCallSession.org_id == org.id,
                or_(
                    VoiceCallSession.id == canonical_call_id,
                    VoiceCallSession.room_name == room_name,
                )
            ).limit(1)
        )
        existing_session = existing_res.scalars().first()

        if isinstance(existing_session, VoiceCallSession):
            if existing_session.end_time is not None:
                return Response(
                    content="""<?xml version="1.0" encoding="UTF-8"?>
<Response><Hangup/></Response>""",
                    media_type="application/xml",
                )
            canonical_call_id = existing_session.id
            call_budget = existing_session.call_budget_seconds
            room_name = existing_session.room_name or room_name
        else:
            try:
                call_budget = await enforce_voice_demo_allowance(db, org.id)
                if call_budget < 1:
                    raise HTTPException(status_code=402, detail="Voice demo allowance exhausted")
            except HTTPException as exc:
                if exc.status_code == 402:
                    return Response(content="""<?xml version="1.0" encoding="UTF-8"?>
<Response><Say>This clinic's voice demo allowance has been used. Please contact the clinic directly. Goodbye.</Say><Hangup/></Response>""", media_type="application/xml")
                if exc.status_code == 429:
                    return Response(content="""<?xml version="1.0" encoding="UTF-8"?>
<Response><Say>All phone lines for this clinic are currently busy. Please try calling back in a few minutes. Goodbye.</Say><Hangup/></Response>""", media_type="application/xml")
                return Response(content="""<?xml version="1.0" encoding="UTF-8"?>
<Response><Say>We are unable to connect your call at this time. Please try again later. Goodbye.</Say><Hangup/></Response>""", media_type="application/xml")

            now_utc = datetime.now(timezone.utc)
            new_session = VoiceCallSession(
                id=canonical_call_id,
                org_id=org.id,
                caller_phone=caller_phone,
                caller_name=caller_name,
                caller_identity=None,  # Actual SIP identity is assigned by LiveKit.
                provider_call_sid=call_sid,
                admission_expires_at=now_utc + timedelta(seconds=getattr(settings, "VOICE_ADMISSION_TTL_SECONDS", 45)),
                session_type="voice_call",
                room_name=room_name,
                start_time=now_utc,
                call_status="ringing",
                triage_status="ringing",
                call_outcome="inquiry",
                attended_by="Unattended / Missed",
                chief_complaint="Call disconnected before receptionist answered.",
                call_budget_seconds=call_budget,
            )
            db.add(new_session)
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                existing_res = await db.execute(
                    select(VoiceCallSession).where(
                        VoiceCallSession.org_id == org.id,
                        or_(
                            VoiceCallSession.id == canonical_call_id,
                            VoiceCallSession.room_name == room_name,
                        )
                    ).limit(1)
                )
                existing_session = existing_res.scalars().first()
                if isinstance(existing_session, VoiceCallSession) and existing_session.end_time is None:
                    canonical_call_id = existing_session.id
                    room_name = existing_session.room_name or room_name
                else:
                    return Response(content="<Response><Hangup/></Response>", media_type="application/xml")

    livekit_sip_domain = getattr(settings, "LIVEKIT_SIP_DOMAIN", "sip.livekit.cloud")
    sip_target = f"sip:{room_name}@{livekit_sip_domain}"
    sip_uri = escape(sip_target + "?" + urlencode({"X-Org-Id": org_id,
        "X-Call-Id": str(canonical_call_id), "X-Twilio-CallSid": call_sid,
        "X-Caller-Phone": caller_phone, "X-Caller-Name": caller_name}))

    twiml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Dial timeout="30" timeLimit="{call_budget}" record="false" action="/api/v1/telephony/twilio/dial-status">
        <Sip statusCallback="/api/v1/telephony/twilio/sip-status?{escape(urlencode({'parent_call_sid': call_sid}))}" statusCallbackEvent="initiated ringing answered completed">
            {sip_uri}
        </Sip>
    </Dial>
</Response>"""

    await ws_manager.broadcast_to_org(
        org_id,
        {
            "event": "INCOMING_CALL_RING",
            "call_id": str(canonical_call_id),
            "call_sid": call_sid,
            "room_name": room_name,
            "caller_phone": caller_phone,
            "called_phone": called_e164,
            "org_name": org.name,
            "timestamp": time.time(),
        },
    )

    await ws_manager.broadcast_to_org(
        org_id,
        {
            "event": "TELEPHONY_PSTN_CALL_INITIATED",
            "call_id": str(canonical_call_id),
            "call_sid": call_sid,
            "room_name": room_name,
            "caller_phone": caller_phone,
            "timestamp": time.time(),
        },
    )

    return Response(content=twiml_response, media_type="application/xml")


async def handle_twilio_dial_status(
    CallSid: Optional[str] = None,
    DialCallSid: Optional[str] = None,
    DialCallStatus: Optional[str] = None,
    DialCallDuration: Optional[str] = None,
    session_factory=None,
) -> Response:
    if CallSid:
        canonical_call_id = uuid.uuid5(uuid.NAMESPACE_OID, CallSid)
        status_clean = (DialCallStatus or "").lower()
        duration = int(DialCallDuration) if DialCallDuration and DialCallDuration.isdigit() else 0
        maker = session_factory if session_factory is not None else AsyncSessionLocal

        async with maker() as db:
            query = select(VoiceCallSession).where(VoiceCallSession.id == canonical_call_id).with_for_update()
            res = await db.execute(query)
            session = res.scalars().first()

            if session and (session.end_time is None or (session.call_status == "missed"
                    and status_clean in {"no-answer", "busy", "failed", "canceled"})):
                session.duration_seconds = max(session.duration_seconds or 0, duration)
                if not session.end_time:
                    session.end_time = datetime.now(timezone.utc)

                if status_clean in ["no-answer", "busy", "failed", "canceled"]:
                    if session.connected_at is None:
                        session.call_status = "missed"
                        if (session.triage_status or "").lower() in ["ringing", "completed"]:
                            session.triage_status = "missed"
                        session.call_outcome = {
                            "no-answer": "no_answer",
                            "busy": "line_busy",
                            "failed": "service_unavailable",
                            "canceled": "caller_abandoned",
                        }.get(status_clean, "missed")
                        session.attended_by = "Unattended / Missed"
                        session.chief_complaint = session.chief_complaint or {
                            "no-answer": "The call rang without being answered.",
                            "busy": "All reception lines were busy.",
                            "failed": "The phone service could not connect the call.",
                            "canceled": "The caller ended the call before it was answered.",
                        }.get(status_clean, "The call could not be completed.")
                        await ws_manager.broadcast_to_org(
                            str(session.org_id),
                            {
                                "event": "CALL_MISSED",
                                "call_sid": CallSid,
                                "room_name": session.room_name,
                                "caller_phone": session.caller_phone,
                                "timestamp": time.time(),
                            },
                        )
                elif status_clean == "completed":
                    if session.call_status != "completed":
                        session.call_status = "completed"
                        if (session.triage_status or "").lower() == "ringing":
                            session.triage_status = "completed"

                await db.commit()

    closing_twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Hangup/>
</Response>"""
    return Response(content=closing_twiml, media_type="application/xml")


async def handle_twilio_sip_status(
    parent_call_sid: Optional[str] = None,
    CallSid: Optional[str] = None,
    CallStatus: Optional[str] = None,
    session_factory=None,
) -> dict:
    if parent_call_sid:
        canonical_call_id = uuid.uuid5(uuid.NAMESPACE_OID, parent_call_sid)
        status_clean = (CallStatus or "").lower()
        maker = session_factory if session_factory is not None else AsyncSessionLocal

        async with maker() as db:
            query = select(VoiceCallSession).where(VoiceCallSession.id == canonical_call_id).with_for_update()
            res = await db.execute(query)
            session = res.scalars().first()

            if session and status_clean == "answered":
                if not session.connected_at:
                    session.connected_at = datetime.now(timezone.utc)
                if session.call_status not in {"completed", "missed"}:
                    session.call_status = "in_progress"
                await db.commit()

    return {"status": "recorded", "child_status": CallStatus}


async def handle_twilio_status(
    CallSid: Optional[str] = None,
    CallStatus: Optional[str] = None,
    CallDuration: Optional[str] = None,
    session_factory=None,
) -> dict:
    if not CallSid:
        return {"status": "ignored", "reason": "missing_call_sid"}

    canonical_call_id = uuid.uuid5(uuid.NAMESPACE_OID, CallSid)
    duration = int(CallDuration) if CallDuration and CallDuration.isdigit() else 0
    status_lower = (CallStatus or "").lower()
    maker = session_factory if session_factory is not None else AsyncSessionLocal

    async with maker() as db:
        query = select(VoiceCallSession).where(VoiceCallSession.id == canonical_call_id).with_for_update()
        res = await db.execute(query)
        session = res.scalars().first()

        if session and session.end_time is None:
            session.duration_seconds = max(session.duration_seconds or 0, duration)

            if status_lower in ["completed", "no-answer", "busy", "failed", "canceled"]:
                if not session.end_time:
                    session.end_time = datetime.now(timezone.utc)

                if status_lower in ["no-answer", "busy", "failed", "canceled"]:
                    session.call_status = "missed"
                    if (session.triage_status or "").lower() == "ringing":
                        session.triage_status = "missed"
                    session.call_outcome = {
                        "no-answer": "no_answer",
                        "busy": "line_busy",
                        "failed": "service_unavailable",
                        "canceled": "caller_abandoned",
                    }[status_lower]
                    session.attended_by = "Unattended / Missed"
                    session.chief_complaint = session.chief_complaint or {
                        "no-answer": "The call rang without being answered.",
                        "busy": "All reception lines were busy.",
                        "failed": "The phone service could not connect the call.",
                        "canceled": "The caller ended the call before it was answered.",
                    }[status_lower]
                    await db.commit()
                    await ws_manager.broadcast_to_org(
                        str(session.org_id),
                        {
                            "event": "CALL_MISSED",
                            "call_sid": CallSid,
                            "room_name": session.room_name,
                            "caller_phone": session.caller_phone,
                            "timestamp": time.time(),
                        },
                    )
                elif status_lower == "completed":
                    if session.call_status == "missed":
                        await db.commit()
                    elif session.connected_at is None and (session.call_status == "ringing" or duration == 0):
                        session.call_status = "missed"
                        if (session.triage_status or "").lower() == "ringing":
                            session.triage_status = "missed"
                        session.call_outcome = "caller_abandoned"
                        session.attended_by = "Unattended / Missed"
                        session.chief_complaint = session.chief_complaint or "The caller ended the call before it was answered."
                        await db.commit()
                        await ws_manager.broadcast_to_org(
                            str(session.org_id),
                            {
                                "event": "CALL_MISSED",
                                "call_sid": CallSid,
                                "room_name": session.room_name,
                                "caller_phone": session.caller_phone,
                                "timestamp": time.time(),
                            },
                        )
                    else:
                        session.call_status = "completed"
                        if (session.triage_status or "").lower() == "ringing":
                            session.triage_status = "completed"
                        await db.commit()

    return {"status": "recorded", "call_sid": CallSid, "call_status": CallStatus}
