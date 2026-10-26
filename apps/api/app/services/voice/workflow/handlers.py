from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.voice.handlers.clinic_tool_handler import dispatch_clinic_tool
from app.services.voice.workflow.responses import (
    booking_readback_response,
    booking_success_response,
    cancellation_success_response,
    clarify_name_response,
    emergency_response,
    farewell_response,
    slot_search_response,
    transfer_response,
)
from app.services.voice.workflow.state import VoiceWorkflowState, WorkflowStage


class VoiceWorkflowHandler:
    @staticmethod
    async def handle_slot_search(
        state: VoiceWorkflowState,
        db: AsyncSession,
        org_id: UUID,
        doctor_name: str | None = None,
        date_str: str | None = None,
        time_str: str | None = None,
    ) -> str:
        args = {
            "doctor_name": doctor_name or state.preferred_doctor,
            "preferred_date": date_str or state.target_date or "tomorrow",
            "preferred_time": time_str or state.target_time,
        }
        result = await dispatch_clinic_tool(
            "search_doctor_slots",
            args,
            db,
            org_id,
            clean_phone=state.caller_phone,
        )
        offers = result.get("offers", [])
        state.candidate_slots = offers
        state.last_slot_search = result
        state.preferred_doctor = result.get("doctor") or doctor_name or state.preferred_doctor
        state.target_date = result.get("date") or date_str or state.target_date
        state.transition_to(WorkflowStage.SLOT_SELECTION if offers else WorkflowStage.AVAILABILITY)
        return slot_search_response(result)

    @staticmethod
    def handle_slot_selection(
        state: VoiceWorkflowState,
        selected_slot: dict[str, Any],
    ) -> str:
        state.selected_slot = selected_slot
        state.target_time = str(selected_slot.get("label") or selected_slot.get("time") or "")
        state.selected_slot_time = state.target_time
        parts = (state.caller_name or "").strip().split(" ", 1)
        first_name = parts[0] if parts and parts[0] else None
        last_name = parts[1] if len(parts) > 1 else ""
        if first_name:
            state.prepared_booking = {
                "doctor_name": state.preferred_doctor or "the doctor",
                "slot_date": state.target_date or "tomorrow",
                "slot_time": state.target_time,
                "first_name": first_name,
                "last_name": last_name,
            }
            state.confirmation_pending = True
            state.readback_completed = True
            state.transition_to(WorkflowStage.BOOKING_CONFIRMATION)
            return booking_readback_response(state.prepared_booking)
        state.transition_to(WorkflowStage.BOOKING_DETAILS)
        return clarify_name_response()

    @staticmethod
    def handle_name_provided(
        state: VoiceWorkflowState,
        full_name: str,
    ) -> str:
        state.caller_name = full_name.strip()
        parts = state.caller_name.split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""
        state.prepared_booking = {
            "doctor_name": state.preferred_doctor or "the doctor",
            "slot_date": state.target_date or "tomorrow",
            "slot_time": state.target_time or "the scheduled time",
            "first_name": first_name,
            "last_name": last_name,
        }
        state.confirmation_pending = True
        state.readback_completed = True
        state.transition_to(WorkflowStage.BOOKING_CONFIRMATION)
        return booking_readback_response(state.prepared_booking)

    @staticmethod
    async def handle_booking_confirmation(
        state: VoiceWorkflowState,
        db: AsyncSession,
        org_id: UUID,
        call_session_id: UUID | None = None,
    ) -> str:
        if not state.prepared_booking or not state.readback_completed:
            return "Could you please confirm the doctor, date, and time you would like to book?"
        result = await dispatch_clinic_tool(
            "confirm_appointment_booking",
            dict(state.prepared_booking),
            db,
            org_id,
            clean_phone=state.caller_phone,
            call_session_id=call_session_id,
        )
        if result.get("status") == "booked" or result.get("confirmed") or result.get("status") == "confirmed":
            state.booking_confirmed = True
            state.confirmation_pending = False
            state.transition_to(WorkflowStage.CLOSING)
            return booking_success_response(state.prepared_booking)
        error_msg = result.get("message") or "That time was just reserved. Would you like to check other times?"
        state.transition_to(WorkflowStage.AVAILABILITY)
        state.clear_selection()
        return error_msg

    @staticmethod
    async def handle_cancellation(
        state: VoiceWorkflowState,
        db: AsyncSession,
        org_id: UUID,
        call_session_id: UUID | None = None,
    ) -> str:
        result = await dispatch_clinic_tool(
            "cancel_appointment",
            {},
            db,
            org_id,
            clean_phone=state.caller_phone,
            call_session_id=call_session_id,
        )
        if result.get("status") == "cancelled" or result.get("cancelled"):
            state.transition_to(WorkflowStage.CLOSING)
            return cancellation_success_response()
        return result.get("message") or "Could not cancel the appointment. Please contact reception."

    @staticmethod
    def handle_emergency(phone: str = "112") -> str:
        return emergency_response(phone)

    @staticmethod
    def handle_transfer(available: bool = False) -> str:
        return transfer_response(available)

    @staticmethod
    def handle_farewell(state: VoiceWorkflowState) -> str:
        state.transition_to(WorkflowStage.CLOSING)
        state.call_completed = True
        return farewell_response()
