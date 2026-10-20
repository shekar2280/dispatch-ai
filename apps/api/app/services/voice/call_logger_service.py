import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.call_session import VoiceCallSession
from app.models.call_turn import VoiceCallTurn
from app.models.organization import Organization

logger = logging.getLogger(__name__)

_TURN_QUEUE: asyncio.Queue = asyncio.Queue()
_FLUSH_TASK: Optional[asyncio.Task] = None
_FLUSH_LOCK: asyncio.Lock = asyncio.Lock()


async def start_turn_flush_worker():
    global _FLUSH_TASK
    if _FLUSH_TASK is None or _FLUSH_TASK.done():
        _FLUSH_TASK = asyncio.create_task(_flush_worker_loop())


async def stop_turn_flush_worker():
    global _FLUSH_TASK
    if _FLUSH_TASK and not _FLUSH_TASK.done():
        _FLUSH_TASK.cancel()
        try:
            await _FLUSH_TASK
        except asyncio.CancelledError:
            pass
        _FLUSH_TASK = None


async def flush_pending_turns(
    db: Optional[AsyncSession] = None,
    session_id: Optional[uuid.UUID] = None,
):
    async with _FLUSH_LOCK:
        pending_turns = []
        retained_turns = []
        while not _TURN_QUEUE.empty():
            try:
                item = _TURN_QUEUE.get_nowait()
                if session_id is None or getattr(item, "session_id", None) == session_id:
                    pending_turns.append(item)
                else:
                    retained_turns.append(item)
            except Exception:
                break

        for item in retained_turns:
            _TURN_QUEUE.put_nowait(item)

        if not pending_turns:
            return

        values_list = [
            {
                "id": getattr(t, "id", None) or uuid.uuid4(),
                "session_id": t.session_id,
                "org_id": t.org_id,
                "turn_number": t.turn_number,
                "event_id": t.event_id, "interrupted": t.interrupted,
                "user_transcript": t.user_transcript,
                "user_audio_url": t.user_audio_url,
                "ai_filler_text": t.ai_filler_text,
                "ai_filler_audio_url": t.ai_filler_audio_url,
                "ai_response_text": t.ai_response_text,
                "ai_response_audio_url": t.ai_response_audio_url,
                "stt_latency_ms": t.stt_latency_ms,
                "llm_latency_ms": t.llm_latency_ms,
                "tts_latency_ms": t.tts_latency_ms,
                "total_latency_ms": t.total_latency_ms,
                "created_at": getattr(t, "created_at", None) or datetime.now(timezone.utc),
            }
            for t in pending_turns
        ]
        stmt = pg_insert(VoiceCallTurn).values(values_list).on_conflict_do_nothing()

        try:
            if db is not None:
                await db.execute(stmt)
                await db.commit()
            else:
                from app.core.database import AsyncSessionLocal
                async with AsyncSessionLocal() as session:
                    await session.execute(stmt)
                    await session.commit()
        except Exception as db_err:
            logger.error(f"Failed to flush queued turns to database: {db_err}")
            try:
                if db is not None:
                    await db.rollback()
            except Exception:
                pass
            for t in pending_turns:
                _TURN_QUEUE.put_nowait(t)
            raise


async def _flush_worker_loop():
    from app.core.database import AsyncSessionLocal
    while True:
        try:
            await asyncio.sleep(3.0)
            async with _FLUSH_LOCK:
                pending_turns = []
                while not _TURN_QUEUE.empty():
                    item = _TURN_QUEUE.get_nowait()
                    pending_turns.append(item)

                if pending_turns:
                    try:
                        values_list = [
                            {
                                "id": getattr(t, "id", None) or uuid.uuid4(),
                                "session_id": t.session_id,
                                "org_id": t.org_id,
                                "turn_number": t.turn_number,
                "event_id": t.event_id, "interrupted": t.interrupted,
                                "user_transcript": t.user_transcript,
                                "user_audio_url": t.user_audio_url,
                                "ai_filler_text": t.ai_filler_text,
                                "ai_filler_audio_url": t.ai_filler_audio_url,
                                "ai_response_text": t.ai_response_text,
                                "ai_response_audio_url": t.ai_response_audio_url,
                                "stt_latency_ms": t.stt_latency_ms,
                                "llm_latency_ms": t.llm_latency_ms,
                                "tts_latency_ms": t.tts_latency_ms,
                                "total_latency_ms": t.total_latency_ms,
                                "created_at": getattr(t, "created_at", None) or datetime.now(timezone.utc),
                            }
                            for t in pending_turns
                        ]
                        stmt = pg_insert(VoiceCallTurn).values(values_list).on_conflict_do_nothing()
                        async with AsyncSessionLocal() as db:
                            await db.execute(stmt)
                            await db.commit()
                    except Exception as db_err:
                        logger.error(f"Failed to flush queued turns to database: {db_err}")
                        for t in pending_turns:
                            _TURN_QUEUE.put_nowait(t)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in telemetry turn flush worker loop: {e}")


