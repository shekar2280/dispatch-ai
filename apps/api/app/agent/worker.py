import logging
import asyncio
from datetime import UTC, datetime
from livekit import rtc
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
)
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.organization import Organization
from app.models.call_session import CallLog
from app.agent.call_context import parse_participant_call_context
from app.agent.clinic.session import run_clinic_session

logger = logging.getLogger("app.agent.worker")
logging.getLogger("hpack").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

async def entrypoint(ctx: JobContext):
    # CLI dev mode sets DEBUG after module import; enforce redaction per job.
    logging.getLogger("livekit.agents").setLevel(logging.WARNING)
    logging.getLogger("livekit.plugins").setLevel(logging.WARNING)
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    async with AsyncSessionLocal() as db:
        admitted = await db.scalar(select(CallLog).where(CallLog.room_name == ctx.room.name))
        expected_identity = admitted.caller_identity if admitted and admitted.session_type == "voice_simulator" else None
    participant = await asyncio.wait_for(ctx.wait_for_participant(identity=expected_identity), 30)

    try:
        context = parse_participant_call_context(participant.metadata, dict(participant.attributes))
        async with AsyncSessionLocal() as db:
            call = await db.scalar(select(CallLog).where(CallLog.room_name == ctx.room.name).with_for_update())
            if not call and participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP and context.call_id and context.org_id:
                call = await db.scalar(select(CallLog).where(
                    CallLog.id == context.call_id,
                    CallLog.org_id == context.org_id,
                    CallLog.session_type == "voice_call",
                    CallLog.end_time.is_(None),
                    CallLog.agent_joined_at.is_(None),
                ).with_for_update())
                if call:
                    call.room_name = ctx.room.name
            if not call or (context.org_id and context.org_id != call.org_id):
                raise ValueError("Room has no matching authorized call session")
            if context.call_id and context.call_id != call.id:
                raise ValueError("SIP call identity does not match room")
            if call.end_time is not None:
                raise ValueError("Call session has already ended")
            now = datetime.now(UTC)
            if call.agent_joined_at or not call.admission_expires_at or call.admission_expires_at <= now:
                raise ValueError("Call admission expired or claimed")
            if call.session_type == "voice_simulator" and participant.identity != call.caller_identity:
                raise ValueError("Participant is not the admitted caller")
            if call.session_type == "voice_call" and participant.kind != rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
                raise ValueError("Expected a SIP caller")
            if call.session_type == "voice_call" and (context.call_id != call.id or context.org_id != call.org_id):
                raise ValueError("SIP caller lacks matching trusted call context")
            call.agent_joined_at = now
            org = await db.get(Organization, call.org_id)
            if not org:
                raise ValueError("Call organization does not exist")
            caller_phone = call.caller_phone
            caller_name = call.caller_name or context.caller_name
            await db.commit()
    except (ValueError, TypeError):
        logger.warning("Rejecting worker session with invalid call context")
        await ctx.room.disconnect()
        return

    await run_clinic_session(
        ctx=ctx,
        org=org,
        caller_phone=caller_phone,
        caller_name=caller_name,
        stt_provider="deepgram",
        call_session_id=call.id,
        participant_identity=participant.identity,
        browser_audio_processed=call.session_type == "voice_simulator",
    )


def prewarm(proc: JobProcess):
    from sqlalchemy.orm import configure_mappers
    from livekit.plugins import silero
    from app.agent.clinic.tools import ClinicVoiceAgent
    # These imports otherwise block the audio event loop on the first call.
    from app.services.clinic.config_service import get_cached_clinic_context
    from app.services.voice.booking_consent import authorize_booking
    configure_mappers()
    proc.userdata["vad"] = silero.VAD.load(min_silence_duration=0.5)
    ClinicVoiceAgent(system_prompt="Warmup instructions")


if __name__ == "__main__":
    logging.getLogger("livekit.agents").setLevel(logging.WARNING)
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            # Dev mode defaults to zero; keep the first local call warm too.
            num_idle_processes=1,
            initialize_process_timeout=60,
            shutdown_process_timeout=60,
        )
    )

