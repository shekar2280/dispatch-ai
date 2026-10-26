from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.voice.workflow.checkpoint_store import find_resumable_checkpoint
from app.services.voice.workflow.state import VoiceWorkflowState, WorkflowStage


@dataclass
class RecoveryContext:
    checkpoint_id: UUID
    original_call_id: UUID
    stage: str
    intent: str | None = None
    preferred_doctor: str | None = None
    target_date: str | None = None
    target_time: str | None = None
    has_committed_appointment: bool = False
    appointment_id: str | None = None
    appointment_time: str | None = None
    doctor_name: str | None = None


async def find_recovery_context(
    db: AsyncSession,
    org_id: UUID,
    caller_phone: str,
    max_age_seconds: int = 900,
) -> RecoveryContext | None:
    if not settings.VOICE_RECOVERY_ENABLED or settings.VOICE_ROLLOUT_STAGE == "disabled":
        return None

    if settings.VOICE_ROLLOUT_STAGE == "simulator" and not (caller_phone.lower().startswith("sim") or "test" in caller_phone.lower() or caller_phone.startswith("+1555")):
        return None

    if settings.VOICE_ROLLOUT_STAGE == "cohort" and (int(org_id.int) % 100) >= settings.VOICE_ROLLOUT_PERCENTAGE:
        return None

    match = await find_resumable_checkpoint(
        db=db,
        org_id=org_id,
        caller_phone=caller_phone,
        max_age_seconds=max_age_seconds,
    )
    if not match:
        return None

    if settings.VOICE_ROLLOUT_STAGE == "shadow":
        return None

    checkpoint, call_log = match
    safe_state = checkpoint.safe_state or {}
    if not isinstance(safe_state, dict):
        return None

    target_date_val = safe_state.get("target_date")
    if target_date_val and isinstance(target_date_val, str):
        try:
            parsed_date = date.fromisoformat(target_date_val)
            if parsed_date < datetime.now(UTC).date():
                target_date_val = None
        except ValueError:
            target_date_val = None

    has_committed = False
    appt_id = None
    appt_time = None
    doc_name = safe_state.get("preferred_doctor")

    if call_log.booking_result and isinstance(call_log.booking_result, dict):
        has_committed = True
        appt_id = str(call_log.booking_result.get("appointment_id") or "")
        appt_time = str(call_log.booking_result.get("slot_time") or "")
        doc_name = call_log.booking_result.get("doctor_name") or doc_name
    elif safe_state.get("booking_confirmed") or safe_state.get("committed_but_not_acknowledged"):
        has_committed = True
        appt_time = safe_state.get("selected_slot_time") or safe_state.get("target_time")

    return RecoveryContext(
        checkpoint_id=checkpoint.id,
        original_call_id=call_log.id,
        stage=checkpoint.stage,
        intent=safe_state.get("intent"),
        preferred_doctor=doc_name,
        target_date=target_date_val,
        target_time=safe_state.get("target_time") or appt_time,
        has_committed_appointment=has_committed,
        appointment_id=appt_id,
        appointment_time=appt_time,
        doctor_name=doc_name,
    )


def build_recovery_greeting(clinic_name: str, recovery_ctx: RecoveryContext) -> str:
    if recovery_ctx.has_committed_appointment:
        return (
            f"Hello! Thank you for calling {clinic_name}. It looks like our previous call was disconnected "
            f"just as your appointment was confirmed. Would you like me to review the details of your confirmed booking?"
        )
    return (
        f"Hello! Thank you for calling {clinic_name}. It looks like our previous call was disconnected. "
        f"Would you like to pick up where we left off, or start fresh?"
    )


def apply_recovery_preferences(workflow: VoiceWorkflowState, recovery_ctx: RecoveryContext):
    workflow.resumed_from_call_id = str(recovery_ctx.original_call_id)
    workflow.recovery_accepted = True
    workflow.intent = recovery_ctx.intent or "booking"
    workflow.preferred_doctor = recovery_ctx.preferred_doctor
    workflow.target_date = recovery_ctx.target_date
    workflow.target_time = recovery_ctx.target_time
    workflow.candidate_slots = []
    workflow.clear_pending_responses()
    workflow.clear_selection()
    if recovery_ctx.has_committed_appointment:
        workflow.transition_to(WorkflowStage.CLOSING)
    else:
        workflow.transition_to(WorkflowStage.AVAILABILITY)


def decline_recovery_offer(workflow: VoiceWorkflowState):
    workflow.recovery_accepted = False
    workflow.resumed_from_call_id = None
    workflow.preferred_doctor = None
    workflow.target_date = None
    workflow.target_time = None
    workflow.candidate_slots = []
    workflow.clear_pending_responses()
    workflow.clear_selection()
    workflow.transition_to(WorkflowStage.INTAKE)
