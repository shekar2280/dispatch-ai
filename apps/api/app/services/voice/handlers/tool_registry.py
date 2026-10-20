import logging
from typing import Dict, Any, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.services.voice.handlers.emergency_tools import (
    handle_trigger_emergency_protocol,
    handle_update_live_emergency_intake,
)
from app.services.voice.handlers.clinic_tool_handler import dispatch_clinic_tool

logger = logging.getLogger(__name__)

SUPPORTED_TOOLS = {
    "verify_patient_identity",
    "search_doctor_slots",
    "confirm_appointment_booking",
    "reschedule_appointment",
    "cancel_appointment",
    "lookup_clinic_faq",
    "check_doctor_live_status",
    "transfer_to_human_operator",
    "trigger_emergency_protocol",
    "update_live_emergency_intake",
}


async def dispatch_tool_execution(
    tool_name: str,
    arguments: Dict[str, Any],
    db: AsyncSession,
    org_id: UUID,
    clean_phone: Optional[str] = None,
    call_session_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    logger.info(f"[TOOL ROUTER] '{tool_name}' | args={list(arguments.keys())}")

    if tool_name not in SUPPORTED_TOOLS:
        logger.warning(f"[TOOL ROUTER] Unknown tool '{tool_name}'. Returning error.")
        return {"error": f"Unknown tool: {tool_name}"}

    from app.models.organization import Organization
    from app.models.call_session import CallLog
    if call_session_id:
        call = await db.scalar(select(CallLog).where(CallLog.id == call_session_id,
            CallLog.org_id == org_id, CallLog.end_time.is_(None), CallLog.provider_started_at.is_not(None)))
        if not call:
            return {"status": "unavailable", "message": "This call is no longer active."}
        if tool_name in {"trigger_emergency_protocol", "update_live_emergency_intake", "cancel_appointment"}:
            return {"status": "reception_required", "message": "Please contact reception for existing appointment details or changes."}

    org_res = await db.execute(select(Organization).where(Organization.id == org_id))
    org_obj = org_res.scalar_one_or_none()
    if not org_obj:
        return {"status": "unavailable", "message": "Clinic configuration is unavailable."}
    valid_org_id = org_obj.id

    if tool_name in ("trigger_emergency_protocol", "update_live_emergency_intake"):
        if tool_name == "trigger_emergency_protocol":
            return await handle_trigger_emergency_protocol(
                arguments, db, valid_org_id, clean_phone
            )
        return await handle_update_live_emergency_intake(
            arguments, db, valid_org_id, clean_phone
        )

    return await dispatch_clinic_tool(
        tool_name=tool_name,
        arguments=arguments,
        db=db,
        org_id=valid_org_id,
        clean_phone=clean_phone,
        call_session_id=call_session_id,
    )
