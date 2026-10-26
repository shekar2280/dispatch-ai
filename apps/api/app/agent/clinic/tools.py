import asyncio
from functools import wraps
import json
import logging
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from livekit.agents import RunContext, StopResponse, llm
from livekit.agents.voice import Agent

from app.agent.confirmation import ConfirmationGate
from app.agent.prompt_builder import format_friendly_date
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.services.voice.tool_execution_service import execute_tool_call
from app.services.voice.workflow.state import VoiceWorkflowState, WorkflowStage

logger = logging.getLogger(__name__)


def _with_delayed_voice_filler(scenario_key: str):
    """Speak a short progress cue only when a voice tool is taking noticeable time."""
    def decorate(tool_func):
        @wraps(tool_func)
        async def wrapped(agent, *args, **kwargs):
            operation = asyncio.create_task(tool_func(agent, *args, **kwargs))
            finished = asyncio.Event()

            async def speak_if_still_waiting():
                await asyncio.sleep(0.7)
                if finished.is_set():
                    return None
                try:
                    from app.agent.agent_prompts import get_scenario_filler
                    return agent.session.say(
                        get_scenario_filler(scenario_key),
                        allow_interruptions=True,
                        add_to_chat_ctx=False,
                    )
                except Exception:
                    logger.debug("Could not play voice progress cue for %s", scenario_key, exc_info=True)
                    return None

            filler = asyncio.create_task(speak_if_still_waiting())
            try:
                result = await operation
            except BaseException:
                finished.set()
                filler.cancel()
                await asyncio.gather(filler, return_exceptions=True)
                raise

            finished.set()
            if not filler.done():
                filler.cancel()
            handle_result = await asyncio.gather(filler, return_exceptions=True)
            handle = handle_result[0] if handle_result and not isinstance(handle_result[0], BaseException) else None
            if handle is not None and not handle.done():
                # Keep the result from speaking over the short progress cue.
                with suppress(Exception):
                    await handle.wait_for_playout()
            return result
        return wrapped
    return decorate


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
        self.workflow = VoiceWorkflowState(caller_phone=self.caller_phone)

        self.outcome_tracker = {
            "intent": "ADMIN",
            "call_outcome": "inquiry",
            "caller_name": None,
            "chief_complaint": None,
        }
        self.telemetry = None
        self.recovery_context = None
        self.provider = settings.PRIMARY_LLM_PROVIDER
        self.model = settings.GROQ_MODEL if settings.PRIMARY_LLM_PROVIDER == "groq" and settings.GROQ_API_KEY else settings.GEMINI_MODEL

    @property
    def workflow_stage(self) -> str:
        return self.workflow.stage.value

    @workflow_stage.setter
    def workflow_stage(self, stage_val: WorkflowStage | str):
        self.workflow.transition_to(stage_val)

    @property
    def state(self) -> VoiceWorkflowState:
        return self.workflow

    def observe_caller_turn(self, event_id, text):
        if event_id != self.confirmation.turn_id:
            self.workflow.pending_slot_search_response = False
            self.workflow.pending_booking_readback = False
        self.confirmation.observe(event_id, text)

    async def on_user_turn_completed(self, turn_ctx, new_message):
        self.observe_caller_turn(new_message.id, new_message.text_content or "")

    async def llm_node(self, chat_ctx, tools, model_settings):
        if self.workflow.agent_paused or self.workflow.service_unavailable:
            return
        from app.services.voice.workflow.responses import (
            booking_readback_response,
            clarify_name_response,
            farewell_response,
            slot_search_response,
        )
        from app.services.voice.workflow.router import (
            match_cancellation,
            match_emergency,
            match_faq,
            match_farewell,
            match_offered_slot,
            match_transfer,
            match_yes_no,
        )
        response_only = getattr(model_settings, "tool_choice", None) == "none"
        latest_text = self._latest_user_text(chat_ctx)
        if not latest_text or response_only:
            if self.workflow.pending_slot_search_response:
                self.workflow.pending_slot_search_response = False
                yield slot_search_response(self.workflow.last_slot_search or {})
                return
            if self.workflow.pending_booking_readback:
                self.workflow.pending_booking_readback = False
                yield booking_readback_response(self.confirmation.proposal or {})
                return
        if latest_text:
            if self.workflow.stage == WorkflowStage.RECOVERY and self.recovery_context:
                from app.services.voice.workflow.recovery import (
                    apply_recovery_preferences,
                    decline_recovery_offer,
                )
                yn = match_yes_no(latest_text)
                norm_text = latest_text.lower()
                is_affirmative = yn is True or any(w in norm_text for w in ("continue", "pick up", "resume", "yes", "sure", "yeah", "yep", "okay", "ok"))
                is_negative = yn is False or any(w in norm_text for w in ("start fresh", "start over", "no", "nope", "different"))
                if is_affirmative and not is_negative:
                    apply_recovery_preferences(self.workflow, self.recovery_context)
                    if self.recovery_context.has_committed_appointment:
                        time_str = self.recovery_context.appointment_time or "your scheduled time"
                        doc_str = f" with Dr. {self.recovery_context.doctor_name}" if self.recovery_context.doctor_name else ""
                        yield f"Your appointment is already confirmed for {time_str}{doc_str}. Is there anything else I can assist you with today?"
                        return
                    else:
                        doc_str = f"Dr. {self.workflow.preferred_doctor}" if self.workflow.preferred_doctor else "the doctor"
                        date_str = format_friendly_date(self.workflow.target_date) if self.workflow.target_date else "your requested date"
                        yield f"Great, let's continue. You were looking for an appointment with {doc_str} on {date_str}. Let me re-verify the available slots."
                        return
                elif is_negative:
                    decline_recovery_offer(self.workflow)
                    yield "Understood, let's start fresh. How can I assist you today?"
                    return
                else:
                    decline_recovery_offer(self.workflow)

            if match_emergency(latest_text):
                result = await self.deflect_emergency(emergency_details=latest_text)
                yield result
                return
            if match_farewell(latest_text):
                self.workflow.call_completed = True
                yield farewell_response()
                return
            if match_transfer(latest_text):
                result = await self.transfer_to_reception()
                yield result
                return

            faq_key = match_faq(latest_text)
            if faq_key and self.workflow.stage in (WorkflowStage.INTAKE, WorkflowStage.AVAILABILITY):
                result = await self.lookup_clinic_faq(query=faq_key)
                yield result
                return

            if match_cancellation(latest_text):
                self.workflow.transition_to(WorkflowStage.IDENTITY_LOOKUP)
                yield "To cancel your appointment, could you please tell me your first and last name?"
                return

            if self.workflow.stage == WorkflowStage.CANCEL_CONFIRMATION and self.workflow.pending_cancellation_appointment_id:
                appt_id = self.workflow.pending_cancellation_appointment_id
                yn = match_yes_no(latest_text)
                if yn is True:
                    await self.cancel_appointment(appointment_id=appt_id)
                    self.workflow.transition_to(WorkflowStage.CLOSING)
                    yield "Your appointment has been cancelled. Is there anything else I can help you with?"
                    return
                elif yn is False:
                    self.workflow.transition_to(WorkflowStage.INTAKE)
                    self.workflow.pending_cancellation_appointment_id = None
                    yield "Understood, your appointment remains scheduled. How else may I assist you?"
                    return

            if self.workflow.stage == WorkflowStage.IDENTITY_LOOKUP:
                cleaned_name = latest_text.strip()
                parts = cleaned_name.split(" ", 1)
                first_name = parts[0]
                last_name = parts[1] if len(parts) > 1 else ""
                res_str = await self.verify_patient_identity(first_name=first_name, last_name=last_name)
                try:
                    res_json = json.loads(res_str) if isinstance(res_str, str) else res_str
                except Exception:
                    res_json = {}
                if isinstance(res_json, dict) and res_json.get("verified"):
                    appts = res_json.get("active_appointments") or []
                    if appts:
                        target = appts[0]
                        self.workflow.pending_cancellation_appointment_id = target.get("appointment_id")
                        self.workflow.transition_to(WorkflowStage.CANCEL_CONFIRMATION)
                        yield f"I found your appointment on {target.get('appointment_date')} at {target.get('appointment_time')} with {target.get('doctor_name')}. Are you sure you want to cancel it?"
                        return
                    else:
                        self.workflow.transition_to(WorkflowStage.INTAKE)
                        yield f"I verified your record for {cleaned_name}, but you have no upcoming appointments to cancel. How else may I help?"
                        return
                else:
                    self.workflow.transition_to(WorkflowStage.INTAKE)
                    yield f"I could not locate an appointment under {cleaned_name}. Would you like to speak with reception?"
                    return

            if self.workflow.stage == WorkflowStage.BOOKING_CONFIRMATION and self.confirmation.proposal:
                if self.confirmation.permits(self.confirmation.proposal):
                    self.workflow.pending_booking_readback = False
                    result = await self.confirm_appointment_booking(**self.confirmation.proposal)
                    yield result
                    return
                if match_yes_no(latest_text) is False:
                    self.workflow.transition_to(WorkflowStage.SLOT_SELECTION)
                    self.confirmation.proposal = None
                    self.workflow.pending_booking_readback = False
                    yield "No problem, I will not book that. Would you like to check a different day or time?"
                    return

            offers = (self.workflow.last_slot_search or {}).get("offers", [])
            if offers and self.workflow.stage in (WorkflowStage.SLOT_SELECTION, WorkflowStage.INTAKE, WorkflowStage.IDENTITY_VERIFIED):
                matched_slot = match_offered_slot(latest_text, offers)
                # A plain affirmative selects the sole offered slot; the exact
                # booking readback below remains the separate consent step.
                if matched_slot is None and len(offers) == 1 and match_yes_no(latest_text) is True:
                    matched_slot = offers[0]
                if matched_slot:
                    self.workflow.pending_slot_search_response = False
                    slot_label = str(matched_slot.get("label") or matched_slot.get("time") or "")
                    last_search = self.workflow.last_slot_search or {}
                    slot_date = str(last_search.get("date") or self.workflow.target_date or "tomorrow")
                    doc_name = str(last_search.get("doctor") or self.workflow.preferred_doctor or "the doctor")
                    caller_name = self.workflow.caller_name or self.outcome_tracker.get("caller_name")
                    if caller_name:
                        parts = caller_name.split(" ", 1)
                        first_name = parts[0]
                        last_name = parts[1] if len(parts) > 1 else ""
                        await self.prepare_appointment_booking(
                            first_name=first_name,
                            last_name=last_name,
                            slot_date=slot_date,
                            slot_time=slot_label,
                            doctor_name=doc_name,
                        )
                        self.workflow.pending_booking_readback = False
                        yield booking_readback_response(self.confirmation.proposal or {})
                        return
                    else:
                        self.workflow.selected_slot_time = slot_label
                        self.workflow.transition_to(WorkflowStage.BOOKING_DETAILS)
                        yield clarify_name_response()
                        return

            if self.workflow.stage == WorkflowStage.BOOKING_DETAILS:
                cleaned_name = latest_text.strip()
                if match_yes_no(cleaned_name) is not False and len(cleaned_name.split()) >= 1:
                    parts = cleaned_name.split(" ", 1)
                    first_name = parts[0]
                    last_name = parts[1] if len(parts) > 1 else ""
                    self.workflow.caller_name = cleaned_name
                    self.outcome_tracker["caller_name"] = cleaned_name
                    last_search = self.workflow.last_slot_search or {}
                    slot_time = self.workflow.selected_slot_time or "2 PM"
                    slot_date = str(last_search.get("date") or self.workflow.target_date or "tomorrow")
                    doc_name = str(last_search.get("doctor") or self.workflow.preferred_doctor or "the doctor")
                    await self.prepare_appointment_booking(
                        first_name=first_name,
                        last_name=last_name,
                        slot_date=slot_date,
                        slot_time=slot_time,
                        doctor_name=doc_name,
                    )
                    self.workflow.pending_booking_readback = False
                    yield booking_readback_response(self.confirmation.proposal or {})
                    return

        from app.services.voice.provider_budget import reserve_llm, settle_llm
        effective_tools = [] if response_only else self._tools_for_stage(tools or [])
        bounded_ctx = chat_ctx
        if isinstance(chat_ctx, llm.ChatContext):
            bounded_ctx = chat_ctx.copy().truncate(max_items=settings.VOICE_LLM_MAX_HISTORY_TURNS * 2 + 4)
        content = json.dumps(bounded_ctx.to_dict(), default=str)
        try:
            from livekit.agents.llm.tool_context import ToolContext
            serialized_tools = json.dumps(
                ToolContext(effective_tools).parse_function_tools("openai"),
                separators=(",", ":"),
            ) if effective_tools else ""
        except Exception:
            serialized_tools = "".join(str(getattr(t, "__annotations__", {})) for t in effective_tools)
        tool_chars = len(serialized_tools)
        messages = bounded_ctx.messages() if callable(getattr(bounded_ctx, "messages", None)) else getattr(bounded_ctx, "messages", [])
        if not messages and hasattr(bounded_ctx, "to_dict"):
            dict_rep = bounded_ctx.to_dict()
            messages = dict_rep.get("items", []) or dict_rep.get("messages", [])
        history_count = len(messages) if isinstance(messages, list) else 0
        instruction_chars = len(self.instructions)
        history_chars = len(content)
        tool_names = [getattr(getattr(t, "info", None), "name", getattr(t, "__name__", str(t))) for t in effective_tools]
        tool_result_chars = 0
        for m in messages:
            role = getattr(m, "role", "") if not isinstance(m, dict) else m.get("role", "")
            if role in ("tool", "tool_call", "function"):
                tool_result_chars += len(str(getattr(m, "content", "") if not isinstance(m, dict) else m.get("content", "")))
        if getattr(self, "telemetry", None):
            self.telemetry.stage_request_shape(
                workflow_stage=self.workflow.stage.value,
                provider=getattr(self, "provider", settings.PRIMARY_LLM_PROVIDER),
                model=getattr(self, "model", settings.GEMINI_MODEL),
                tool_names=tool_names,
                tool_count=len(tool_names),
                history_item_count=history_count,
                instruction_characters=instruction_chars,
                serialized_history_characters=history_chars,
                serialized_tool_schema_characters=tool_chars,
                tool_result_characters=tool_result_chars,
            )
        from app.services.voice.provider_router import provider_router
        active_route = provider_router.select_route()
        if active_route and not active_route.degraded:
            self.provider = active_route.provider
            self.model = active_route.model
        from fastapi import HTTPException
        reservation = None
        try:
            output_cap = (
                settings.VOICE_GROQ_MAX_COMPLETION_TOKENS
                if self.provider == "groq"
                else settings.VOICE_LLM_MAX_OUTPUT_TOKENS
            )
            reservation = await reserve_llm(
                len(content) + len(self.instructions) + tool_chars,
                provider=self.provider,
                model=self.model,
                max_completion_tokens=output_cap,
            )
        except HTTPException:
            fallback_route = provider_router.select_route()
            if fallback_route and fallback_route.provider != self.provider and not fallback_route.degraded:
                self.provider = fallback_route.provider
                self.model = fallback_route.model
                output_cap = (
                    settings.VOICE_GROQ_MAX_COMPLETION_TOKENS
                    if self.provider == "groq"
                    else settings.VOICE_LLM_MAX_OUTPUT_TOKENS
                )
                try:
                    reservation = await reserve_llm(
                        len(content) + len(self.instructions) + tool_chars,
                        provider=self.provider,
                        model=self.model,
                        max_completion_tokens=output_cap,
                    )
                except HTTPException:
                    self.workflow.service_unavailable = True
                    yield "Our appointment service is temporarily busy. Please contact reception or try again shortly."
                    return
            else:
                self.workflow.service_unavailable = True
                yield "Our appointment service is temporarily busy. Please contact reception or try again shortly."
                return
        yielded_any = False
        actual_tokens = 0
        completion_chars = 0
        try:
            async for chunk in Agent.default.llm_node(self, bounded_ctx, effective_tools, model_settings):
                usage = getattr(chunk, "usage", None)
                if usage:
                    actual_tokens = max(actual_tokens, int(getattr(usage, "total_tokens", 0) or 0))
                delta = getattr(chunk, "content", "") or ""
                if isinstance(delta, str):
                    completion_chars += len(delta)
                yielded_any = True
                yield chunk
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            from app.services.voice.circuit_breaker import circuit_breaker
            from app.services.voice.diagnostics import classify_provider_error, unwrap_root_cause
            if isinstance(unwrap_root_cause(exc), asyncio.CancelledError):
                raise
            diag = classify_provider_error(exc)
            circuit_breaker.record_failure(self.provider, status_code=diag.status_code, retry_after=diag.retry_after)
            fallback_route = provider_router.select_route()
            if fallback_route and fallback_route.provider != self.provider and not fallback_route.degraded:
                self.provider = fallback_route.provider
                self.model = fallback_route.model
            self.workflow.service_unavailable = True
            if not yielded_any:
                yield "Pardon me, I had a brief connection issue. Could you please repeat that?"
            else:
                yield " ... I apologize, my connection briefly dropped."
        finally:
            if not actual_tokens and completion_chars > 0:
                import math
                actual_tokens = max(1, math.ceil((len(content) + len(self.instructions) + tool_chars + completion_chars) / 4))
            if actual_tokens and reservation:
                try:
                    await settle_llm(reservation, actual_tokens)
                except Exception:
                    logger.exception("Could not reconcile voice token usage call=%s", self.call_session_id)

    def _tools_for_stage(self, tools):
        allowed = {
            WorkflowStage.INTAKE: {"search_doctor_slots", "lookup_clinic_faq", "check_doctor_live_status", "verify_patient_identity", "transfer_to_reception", "deflect_emergency", "end_call"},
            WorkflowStage.AVAILABILITY: {"search_doctor_slots", "lookup_clinic_faq", "check_doctor_live_status", "verify_patient_identity", "transfer_to_reception", "deflect_emergency", "end_call"},
            WorkflowStage.SLOT_SELECTION: {"search_doctor_slots", "prepare_appointment_booking", "transfer_to_reception", "deflect_emergency", "end_call"},
            WorkflowStage.BOOKING_DETAILS: {"search_doctor_slots", "prepare_appointment_booking", "transfer_to_reception", "deflect_emergency", "end_call"},
            WorkflowStage.BOOKING_CONFIRMATION: {"search_doctor_slots", "confirm_appointment_booking", "prepare_appointment_booking", "transfer_to_reception", "deflect_emergency", "end_call"},
            WorkflowStage.IDENTITY_LOOKUP: {"verify_patient_identity", "transfer_to_reception", "deflect_emergency", "end_call"},
            WorkflowStage.IDENTITY_VERIFIED: {"search_doctor_slots", "reschedule_appointment", "cancel_appointment", "transfer_to_reception", "deflect_emergency", "end_call"},
        }.get(self.workflow.stage, {"transfer_to_reception", "deflect_emergency", "end_call"})
        return [tool for tool in tools if getattr(getattr(tool, "info", None), "name", getattr(tool, "__name__", "")) in allowed]
        return [tool for tool in tools if getattr(getattr(tool, "info", None), "name", getattr(tool, "__name__", "")) in allowed]

    @staticmethod
    def _latest_user_text(chat_ctx):
        items = list(getattr(chat_ctx, "items", []) or [])
        for item in reversed(items):
            if getattr(item, "role", None) != "user":
                continue
            text = getattr(item, "text_content", "")
            text = text() if callable(text) else text
            if isinstance(text, str) and text.strip():
                return text.strip()
        return ""

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
            logger.warning("TTS node partial failure for call=%s", self.call_session_id)


    @llm.function_tool()
    async def prepare_appointment_booking(self, first_name: str, last_name: str,
            slot_date: str, slot_time: str, doctor_name: str = "",
            chief_complaint: str = "", booking_mode: str = "appointment") -> str:
        payload = {
            "first_name": first_name,
            "last_name": last_name,
            "slot_date": slot_date,
            "slot_time": slot_time,
            "doctor_name": doctor_name,
            "chief_complaint": chief_complaint,
            "booking_mode": booking_mode,
        }
        if self.call_session_id and self.org_id:
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
        self.confirmation.propose(payload)
        self.workflow.transition_to(WorkflowStage.BOOKING_CONFIRMATION)
        self.workflow.pending_booking_readback = True
        return json.dumps({"status": "awaiting_confirmation", "details": payload,
                           "instruction": "Read these details, ask if correct, then wait for the caller's next response."})

    @llm.function_tool()
    @_with_delayed_voice_filler("search_doctor_slots")
    async def search_doctor_slots(
        self,
        specialty_or_complaint: str,
        target_date: str,
        target_time: str = "",
        preferred_doctor_name: str = "",
    ) -> str:
        async with AsyncSessionLocal() as db:
            self.workflow.target_date = target_date
            self.workflow.preferred_doctor = preferred_doctor_name or None
            self.workflow.chief_complaint = specialty_or_complaint or None

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
            target_st = WorkflowStage.IDENTITY_VERIFIED if self.workflow.patient_verified else WorkflowStage.SLOT_SELECTION
            self.workflow.transition_to(target_st)
            if isinstance(res, dict):
                self.workflow.last_slot_search = res
                self.workflow.pending_slot_search_response = True
                if self.call_session_id and self.org_id:
                    from app.services.voice.workflow.checkpoint_store import save_checkpoint
                    with suppress(Exception):
                        await save_checkpoint(db=db, org_id=self.org_id, call_id=self.call_session_id, state=self.workflow, status="active")
                return json.dumps(res)
            return str(res)

    @llm.function_tool()
    @_with_delayed_voice_filler("confirm_appointment_booking")
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
            return "No booking made. Prepare the exact details, complete the readback, and wait for the caller's response before deciding whether they agreed."
        from app.services.voice.call_logger_service import flush_pending_turns
        await flush_pending_turns(session_id=self.call_session_id)
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select

            from app.models.call_session import CallLog
            call = await db.scalar(select(CallLog).where(CallLog.id == self.call_session_id,
                CallLog.org_id == self.org_id).with_for_update())
            if call and (call.booking_proposal or {}).get("details") == payload:
                # Bind the completed readback observed by the server; model arguments cannot supply this ID.
                call.booking_proposal = {**call.booking_proposal,
                                         "readback_event_id": self.confirmation.readback_turn}
            res = await execute_tool_call(
                tool_name="confirm_appointment_booking",
                arguments={
                    "operation_key": f"voice-booking:{self.call_session_id}:{self.caller_phone}:{slot_date}:{slot_time}",
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
                self.workflow.booking_confirmed = True
                self.workflow.committed_but_not_acknowledged = True
                self.workflow.transition_to(WorkflowStage.INTAKE)
                self.workflow.caller_name = confirmed_name
                self.workflow.target_date = slot_date
                self.workflow.token_number = res.get("token_number")
                self.workflow.intent = "appointment_booked"
                if self.call_session_id and self.org_id:
                    from app.services.voice.workflow.checkpoint_store import save_checkpoint
                    with suppress(Exception):
                        await save_checkpoint(db=db, org_id=self.org_id, call_id=self.call_session_id, state=self.workflow, status="completed")

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
                        f"You're registered for a visit today.{token_phrase} Please check in at reception on arrival; queue order is based on check-in."
                    )
                return (
                    f"You're booked for {date_phrase} at {slot_time} with {doctor_name or 'the doctor'}.{token_phrase} "
                    f"Please check in on arrival; consultation order is based on check-in. Is there anything else I can help with?"
                )
            return str(res)

    @llm.function_tool()
    @_with_delayed_voice_filler("verify_patient_identity")
    async def verify_patient_identity(
        self,
        first_name: str,
        last_name: str,
    ) -> str:
        async with AsyncSessionLocal() as db:
            res = await execute_tool_call(
                tool_name="verify_patient_identity",
                arguments={
                    "first_name": first_name,
                    "last_name": last_name,
                },
                db=db,
                org_id=self.org_id,
                clean_phone=self.caller_phone,
                call_session_id=self.call_session_id,
            )
            if isinstance(res, dict) and res.get("verified"):
                self.workflow.patient_verified = True
                self.workflow.caller_name = res.get("patient_name")
                self.workflow.active_appointments = res.get("active_appointments", [])
                self.workflow.transition_to(WorkflowStage.IDENTITY_VERIFIED)
            return json.dumps(res)

    @llm.function_tool()
    @_with_delayed_voice_filler("reschedule_appointment")
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
                    "operation_key": f"voice-reschedule:{self.call_session_id}:{appointment_id}:{new_date}:{new_time}",
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
                self.workflow.target_date = new_date
                if self.call_session_id and self.org_id:
                    from app.services.voice.workflow.checkpoint_store import save_checkpoint
                    with suppress(Exception):
                        await save_checkpoint(db=db, org_id=self.org_id, call_id=self.call_session_id, state=self.workflow, status="active")
            return json.dumps(res)

    @llm.function_tool()
    @_with_delayed_voice_filler("cancel_appointment")
    async def cancel_appointment(
        self,
        appointment_id: str,
        cancellation_reason: str = "Patient request via voice",
    ) -> str:
        async with AsyncSessionLocal() as db:
            res = await execute_tool_call(
                tool_name="cancel_appointment",
                arguments={
                    "operation_key": f"voice-cancel:{self.call_session_id}:{appointment_id}",
                    "appointment_id": appointment_id,
                    "cancellation_reason": cancellation_reason,
                },
                db=db,
                org_id=self.org_id,
                clean_phone=self.caller_phone,
                call_session_id=self.call_session_id,
            )
            if isinstance(res, dict) and res.get("status") in ("cancelled", "success"):
                self.outcome_tracker["call_outcome"] = "appointment_cancelled"
                if self.call_session_id and self.org_id:
                    from app.services.voice.workflow.checkpoint_store import save_checkpoint
                    with suppress(Exception):
                        await save_checkpoint(db=db, org_id=self.org_id, call_id=self.call_session_id, state=self.workflow, status="completed")
            return json.dumps(res)

    @llm.function_tool()
    @_with_delayed_voice_filler("lookup_clinic_faq")
    async def lookup_clinic_faq(
        self,
        query: str,
    ) -> str:
        try:
            async with AsyncSessionLocal() as db:
                res = await execute_tool_call(
                    tool_name="lookup_clinic_faq",
                    arguments={"query": query},
                    db=db,
                    org_id=self.org_id,
                    clean_phone=self.caller_phone,
                    call_session_id=self.call_session_id,
                )
                if isinstance(res, dict) and "answer" in res:
                    return str(res["answer"])
                return str(res)
        except Exception:
            return "Please contact reception during office hours for details."

    @llm.function_tool()
    @_with_delayed_voice_filler("check_doctor_live_status")
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
        self.workflow.call_completed = True
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
        self.workflow.call_completed = True
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
            self.workflow.agent_paused = True
            if self.room and hasattr(self.room, "local_participant") and self.room.local_participant:
                payload = json.dumps({
                    "type": "staff_transfer_requested",
                    "call_id": str(self.call_session_id) if self.call_session_id else None,
                    "reason": reason,
                }).encode("utf-8")
                with suppress(Exception):
                    await self.room.local_participant.publish_data(payload, reliable=True)
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