def queue_voice_turn(
    session_id: uuid.UUID,
    org_id: uuid.UUID,
    turn_number: int,
    user_transcript: Optional[str] = None,
    user_audio_url: Optional[str] = None,
    ai_filler_text: Optional[str] = None,
    ai_filler_audio_url: Optional[str] = None,
    ai_response_text: Optional[str] = None,
    ai_response_audio_url: Optional[str] = None,
    stt_latency_ms: Optional[int] = None,
    llm_latency_ms: Optional[int] = None,
    tts_latency_ms: Optional[int] = None,
    total_latency_ms: Optional[int] = None,
    event_id: Optional[str] = None,
    interrupted: bool = False,
):
    """Pushes a call turn non-blockingly to the flush queue."""
    turn = VoiceCallTurn(
        id=uuid.uuid4(),
        session_id=session_id,
        org_id=org_id,
        turn_number=turn_number,
        user_transcript=user_transcript,
        user_audio_url=user_audio_url,
        ai_filler_text=ai_filler_text,
        ai_filler_audio_url=ai_filler_audio_url,
        ai_response_text=ai_response_text,
        ai_response_audio_url=ai_response_audio_url,
        stt_latency_ms=stt_latency_ms,
        llm_latency_ms=llm_latency_ms,
        tts_latency_ms=tts_latency_ms,
        total_latency_ms=total_latency_ms,
        created_at=datetime.now(timezone.utc),
        event_id=event_id,
        interrupted=interrupted,
    )
    _TURN_QUEUE.put_nowait(turn)
    global _FLUSH_TASK
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running() and (_FLUSH_TASK is None or _FLUSH_TASK.done()):
            _FLUSH_TASK = loop.create_task(_flush_worker_loop())
    except RuntimeError:
        pass


async def start_voice_session(
    db: AsyncSession,
    org_id: uuid.UUID,
    caller_phone: str,
    caller_name: Optional[str] = None,
    patient_id: Optional[uuid.UUID] = None,
    session_type: str = "voice_simulator",
    room_name: Optional[str] = None,
) -> Optional[VoiceCallSession]:
    """Creates a master voice call session record in the database."""
    try:
        res = await db.execute(select(Organization).where(Organization.id == org_id))
        valid_org = res.scalar_one_or_none()
        resolved_org_id = valid_org.id if valid_org else org_id

        session = VoiceCallSession(
            id=uuid.uuid4(),
            org_id=resolved_org_id,
            caller_phone=caller_phone,
            caller_name=caller_name,
            patient_id=patient_id,
            session_type=session_type,
            room_name=room_name,
            triage_status="admin",
            call_outcome="inquiry",
            total_turns=0,
            start_time=datetime.now(timezone.utc),
        )
        db.add(session)
        await db.commit()
        return session
    except Exception as e:
        await db.rollback()
        logger.error(f"Could not create voice_call_session: {e}")
        return None


async def initialize_call_session(
    org_id: Optional[uuid.UUID],
    room_name: str,
    caller_phone: str,
    caller_name: Optional[str] = None,
    call_session_id: Optional[uuid.UUID] = None,
    call_start_time: Optional[datetime] = None,
) -> uuid.UUID:
    if not org_id or not call_session_id:
        raise ValueError("An authorized canonical call ID is required")
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        call = await db.scalar(select(VoiceCallSession).where(
            VoiceCallSession.id == call_session_id, VoiceCallSession.org_id == org_id,
            VoiceCallSession.room_name == room_name, VoiceCallSession.end_time.is_(None)))
        if not call:
            raise ValueError("Authorized call session not found")
        return call.id


