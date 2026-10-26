import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class WorkflowStage(StrEnum):
    INTAKE = "intake"
    RECOVERY = "recovery"
    AVAILABILITY = "availability"
    SLOT_SELECTION = "slot_selection"
    BOOKING_DETAILS = "booking_details"
    BOOKING_CONFIRMATION = "booking_confirmation"
    IDENTITY_LOOKUP = "identity_lookup"
    IDENTITY_VERIFIED = "identity_verified"
    RESCHEDULE_CONFIRMATION = "reschedule_confirmation"
    CANCEL_CONFIRMATION = "cancel_confirmation"
    CLOSING = "closing"


VALID_TRANSITIONS: dict[WorkflowStage, set[WorkflowStage]] = {
    WorkflowStage.INTAKE: {
        WorkflowStage.RECOVERY,
        WorkflowStage.AVAILABILITY,
        WorkflowStage.SLOT_SELECTION,
        WorkflowStage.BOOKING_DETAILS,
        WorkflowStage.BOOKING_CONFIRMATION,
        WorkflowStage.IDENTITY_LOOKUP,
        WorkflowStage.IDENTITY_VERIFIED,
        WorkflowStage.CLOSING,
        WorkflowStage.INTAKE,
    },
    WorkflowStage.RECOVERY: {
        WorkflowStage.INTAKE,
        WorkflowStage.AVAILABILITY,
        WorkflowStage.SLOT_SELECTION,
        WorkflowStage.BOOKING_DETAILS,
        WorkflowStage.BOOKING_CONFIRMATION,
        WorkflowStage.IDENTITY_LOOKUP,
        WorkflowStage.IDENTITY_VERIFIED,
        WorkflowStage.CLOSING,
        WorkflowStage.RECOVERY,
    },
    WorkflowStage.AVAILABILITY: {
        WorkflowStage.SLOT_SELECTION,
        WorkflowStage.BOOKING_DETAILS,
        WorkflowStage.BOOKING_CONFIRMATION,
        WorkflowStage.INTAKE,
        WorkflowStage.CLOSING,
        WorkflowStage.AVAILABILITY,
    },
    WorkflowStage.SLOT_SELECTION: {
        WorkflowStage.BOOKING_DETAILS,
        WorkflowStage.BOOKING_CONFIRMATION,
        WorkflowStage.AVAILABILITY,
        WorkflowStage.INTAKE,
        WorkflowStage.CLOSING,
        WorkflowStage.SLOT_SELECTION,
    },
    WorkflowStage.BOOKING_DETAILS: {
        WorkflowStage.BOOKING_CONFIRMATION,
        WorkflowStage.SLOT_SELECTION,
        WorkflowStage.INTAKE,
        WorkflowStage.CLOSING,
        WorkflowStage.BOOKING_DETAILS,
    },
    WorkflowStage.BOOKING_CONFIRMATION: {
        WorkflowStage.CLOSING,
        WorkflowStage.SLOT_SELECTION,
        WorkflowStage.AVAILABILITY,
        WorkflowStage.INTAKE,
        WorkflowStage.BOOKING_CONFIRMATION,
    },
    WorkflowStage.IDENTITY_LOOKUP: {
        WorkflowStage.IDENTITY_VERIFIED,
        WorkflowStage.CANCEL_CONFIRMATION,
        WorkflowStage.RESCHEDULE_CONFIRMATION,
        WorkflowStage.SLOT_SELECTION,
        WorkflowStage.INTAKE,
        WorkflowStage.CLOSING,
        WorkflowStage.IDENTITY_LOOKUP,
    },
    WorkflowStage.IDENTITY_VERIFIED: {
        WorkflowStage.SLOT_SELECTION,
        WorkflowStage.BOOKING_DETAILS,
        WorkflowStage.BOOKING_CONFIRMATION,
        WorkflowStage.CANCEL_CONFIRMATION,
        WorkflowStage.RESCHEDULE_CONFIRMATION,
        WorkflowStage.INTAKE,
        WorkflowStage.CLOSING,
        WorkflowStage.IDENTITY_VERIFIED,
    },
    WorkflowStage.CANCEL_CONFIRMATION: {
        WorkflowStage.CLOSING,
        WorkflowStage.INTAKE,
        WorkflowStage.CANCEL_CONFIRMATION,
    },
    WorkflowStage.RESCHEDULE_CONFIRMATION: {
        WorkflowStage.SLOT_SELECTION,
        WorkflowStage.INTAKE,
        WorkflowStage.CLOSING,
        WorkflowStage.RESCHEDULE_CONFIRMATION,
    },
    WorkflowStage.CLOSING: {
        WorkflowStage.INTAKE,
        WorkflowStage.CLOSING,
    },
}


