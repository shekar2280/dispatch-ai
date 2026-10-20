from typing import Any
import json
import logging
from datetime import UTC, datetime
from uuid import UUID
from livekit.agents import llm, RunContext, StopResponse
from livekit.agents.voice import Agent
from app.core.database import AsyncSessionLocal
from app.services.voice.tool_execution_service import execute_tool_call
from app.agent.prompt_builder import format_friendly_date
from app.agent.confirmation import ConfirmationGate
from app.core.config import settings

logger = logging.getLogger(__name__)


class ClinicVoiceAgent(Agent):
    def __init__(
        self,
        system_prompt: str,
        org_id: UUID | None = None,
        caller_phone: str | None = None,
        emergency_phone: str = "112",
        room: Any = None,
    ):
        super().__init__(instructions=system_prompt)
        self.org_id = org_id
        self.caller_phone = caller_phone or ""
        self.emergency_phone = emergency_phone or "112"
        self.room = room
        self.call_session_id: UUID | None = None
        self.confirmation = ConfirmationGate()
        self.state = {
            "caller_name": None,
            "patient_verified": False,
            "intent": "inquiry",
            "target_date": None,
            "preferred_doctor": None,
            "chief_complaint": None,
            "booking_confirmed": False,
            "token_number": None,
            "agent_paused": False,
        }

        self.outcome_tracker = {
            "intent": "ADMIN",
            "call_outcome": "inquiry",
            "caller_name": None,
            "chief_complaint": None,
        }

    def observe_caller_turn(self, event_id, text):
        self.confirmation.observe(event_id, text)

    async def on_user_turn_completed(self, turn_ctx, new_message):
        self.observe_caller_turn(new_message.id, new_message.text_content or "")

    async def llm_node(self, chat_ctx, tools, model_settings):
        if self.state.get("agent_paused") or self.state.get("service_unavailable"):
            return
        from app.services.voice.provider_budget import reserve_llm, settle_llm
        content = json.dumps(chat_ctx.to_dict(), default=str)
        tool_bytes = sum(len(str(getattr(t, "__annotations__", {})).encode()) + 1024 for t in tools)
        from fastapi import HTTPException
        try:
            reservation = await reserve_llm(len(content.encode()) + len(self.instructions.encode()) + tool_bytes)
        except HTTPException:
            self.state["service_unavailable"] = True
            yield "Our appointment service is temporarily busy. Please contact reception or try again shortly."
            return
        yielded_any = False
        actual_tokens = 0
        try:
            async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
                usage = getattr(chunk, "usage", None)
                if usage:
                    actual_tokens = max(actual_tokens, int(getattr(usage, "total_tokens", 0) or 0))
                yielded_any = True
                yield chunk
        except Exception:
            self.state["service_unavailable"] = True
            if not yielded_any:
                yield "Pardon me, I had a brief connection issue. Could you please repeat that?"
            else:
                yield " ... I apologize, my connection briefly dropped."
        finally:
            if actual_tokens:
                try:
                    await settle_llm(reservation, actual_tokens)
                except Exception:
                    # Keep the full reservation if reconciliation fails.
                    logger.exception("Could not reconcile voice token usage call=%s", self.call_session_id)

    async def tts_node(self, text, model_settings):
        from app.services.voice.provider_budget import reserve_budget
        await reserve_budget("deepgram-tts-characters", 1200,
                             daily_units=settings.VOICE_TTS_DAILY_CHARACTERS)
        async def bounded_text():
            remaining = 1200
            async for chunk in text:
                if remaining <= 0:
                    break
                spoken = chunk[:remaining]
                remaining -= len(spoken)
                yield spoken
        try:
            async for frame in Agent.default.tts_node(self, bounded_text(), model_settings):
                yield frame
        except Exception:
            self.state["service_unavailable"] = True


    @llm.function_tool()
    async def prepare_appointment_booking(self, first_name: str, last_name: str,
            slot_date: str, slot_time: str, doctor_name: str = "",
            chief_complaint: str = "", booking_mode: str = "appointment") -> str:
        """Prepare exact details to read back. Does not book. Await a new caller confirmation."""
        payload = {
            "first_name": first_name,
            "last_name": last_name,
            "slot_date": slot_date,
            "slot_time": slot_time,
            "doctor_name": doctor_name,
            "chief_complaint": chief_complaint,
            "booking_mode": booking_mode,
        }
        self.confirmation.propose(payload)
        from app.models.call_session import CallLog
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            call = await db.scalar(select(CallLog).where(CallLog.id == self.call_session_id,
                CallLog.org_id == self.org_id).with_for_update())
            if not call or call.org_id != self.org_id or call.end_time:
                return "This call has ended. No booking was made."
            if call.booking_result:
                return json.dumps(call.booking_result)
            call.booking_proposal = {"details": payload, "caller_event_id": self.confirmation.turn_id,
                                     "prepared_at": datetime.now(UTC).isoformat()}
            await db.commit()
        return json.dumps({"status": "awaiting_confirmation", "details": payload,
                           "instruction": "Read these details, ask if correct, then wait for the caller's next response."})

    @llm.function_tool()
    async def search_doctor_slots(
        self,
        specialty_or_complaint: str,
        target_date: str,
        target_time: str = "",
        preferred_doctor_name: str = "",
    ) -> str:
        async with AsyncSessionLocal() as db:
            self.state["target_date"] = target_date
            self.state["preferred_doctor"] = preferred_doctor_name or None
            self.state["chief_complaint"] = specialty_or_complaint or None

            res = await execute_tool_call(
                tool_name="search_doctor_slots",
                arguments={
                    "specialty_or_complaint": specialty_or_complaint,
                    "target_date": target_date,
                    "target_time": target_time,
                    "preferred_doctor_name": preferred_doctor_name,
                },
                db=db,
                org_id=self.org_id,
                clean_phone=self.caller_phone,
                call_session_id=self.call_session_id,
            )
            return str(res)

    @llm.function_tool()
    async def confirm_appointment_booking(
        self,
        first_name: str,
        last_name: str,
        slot_date: str,
        slot_time: str,
        doctor_name: str = "",
        chief_complaint: str = "",
        booking_mode: str = "appointment",
    ) -> str:
        payload = {
            "first_name": first_name,
            "last_name": last_name,
            "slot_date": slot_date,
            "slot_time": slot_time,
            "doctor_name": doctor_name,
            "chief_complaint": chief_complaint,
            "booking_mode": booking_mode,
        }
        if not self.confirmation.permits(payload):
            return "No booking made. Prepare the exact details, read them back, and wait for a clear yes from the caller."
        from app.services.voice.call_logger_service import flush_pending_turns
        await flush_pending_turns(session_id=self.call_session_id)
        async with AsyncSessionLocal() as db:
            from app.models.call_session import CallLog
            from sqlalchemy import select
            call = await db.scalar(select(CallLog).where(CallLog.id == self.call_session_id,
                CallLog.org_id == self.org_id).with_for_update())
            if call and (call.booking_proposal or {}).get("details") == payload:
                # Bind the completed readback observed by the server; model arguments cannot supply this ID.
                call.booking_proposal = {**call.booking_proposal,
                                         "readback_event_id": self.confirmation.readback_turn}
            res = await execute_tool_call(
                tool_name="confirm_appointment_booking",
                arguments={
                    "first_name": first_name,
                    "last_name": last_name,
                    "slot_date": slot_date,
                    "slot_time": slot_time,
                    "booking_mode": booking_mode,
                    "doctor_name": doctor_name,
                    "chief_complaint": chief_complaint,
                },
                db=db,
                org_id=self.org_id,
                clean_phone=self.caller_phone,
                call_session_id=self.call_session_id,
            )

            if isinstance(res, dict) and (
                res.get("status") in ("success", "confirmed")
            ):
                confirmed_name = res.get("patient_name") or f"{first_name} {last_name}".strip()
                self.outcome_tracker["call_outcome"] = "appointment_booked"
                self.outcome_tracker["caller_name"] = (
                    confirmed_name
                )
                self.outcome_tracker["chief_complaint"] = (
                    f"Booked OPD: {chief_complaint} with {doctor_name or 'Doctor'}".strip()
                )
                self.state["booking_confirmed"] = True
                self.state["caller_name"] = confirmed_name
                self.state["target_date"] = slot_date
                self.state["token_number"] = res.get("token_number")
                self.state["intent"] = "appointment_booked"

                spoken_d = res.get("spoken_date") or format_friendly_date(slot_date)
                date_phrase = f"for {spoken_d}"
                token_num = res.get("token_number")
                estimated_turn = res.get("estimated_turn_time")
                token_phrase = (
                    f" Your token number is {res.get('display_token') or token_num}."
                    f" Current estimated availability is around {estimated_turn}; it may change."
                    if res.get("booking_mode") == "queue" and estimated_turn
                    else f" Your token number is {token_num}." if token_num else ""
                )
                if res.get("booking_mode") == "queue":
                    return (
                        f"You are registered for a visit today for {confirmed_name}."
                        f"{token_phrase} Please check in at reception on arrival. Queue order starts at physical check-in."
                    )
                return (
                    f"Your arrival window for {confirmed_name} is confirmed {date_phrase} at {slot_time} with {doctor_name or 'the doctor'}.{token_phrase} "
                    f"Consultation order follows physical check-in; waiting time may change. Is there anything else I can help you with today?"
                )
            return str(res)

    @llm.function_tool()
    async def verify_patient_identity(
        self,
        first_name: str,
        last_name: str,
        date_of_birth: str = "",
    ) -> str:
        async with AsyncSessionLocal() as db:
            res = await execute_tool_call(
                tool_name="verify_patient_identity",
                arguments={
                    "first_name": first_name,
                    "last_name": last_name,
                    "date_of_birth": date_of_birth,
                },
                db=db,
                org_id=self.org_id,
                clean_phone=self.caller_phone,
                call_session_id=self.call_session_id,
            )
            if isinstance(res, dict) and res.get("verified"):
                self.state["patient_verified"] = True
                self.state["caller_name"] = res.get("patient_name")
            return json.dumps(res)

    @llm.function_tool()
    async def reschedule_appointment(
        self,
        appointment_id: str,
        new_date: str,
        new_time: str,
    ) -> str:
        async with AsyncSessionLocal() as db:
            res = await execute_tool_call(
                tool_name="reschedule_appointment",
                arguments={
                    "appointment_id": appointment_id,
                    "new_date": new_date,
                    "new_time": new_time,
                },
                db=db,
                org_id=self.org_id,
                clean_phone=self.caller_phone,
                call_session_id=self.call_session_id,
            )
            if isinstance(res, dict) and res.get("status") == "success":
                self.outcome_tracker["call_outcome"] = "appointment_rescheduled"
                self.state["target_date"] = new_date
            return json.dumps(res)

    @llm.function_tool()
    async def lookup_clinic_faq(
        self,
        query: str,
    ) -> str:
        async with AsyncSessionLocal() as db:
            res = await execute_tool_call(
                tool_name="lookup_clinic_faq",
                arguments={"query": query},
                db=db,
                org_id=self.org_id,
                clean_phone=self.caller_phone,
                call_session_id=self.call_session_id,
            )
            return str(res)

    @llm.function_tool()
    async def check_doctor_live_status(
        self,
        doctor_name_or_specialty: str,
    ) -> str:
        async with AsyncSessionLocal() as db:
            res = await execute_tool_call(
                tool_name="check_doctor_live_status",
                arguments={"doctor_name_or_specialty": doctor_name_or_specialty},
                db=db,
                org_id=self.org_id,
                clean_phone=self.caller_phone,
                call_session_id=self.call_session_id,
            )
            return str(res)

    @llm.function_tool()
    async def end_call(
        self,
        context: RunContext,
        farewell_message: str = "",
    ) -> str:
        """Say a short goodbye once, finish audio playback, then end the call."""
        await context.wait_for_playout()
        farewell = farewell_message.strip()[:240] or "Thank you for calling. Take care. Goodbye!"
        await context.session.say(farewell, allow_interruptions=False).wait_for_playout()
        if self.outcome_tracker.get("call_outcome") != "appointment_booked":
            self.outcome_tracker["call_outcome"] = "completed"
        self.state["call_completed"] = True
        context.session.shutdown(drain=True)
        # No second model-generated farewell after the tool finishes.
        raise StopResponse()

    @llm.function_tool()
    async def deflect_emergency(
        self,
        emergency_details: str,
    ) -> str:
        self.outcome_tracker["call_outcome"] = "emergency_deflected"
        self.outcome_tracker["chief_complaint"] = emergency_details
        self.state["call_completed"] = True
        from app.services.infra.websocket_manager import ws_manager
        if self.org_id:
            await ws_manager.broadcast_to_org(str(self.org_id), {
                "event": "EMERGENCY_SOS_ALERT",
                "call_id": str(self.call_session_id) if self.call_session_id else None,
                "org_id": str(self.org_id),
                "caller_phone": self.caller_phone,
                "chief_complaint": emergency_details,
                "emergency_phone": self.emergency_phone,
                "triage_status": "emergency",
            })
        action = f"call {self.emergency_phone}" if self.emergency_phone else "contact local emergency services"
        return (
            f"Emergency noted. Immediately and firmly instruct the caller: "
            f"'This sounds like an urgent medical situation. Please hang up immediately and {action} or go to the nearest emergency room.' "
            f"Do not offer an appointment or put them on hold. Conclude the call."
        )

    @llm.function_tool()
    async def transfer_to_reception(
        self,
        reason: str = "",
    ) -> str:
        staff_present = False
        if self.room and hasattr(self.room, "remote_participants"):
            for p in self.room.remote_participants.values():
                identity = getattr(p, "identity", "") or ""
                metadata = getattr(p, "metadata", "") or ""
                if identity.startswith("staff_") or '"role":"staff"' in metadata or '"role": "staff"' in metadata:
                    staff_present = True
                    break
        if staff_present:
            self.outcome_tracker["call_outcome"] = "transferred_to_staff"
            self.state["agent_paused"] = True
            if self.room and hasattr(self.room, "local_participant") and self.room.local_participant:
                payload = json.dumps({
                    "type": "staff_transfer_requested",
                    "call_id": str(self.call_session_id) if self.call_session_id else None,
                    "reason": reason,
                }).encode("utf-8")
                try:
                    await self.room.local_participant.publish_data(payload, reliable=True)
                except Exception:
                    pass
            return (
                "Staff member is connected in the clinic room. State: 'Connecting you with our reception desk right now, please hold for just a moment.' "
                "Then pause and allow staff to speak."
            )
        self.outcome_tracker["call_outcome"] = "staff_transfer_unavailable"
        return (
            "No receptionist is currently connected; unavailable for a live transfer. "
            "Say: 'I can't connect you to reception right now. Please contact the clinic directly to change or cancel your appointment.' "
            "You can still check public opening times or availability. Do not promise a callback, "
            "claim a message was saved, or say the appointment was changed or cancelled."
        )

