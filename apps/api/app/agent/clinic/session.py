"""Caller-bound, budgeted clinic voice session."""
import asyncio
import json
import logging
from datetime import UTC, datetime
from contextlib import suppress
from livekit.agents import JobContext, APIConnectOptions, room_io
from livekit.agents.voice import AgentSession
from livekit.agents.voice.agent_session import SessionConnectOptions
from livekit.plugins import deepgram, google, silero
from sqlalchemy import select
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.clinic_config import require_clinic_timezone
from app.agent.prompt_builder import build_clinic_prompt
from app.agent.clinic.tools import ClinicVoiceAgent
from app.models.call_session import CallLog
from app.services.audio.call_recording import CallRecorder
from app.services.audio.tts_service import resolve_voice
from app.services.voice.call_logger_service import queue_voice_turn, flush_pending_turns
from app.services.voice.telemetry import VoiceTelemetry
from app.services.voice.lifecycle import activate_call, terminate_call
from app.services.voice.diagnostics import classify_provider_error
from app.agent.session_control import until_stopped
from app.services.voice.country_emergency import resolve_emergency_phone

logger = logging.getLogger(__name__)


async def run_clinic_session(ctx: JobContext, org, caller_phone: str, caller_name=None,
                             stt_provider="deepgram", call_session_id=None, participant_identity=None,
                             browser_audio_processed=False):
    if not call_session_id or not participant_identity:
        raise ValueError("An admitted call and bound caller are required")
    greeting = (org.ai_greeting_prompt or org.custom_greeting or
                f"Hello! Thank you for calling {org.name}. How can I assist you today?").strip()[:400]
    greeting = greeting.replace("{{clinic_name}}", org.name).replace("{clinic_name}", org.name)
    emergency_phone = resolve_emergency_phone(org.emergency_deflection_phone, getattr(org, "country_code", None))
    async with AsyncSessionLocal() as db:
        from app.services.clinic.config_service import get_cached_clinic_context
        clinic = await get_cached_clinic_context(org.id, db)
        prompt = await build_clinic_prompt(db=db, org_id=org.id, clinic_name=org.name,
            tz_name=require_clinic_timezone(org), caller_name=caller_name, caller_phone=caller_phone,
            closure_notice=clinic.get("closure_notice"), custom_greeting=greeting,
            clinic_specialty=org.clinic_specialty, lead_doctor_name=org.lead_doctor_name,
            emergency_deflection_phone=emergency_phone)
    voice = resolve_voice(getattr(org, "voice_id", None) or org.ai_voice_name)
    stt_plugin = deepgram.STT(model=settings.VOICE_STT_MODEL, language=settings.VOICE_STT_LANGUAGE,
                             api_key=settings.DEEPGRAM_API_KEY)
    tts_plugin = deepgram.TTS(model=voice, api_key=settings.DEEPGRAM_API_KEY)
    llm_plugin = google.LLM(model=settings.GEMINI_MODEL, api_key=settings.GEMINI_API_KEY,
                            temperature=0.3, max_output_tokens=settings.VOICE_LLM_MAX_OUTPUT_TOKENS)
    vad_plugin = getattr(getattr(ctx, "proc", None), "userdata", {}).get("vad")
    if vad_plugin is None:
        vad_plugin = silero.VAD.load(min_silence_duration=0.5)
    session = AgentSession(
        stt=stt_plugin, tts=tts_plugin, llm=llm_plugin,
        vad=vad_plugin,
        turn_handling={
            "interruption": {"enabled": True, "mode": "vad", "min_duration": 0.7,
                             "min_words": 1, "resume_false_interruption": True},
            "endpointing": {"min_delay": 1.0, "max_delay": 2.0},
            "preemptive_generation": {"enabled": False},
        },
        max_tool_steps=2,
        conn_options=SessionConnectOptions(
            # Gemini rejects deadlines below 10s before generating any response.
            llm_conn_options=APIConnectOptions(max_retry=1, timeout=15.0, retry_interval=1.0),
            stt_conn_options=APIConnectOptions(max_retry=2, timeout=5.0, retry_interval=0.5),
            tts_conn_options=APIConnectOptions(max_retry=2, timeout=5.0, retry_interval=0.5),
        ),
    )
    agent = ClinicVoiceAgent(system_prompt=prompt, org_id=org.id, caller_phone=caller_phone,
                             emergency_phone=emergency_phone, room=ctx.room)
    agent.call_session_id = call_session_id
    recorder = CallRecorder(ctx.room, org.id, call_session_id)
    telemetry = VoiceTelemetry()
    turns, seen_items = [], set()
    stop = asyncio.Event()
    end_reason = "caller_disconnected"
    last_activity = asyncio.get_running_loop().time()
    activated = False
    durable_tasks = set()

    async def persist_readback(event_id, interrupted, expected_details, expected_caller):
        if interrupted:
            return
        await flush_pending_turns(session_id=call_session_id)
        async with AsyncSessionLocal() as db:
            call = await db.scalar(select(CallLog).where(CallLog.id == call_session_id,
                CallLog.org_id == org.id).with_for_update())
            if (call and call.booking_proposal and not call.booking_result
                    and call.booking_proposal.get("details") == expected_details
                    and call.booking_proposal.get("caller_event_id") == expected_caller):
                call.booking_proposal = {**call.booking_proposal, "readback_event_id": event_id}
                await db.commit()

    def schedule(coro):
        task = asyncio.create_task(coro)
        durable_tasks.add(task)
        def finished(completed):
            durable_tasks.discard(completed)
            if not completed.cancelled() and completed.exception():
                logger.error("Call persistence failed", exc_info=completed.exception())
                stop.set()
        task.add_done_callback(finished)

    @session.on("conversation_item_added")
    def on_item(event):
        nonlocal last_activity
        item = event.item
        role = getattr(item, "role", "")
        if role not in {"user", "assistant"}:
            return
        value = getattr(item, "text_content", None)
        if callable(value):
            value = value()
        if not isinstance(value, str):
            value = getattr(item, "raw_text_content", "")
        if not isinstance(value, str) or not value.strip():
            return
        event_id = str(getattr(item, "id", ""))
        if not event_id or event_id in seen_items:
            return
        seen_items.add(event_id)
        last_activity = asyncio.get_running_loop().time()
        turns.append({"role": "user" if role == "user" else "agent", "text": value,
                      "event_id": event_id, "interrupted": bool(getattr(item, "interrupted", False)),
                      "offset_seconds": max(0, last_activity-recorder.started_at)})
        if role == "user":
            agent.observe_caller_turn(event_id, value)
        queue_voice_turn(session_id=call_session_id, org_id=org.id, turn_number=len(turns),
            user_transcript=value if role == "user" else None,
            ai_response_text=value if role == "assistant" else None,
            event_id=event_id, interrupted=bool(getattr(item, "interrupted", False)))
        # Flush each committed event; call-end snapshots are derived, not the only copy.
        if role == "assistant" and agent.confirmation.proposal:
            interrupted = bool(getattr(item, "interrupted", False))
            agent.confirmation.readback(event_id, value, interrupted)
            schedule(persist_readback(event_id, interrupted, dict(agent.confirmation.proposal),
                                     agent.confirmation.proposal_turn))
        else:
            schedule(flush_pending_turns(session_id=call_session_id))
        if agent.state.get("service_unavailable"):
            async def end_after_notice():
                nonlocal end_reason
                end_reason = "provider_limit"
                await asyncio.sleep(3)
                stop.set()
            schedule(end_after_notice())

    @session.on("metrics_collected")
    def on_metrics(event):
        telemetry.record(event.metrics)

    @session.on("error")
    def on_error(event):
        nonlocal end_reason
        diag = classify_provider_error(event.error)
        logger.error(
            "Voice provider failed call=%s category=%s wrapper=%s underlying=%s status=%s request_id=%s msg=%s",
            call_session_id, diag.category.value, diag.wrapper_type, diag.underlying_type,
            diag.status_code, diag.request_id, diag.sanitized_message
        )
        if diag.recoverable:
            return
        wrapper_lower = f"{diag.wrapper_type.lower()} {diag.underlying_type.lower()}"
        if "stt" in wrapper_lower:
            end_reason = "stt_failure"
        elif "tts" in wrapper_lower:
            end_reason = "tts_failure"
        elif diag.category.value == "rate_limited":
            end_reason = "provider_limit"
        else:
            end_reason = "provider_unavailable"
        stop.set()

    @session.on("close")
    def on_close(event):
        nonlocal end_reason
        if agent.state.get("call_completed"):
            end_reason = "completed"
        stop.set()

    @session.on("function_tools_executed")
    def on_tools(event):
        names = [getattr(call, "name", "") for call in getattr(event, "function_calls", [])]
        if "deflect_emergency" in names:
            # Drain the emergency instruction instead of cutting it off on a timer.
            session.shutdown(drain=True)

    @session.on("agent_state_changed")
    def on_agent_state(event):
        nonlocal last_activity
        last_activity = asyncio.get_running_loop().time()

    @session.on("user_state_changed")
    def on_user_state(event):
        nonlocal last_activity
        last_activity = asyncio.get_running_loop().time()

    def disconnected(*args):
        stop.set()
    ctx.room.on("disconnected", disconnected)

    def on_room_data(data_packet):
        try:
            raw = getattr(data_packet, "data", b"")
            if isinstance(raw, str):
                raw = raw.encode("utf-8")
            payload = json.loads(raw.decode("utf-8"))
            msg_type = payload.get("type")
            if msg_type == "takeover_claim":
                agent.state["agent_paused"] = True
                session.interrupt()
                if ctx.room.local_participant:
                    for pub in ctx.room.local_participant.track_publications.values():
                        if getattr(pub, "track", None):
                            with suppress(Exception):
                                pub.track.set_mute(True)
                agent.outcome_tracker["call_outcome"] = "staff_takeover"
                ack = json.dumps({"type": "takeover_ack", "status": "claimed", "call_id": str(call_session_id)}).encode("utf-8")
                schedule(ctx.room.local_participant.publish_data(ack, reliable=True))
            elif msg_type == "takeover_release":
                agent.state["agent_paused"] = False
                if ctx.room.local_participant:
                    for pub in ctx.room.local_participant.track_publications.values():
                        if getattr(pub, "track", None):
                            with suppress(Exception):
                                pub.track.set_mute(False)
                ack = json.dumps({"type": "takeover_ack", "status": "released", "call_id": str(call_session_id)}).encode("utf-8")
                schedule(ctx.room.local_participant.publish_data(ack, reliable=True))
        except Exception:
            logger.warning("Failed processing room data packet", exc_info=True)
    ctx.room.on("data_received", on_room_data)

    async def checkpoint():
        while True:
            await asyncio.sleep(3)
            await flush_pending_turns(session_id=call_session_id)
            async with AsyncSessionLocal() as db:
                call = await db.get(CallLog, call_session_id)
                if call:
                    call.telemetry_summary = {**telemetry.payload(), "llm_model": settings.GEMINI_MODEL,
                        "stt_model": settings.VOICE_STT_MODEL, "tts_model": voice}
                    await db.commit()

    async def guard(deadline):
        nonlocal end_reason, last_activity
        while not stop.is_set():
            now = datetime.now(UTC)
            if now >= deadline:
                end_reason = "time_limit"
                stop.set()
                return
            is_idle = getattr(session, "agent_state", "listening") == "listening" and getattr(session, "user_state", "listening") == "listening"
            current_time = asyncio.get_running_loop().time()
            if not is_idle:
                last_activity = current_time
            elif current_time - last_activity >= 35:
                end_reason = "idle_timeout"
                stop.set()
                return
            await asyncio.sleep(min(1, max(0.1, (deadline-now).total_seconds())))

    background = []
    try:
        deadline = await activate_call(call_session_id, org.id)
        activated = True
        background = [asyncio.create_task(guard(deadline)), asyncio.create_task(checkpoint())]
        recorder.start()
        # Our CallRecorder already captures both tracks. Avoid the SDK's second
        # recording/mixing pipeline on the realtime event loop.
        started = await until_stopped(session.start(agent=agent, room=ctx.room, record=False,
            room_options=room_io.RoomOptions(participant_identity=participant_identity,
                text_input=False, close_on_disconnect=True,
                # The simulator already applies browser gain control. Avoid a
                # second synchronous gain pass; phone callers still need it.
                audio_input=room_io.AudioInputOptions(auto_gain_control=not browser_audio_processed),
                # Avoid spectral speech-rate analysis on the realtime audio loop.
                # Transcripts still publish, without word-by-word playout alignment.
                text_output=room_io.TextOutputOptions(sync_transcription=False))),
            stop, timeout=max(.1, min(15, (deadline-datetime.now(UTC)).total_seconds())))
        if not started:
            return
        async with AsyncSessionLocal() as db:
            call = await db.get(CallLog, call_session_id)
            if call and not call.end_time:
                call.connected_at = datetime.now(UTC)
                await db.commit()
        await until_stopped(session.say(greeting, allow_interruptions=True).wait_for_playout(),
            stop, timeout=max(.1, (deadline-datetime.now(UTC)).total_seconds()))
        await stop.wait()
    except Exception:
        end_reason = "service_unavailable"
        logger.exception("Clinic voice session failed")
    finally:
        for task in background:
            task.cancel()
        await asyncio.gather(*background, return_exceptions=True)
        if durable_tasks:
            with suppress(TimeoutError):
                await asyncio.wait_for(asyncio.gather(*list(durable_tasks), return_exceptions=True), 5)
        with suppress(Exception):
            await asyncio.wait_for(session.aclose(), 5)
        with suppress(Exception):
            await asyncio.wait_for(asyncio.gather(*(plugin.aclose() for plugin in
                (stt_plugin, tts_plugin, llm_plugin)), return_exceptions=True), 5)
        try:
            await terminate_call(call_session_id, org.id, end_reason)
        except Exception:
            logger.exception("Media termination pending; independent reconciler will retry")
        try:
            await flush_pending_turns(session_id=call_session_id)
            async with AsyncSessionLocal() as db:
                call = await db.scalar(select(CallLog).where(CallLog.id == call_session_id, CallLog.org_id == org.id).with_for_update())
                if call:
                    call.full_transcript = "\n".join(f"{'Caller' if t['role']=='user' else 'Receptionist'}: {t['text']}" for t in turns)
                    call.turns = turns
                    call.total_turns = len(turns)
                    call.telemetry_summary = {**telemetry.payload(), "llm_model": settings.GEMINI_MODEL,
                                             "stt_model": settings.VOICE_STT_MODEL, "tts_model": voice}
                    tracked_outcome = agent.outcome_tracker.get("call_outcome")
                    if call.booking_result or agent.state.get("booking_confirmed"):
                        call.call_outcome = "appointment_booked"
                    elif tracked_outcome in {"emergency_deflected", "transferred_to_staff", "staff_takeover", "staff_transfer_unavailable"}:
                        call.call_outcome = tracked_outcome
                    elif end_reason in {"caller_disconnected", "completed"} and any(t["role"] == "user" for t in turns):
                        call.call_outcome = tracked_outcome or "inquiry"
                    call.attended_by = "AI Receptionist" if activated else "Unattended / Missed"
                    # Booking for a family member must not rename a known caller.
                    if agent.outcome_tracker.get("caller_name") and (call.caller_name or "").strip().casefold() in {
                        "", "incoming caller", "anonymous caller", "unknown caller", "web simulator caller", "test caller",
                    }:
                        call.caller_name = agent.outcome_tracker["caller_name"]
                    call.chief_complaint = agent.outcome_tracker.get("chief_complaint")
                    if tracked_outcome == "emergency_deflected":
                        call.triage_status = "EMERGENCY"
                    else:
                        call.triage_status = "ADMIN" if any(t["role"] == "user" for t in turns) else "MISSED"
                    await db.commit()
        except Exception:
            logger.exception("Call summary pending; incremental transcript preserved")
        if activated:
            with suppress(Exception):
                await recorder.finalize()
        from app.services.infra.websocket_manager import ws_manager
        await ws_manager.broadcast_to_org(str(org.id), {"event": "CALL_ENDED", "call_id": str(call_session_id),
                                                       "room_name": ctx.room.name, "reason": end_reason})
