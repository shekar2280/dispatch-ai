import logging
from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.call_session import VoiceCallSession
from app.models.patient import Patient
from app.models.organization import Organization
from app.services.infra.websocket_manager import ws_manager

logger = logging.getLogger(__name__)


async def handle_trigger_emergency_protocol(
    arguments: Dict[str, Any],
    db: AsyncSession,
    valid_org_id: UUID,
    clean_phone: Optional[str] = None,
) -> Dict[str, Any]:
    chief_complaint = str(arguments.get("chief_complaint", "Severe Emergency")).strip()
    transcript = str(arguments.get("transcript", "")).strip()
    caller_name = str(arguments.get("patient_name") or arguments.get("caller_name") or "Emergency Caller").strip()

    try:
        patient_id = None
        if clean_phone:
            pat_res = await db.execute(
                select(Patient).where(
                    (Patient.org_id == valid_org_id) &
                    (Patient.phone_number == clean_phone)
                )
            )
            patient = pat_res.scalars().first()
            if patient:
                patient_id = patient.id

        org_res = await db.execute(select(Organization).where(Organization.id == valid_org_id))
        org = org_res.scalar_one_or_none()
        emergency_phone = (org.voice_ai_settings or {}).get("emergency_deflection_phone") if org else None

        session_query = await db.execute(
            select(VoiceCallSession)
            .where(
                (VoiceCallSession.org_id == valid_org_id) &
                (VoiceCallSession.caller_phone == clean_phone)
            )
            .order_by(VoiceCallSession.start_time.desc())
            .limit(1)
        )
        call_session = session_query.scalar_one_or_none()

        if call_session:
            call_session.triage_status = "emergency"
            call_session.intent_classification = "EMERGENCY_SOS"
            call_session.security_flagged = True
            call_session.chief_complaint = chief_complaint
            if patient_id:
                call_session.patient_id = patient_id
            await db.commit()
            await db.refresh(call_session)

        alert_payload = {
            "event": "EMERGENCY_SOS_ALERT",
            "session_id": str(call_session.id) if call_session else None,
            "org_id": str(valid_org_id),
            "caller_phone": clean_phone or "Unknown",
            "caller_name": caller_name,
            "chief_complaint": chief_complaint,
            "emergency_phone": emergency_phone,
            "transcript": transcript,
            "triage_status": "emergency",
        }
        await ws_manager.broadcast_to_org(str(valid_org_id), alert_payload)

        return {
            "status": "emergency_triggered",
            "emergency_phone": emergency_phone,
            "chief_complaint": chief_complaint,
            "message": f"Medical emergency registered. Caller advised to call {emergency_phone} or proceed to nearest emergency department immediately."
            if emergency_phone else "Medical emergency registered. Caller advised to contact local emergency services or proceed to the nearest emergency department immediately.",
        }
    except Exception as e:
        logger.error(f"Error handling emergency protocol: {e}")
        return {
            "status": "error",
            "reason": str(e),
        }


async def handle_update_live_emergency_intake(
    arguments: Dict[str, Any],
    db: AsyncSession,
    valid_org_id: UUID,
    clean_phone: Optional[str] = None,
) -> Dict[str, Any]:
    caller_name = str(arguments.get("caller_name", "")).strip()
    chief_complaint = str(arguments.get("chief_complaint", "")).strip()
    patient_condition = str(arguments.get("patient_condition", "")).strip()

    session_query = await db.execute(
        select(VoiceCallSession)
        .where(
            (VoiceCallSession.org_id == valid_org_id) &
            (VoiceCallSession.caller_phone == clean_phone)
        )
        .order_by(VoiceCallSession.start_time.desc())
        .limit(1)
    )
    call_session = session_query.scalar_one_or_none()

    if call_session:
        call_session.triage_status = "emergency"
        call_session.security_flagged = True
        combined = f"{chief_complaint} {patient_condition}".strip()
        if combined:
            call_session.chief_complaint = combined
        if caller_name:
            call_session.caller_name = caller_name
        await db.commit()
        await db.refresh(call_session)

    payload = {
        "event": "LIVE_EMERGENCY_INTAKE_UPDATED",
        "session_id": str(call_session.id) if call_session else None,
        "org_id": str(valid_org_id),
        "caller_phone": clean_phone,
        "caller_name": caller_name or (call_session.caller_name if call_session else "Emergency Caller"),
        "chief_complaint": chief_complaint or (call_session.chief_complaint if call_session else "Emergency"),
        "patient_condition": patient_condition,
        "triage_status": "emergency",
    }
    await ws_manager.broadcast_to_org(str(valid_org_id), payload)
    return {
        "status": "success",
        "session_id": str(call_session.id) if call_session else None,
    }