class InvalidWorkflowTransitionError(ValueError):
    pass


@dataclass
class VoiceWorkflowState:
    stage: WorkflowStage = WorkflowStage.INTAKE
    intent: str = "inquiry"
    caller_name: str | None = None
    caller_phone: str = ""
    patient_id: str | None = None
    verified_name: str | None = None
    patient_verified: bool = False
    preferred_doctor: str | None = None
    target_date: str | None = None
    target_time: str | None = None
    selected_slot_time: str | None = None
    selected_slot_key: str | None = None
    chief_complaint: str | None = None
    candidate_slots: list[dict[str, Any]] = field(default_factory=list)
    selected_slot: dict[str, Any] | None = None
    last_slot_search: dict[str, Any] | None = None
    pending_slot_search_response: bool = False
    pending_booking_readback: bool = False
    prepared_booking: dict[str, Any] | None = None
    prepared_cancellation: dict[str, Any] | None = None
    pending_cancellation_appointment_id: str | None = None
    active_appointments: list[dict[str, Any]] = field(default_factory=list)
    confirmation_pending: bool = False
    last_readback_text: str | None = None
    readback_completed: bool = False
    booking_confirmed: bool = False
    token_number: int | None = None
    service_unavailable: bool = False
    agent_paused: bool = False
    call_completed: bool = False
    pending_deterministic_response: str | None = None
    consecutive_unrecognized: int = 0
    workflow_version: int = 1
    state_version: int = 1
    last_completed_event_id: str | None = None
    expires_at: str | None = None
    resumed_from_call_id: str | None = None
    recovery_offered: bool = False
    recovery_accepted: bool = False
    committed_but_not_acknowledged: bool = False

    def can_transition_to(self, target_stage: WorkflowStage | str) -> bool:
        try:
            resolved = WorkflowStage(target_stage) if isinstance(target_stage, str) else target_stage
        except ValueError:
            return False
        allowed = VALID_TRANSITIONS.get(self.stage, set())
        return resolved in allowed

    def transition_to(self, target_stage: WorkflowStage | str, strict: bool = False) -> bool:
        try:
            resolved = WorkflowStage(target_stage) if isinstance(target_stage, str) else target_stage
        except ValueError:
            if strict:
                raise InvalidWorkflowTransitionError(f"Unknown workflow stage: {target_stage}") from None
            logger.warning("Unknown workflow stage attempted: %s", target_stage)
            return False
        if not self.can_transition_to(resolved):
            if strict:
                raise InvalidWorkflowTransitionError(f"Invalid transition: {self.stage} -> {resolved}")
            logger.warning("Invalid workflow transition attempted: %s -> %s", self.stage, resolved)
            return False
        self.stage = resolved
        self.state_version += 1
        return True

    def clear_pending_responses(self):
        self.pending_deterministic_response = None
        self.pending_slot_search_response = False
        self.pending_booking_readback = False

    def clear_selection(self):
        self.selected_slot = None
        self.selected_slot_time = None
        self.selected_slot_key = None
        self.prepared_booking = None
        self.confirmation_pending = False
        self.readback_completed = False

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "intent": self.intent,
            "patient_verified": self.patient_verified,
            "preferred_doctor": self.preferred_doctor,
            "target_date": self.target_date,
            "target_time": self.target_time,
            "selected_slot_time": self.selected_slot_time,
            "candidate_count": len(self.candidate_slots),
            "has_selected_slot": self.selected_slot is not None,
            "has_prepared_booking": self.prepared_booking is not None,
            "confirmation_pending": self.confirmation_pending,
            "readback_completed": self.readback_completed,
            "booking_confirmed": self.booking_confirmed,
            "service_unavailable": self.service_unavailable,
            "agent_paused": self.agent_paused,
            "call_completed": self.call_completed,
            "workflow_version": self.workflow_version,
            "state_version": self.state_version,
            "last_completed_event_id": self.last_completed_event_id,
            "resumed_from_call_id": self.resumed_from_call_id,
            "recovery_offered": self.recovery_offered,
            "recovery_accepted": self.recovery_accepted,
            "committed_but_not_acknowledged": self.committed_but_not_acknowledged,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "intent": self.intent,
            "caller_name": self.caller_name,
            "caller_phone": self.caller_phone,
            "patient_id": self.patient_id,
            "verified_name": self.verified_name,
            "patient_verified": self.patient_verified,
            "preferred_doctor": self.preferred_doctor,
            "target_date": self.target_date,
            "target_time": self.target_time,
            "selected_slot_time": self.selected_slot_time,
            "selected_slot_key": self.selected_slot_key,
            "chief_complaint": self.chief_complaint,
            "candidate_slots": self.candidate_slots,
            "selected_slot": self.selected_slot,
            "last_slot_search": self.last_slot_search,
            "pending_slot_search_response": self.pending_slot_search_response,
            "pending_booking_readback": self.pending_booking_readback,
            "prepared_booking": self.prepared_booking,
            "prepared_cancellation": self.prepared_cancellation,
            "pending_cancellation_appointment_id": self.pending_cancellation_appointment_id,
            "active_appointments": self.active_appointments,
            "confirmation_pending": self.confirmation_pending,
            "last_readback_text": self.last_readback_text,
            "readback_completed": self.readback_completed,
            "booking_confirmed": self.booking_confirmed,
            "token_number": self.token_number,
            "service_unavailable": self.service_unavailable,
            "agent_paused": self.agent_paused,
            "call_completed": self.call_completed,
            "pending_deterministic_response": self.pending_deterministic_response,
            "consecutive_unrecognized": self.consecutive_unrecognized,
            "workflow_version": self.workflow_version,
            "state_version": self.state_version,
            "last_completed_event_id": self.last_completed_event_id,
            "expires_at": self.expires_at,
            "resumed_from_call_id": self.resumed_from_call_id,
            "recovery_offered": self.recovery_offered,
            "recovery_accepted": self.recovery_accepted,
            "committed_but_not_acknowledged": self.committed_but_not_acknowledged,
        }

    def __getitem__(self, key: str) -> Any:
        if not hasattr(self, key):
            raise KeyError(key)
        val = getattr(self, key)
        if isinstance(val, WorkflowStage):
            return val.value
        return val

    def __setitem__(self, key: str, value: Any) -> None:
        if key in ("stage", "workflow_stage"):
            self.transition_to(value)
            return
        if not hasattr(self, key):
            setattr(self, key, value)
            return
        current = getattr(self, key)
        if isinstance(current, WorkflowStage):
            self.transition_to(value)
            return
        setattr(self, key, value)
        self.state_version += 1

    def __contains__(self, key: str) -> bool:
        if not hasattr(self, key):
            return False
        val = getattr(self, key)
        if isinstance(val, bool):
            return val
        return val is not None

    def get(self, key: str, default: Any = None) -> Any:
        if not hasattr(self, key):
            return default
        val = getattr(self, key)
        if val is None:
            return default
        if isinstance(val, WorkflowStage):
            return val.value
        return val

    def pop(self, key: str, default: Any = None) -> Any:
        if not hasattr(self, key):
            return default
        val = getattr(self, key)
        if val is None:
            return default
        if isinstance(val, bool):
            setattr(self, key, False)
        else:
            setattr(self, key, None)
        self.state_version += 1
        return val

    def update(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            self[k] = v