async def log_voice_turn(
    db: AsyncSession,
    session_id: uuid.UUID,
    org_id: uuid.UUID,
    turn_number: int,
    user_transcript: Optional[str] = None,
    user_audio_url: Optional[str] = None,
    ai_filler_text: Optional[str] = None,
    ai_filler_audio_url: Optional[str] = None,
    ai_response_text: Optional[str] = None,
    ai_response_audio_url: Optional[str] = None,
    stt_latency_ms: Optional[int] = None,
    llm_latency_ms: Optional[int] = None,
    tts_latency_ms: Optional[int] = None,
    total_latency_ms: Optional[int] = None,
) -> Optional[VoiceCallTurn]:
    """Persists a turn-by-turn audit record synchronously."""
    try:
        res = await db.execute(select(Organization).where(Organization.id == org_id))
        valid_org = res.scalar_one_or_none()
        resolved_org_id = valid_org.id if valid_org else org_id

        turn = VoiceCallTurn(
            id=uuid.uuid4(),
            session_id=session_id,
            org_id=resolved_org_id,
            turn_number=turn_number,
            user_transcript=user_transcript,
            user_audio_url=user_audio_url,
            ai_filler_text=ai_filler_text,
            ai_filler_audio_url=ai_filler_audio_url,
            ai_response_text=ai_response_text,
            ai_response_audio_url=ai_response_audio_url,
            stt_latency_ms=stt_latency_ms,
            llm_latency_ms=llm_latency_ms,
            tts_latency_ms=tts_latency_ms,
            total_latency_ms=total_latency_ms,
            created_at=datetime.now(timezone.utc),
        )
        db.add(turn)
        result = await db.execute(
            select(VoiceCallSession).where(VoiceCallSession.id == session_id)
        )
        sess = result.scalar_one_or_none()
        if sess:
            sess.total_turns = (sess.total_turns or 0) + 1

        await db.commit()
        return turn
    except Exception as e:
        await db.rollback()
        logger.error(f"Could not log voice turn: {e}")
        return None


async def finalize_voice_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    call_outcome: str = "inquiry",
    full_transcript: Optional[str] = None,
    triage_status: str = "admin",
    duration_seconds: Optional[int] = None,
    attended_by: Optional[str] = None,
    turns: Optional[List[Dict[str, Any]]] = None,
    total_turns: Optional[int] = None,
    chief_complaint: Optional[str] = None,
    caller_name: Optional[str] = None,
) -> Optional[VoiceCallSession]:
    try:
        result = await db.execute(
            select(VoiceCallSession).where(VoiceCallSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            return None

        session.end_time = datetime.now(timezone.utc)
        if duration_seconds is not None:
            session.duration_seconds = max(0, duration_seconds)
        elif session.start_time:
            start_utc = (
                session.start_time
                if session.start_time.tzinfo
                else session.start_time.replace(tzinfo=timezone.utc)
            )
            delta = session.end_time - start_utc
            session.duration_seconds = max(0, int(delta.total_seconds()))

        session.call_outcome = call_outcome
        if session.call_status not in ("completed", "missed", "failed"):
            session.call_status = "completed" if session.agent_joined_at or session.connected_at else "missed"
        session.triage_status = triage_status
        if attended_by:
            session.attended_by = attended_by
        if full_transcript:
            session.full_transcript = full_transcript
        if turns is not None:
            session.turns = turns
        if total_turns is not None:
            session.total_turns = max(0, total_turns)
        if chief_complaint:
            session.chief_complaint = chief_complaint
        if caller_name:
            session.caller_name = caller_name

        await db.commit()
        return session
    except Exception as e:
        await db.rollback()
        logger.error(f"Could not finalize voice session: {e}")
        return None


async def get_recent_voice_turns(
    db: AsyncSession, limit: int = 20
) -> List[Dict[str, Any]]:
    """Retrieves recent voice turns with session metadata."""
    stmt = (
        select(VoiceCallTurn, VoiceCallSession)
        .join(VoiceCallSession, VoiceCallTurn.session_id == VoiceCallSession.id)
        .order_by(VoiceCallTurn.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()
    out = []
    for turn, session in rows:
        out.append({
            "session_id": str(session.id),
            "caller_phone": session.caller_phone,
            "caller_name": session.caller_name,
            "turn_number": turn.turn_number,
            "user_transcript": turn.user_transcript,
            "ai_response_text": turn.ai_response_text,
            "total_latency_ms": turn.total_latency_ms,
            "created_at": turn.created_at.isoformat() if turn.created_at else None,
        })
    return out
