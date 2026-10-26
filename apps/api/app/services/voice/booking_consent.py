"""Persisted consent is read from transcript events, never from model arguments."""
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.call_turn import VoiceCallTurn
from app.models.call_session import CallLog


from app.agent.confirmation import is_explicit_confirmation


async def authorize_booking(db, org_id, call_id, details):
    call = await db.scalar(select(CallLog).where(
        CallLog.id == call_id, CallLog.org_id == org_id).with_for_update().execution_options(populate_existing=True))
    if (not call or call.end_time or not call.provider_started_at
            or not call.deadline_at or call.deadline_at <= datetime.now(timezone.utc)):
        return None, {"status": "call_ended", "message": "This call is no longer active."}
    if isinstance(call.booking_result, dict):
        return call, call.booking_result
    proposal = call.booking_proposal or {}
    if proposal.get("details") != details:
        return call, {"status": "confirmation_required", "message": "Read back the current details and ask for confirmation."}
    events = (await db.execute(select(VoiceCallTurn).where(
        VoiceCallTurn.org_id == org_id, VoiceCallTurn.session_id == call_id,
        VoiceCallTurn.event_id.is_not(None)).order_by(VoiceCallTurn.turn_number.desc()).limit(3))).scalars().all()
    caller = next((event for event in events if event.user_transcript), None)
    readback = next((event for event in events if event.ai_response_text), None)
    if (not caller or not readback or readback.interrupted
            or readback.event_id != proposal.get("readback_event_id")
            or caller.event_id == proposal.get("caller_event_id")
            or caller.turn_number <= readback.turn_number
            or not is_explicit_confirmation(caller.user_transcript)):
        return call, {"status": "confirmation_required", "message": "Read back the current booking details, then wait for the caller's response."}
    return call, None
