import asyncio
import logging
from datetime import UTC, datetime, timedelta
from sqlalchemy import select, delete, text
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.call_session import CallLog
from app.models.call_turn import VoiceCallTurn
from app.services.infra.storage import _call_storage_client, CALL_RECORDING_BUCKET

logger = logging.getLogger(__name__)


async def prune_limit_windows():
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("delete from public.voice_token_rate_limits where window_start < :cutoff"),
            {"cutoff": datetime.now(UTC) - timedelta(days=2)},
        )
        await db.commit()


async def purge_expired_audio_recordings(batch_size: int = 100) -> int:
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=settings.VOICE_AUDIO_RETENTION_DAYS)
    purged_count = 0

    async with AsyncSessionLocal() as db:
        query = (
            select(CallLog)
            .where(
                CallLog.end_time < cutoff,
                CallLog.recording_status.in_(["ready", "partial"]),
                CallLog.recording_storage_path.is_not(None),
            )
            .limit(batch_size)
        )
        calls = (await db.scalars(query)).all()
        if not calls:
            return 0

        paths_to_delete = []
        calls_to_update = []
        for call in calls:
            raw_path = call.recording_storage_path.removeprefix(f"{CALL_RECORDING_BUCKET}/")
            paths_to_delete.append(raw_path)
            partial_path = raw_path.removesuffix(".wav") + ".partial.wav"
            paths_to_delete.append(partial_path)
            calls_to_update.append(call)

        try:
            client = _call_storage_client()
            await asyncio.to_thread(client.storage.from_(CALL_RECORDING_BUCKET).remove, paths_to_delete)
        except Exception as exc:
            logger.warning("Failed to batch delete audio paths from storage: %s", exc)

        for call in calls_to_update:
            summary = dict(call.telemetry_summary or {})
            summary["audio_purged_at"] = now.isoformat()
            call.telemetry_summary = summary
            call.recording_storage_path = None
            call.recording_status = "disabled"
            purged_count += 1

        await db.commit()
    return purged_count


async def redact_expired_transcripts(batch_size: int = 100) -> int:
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=settings.VOICE_TRANSCRIPT_RETENTION_DAYS)
    redacted_count = 0

    async with AsyncSessionLocal() as db:
        query = (
            select(CallLog)
            .where(
                CallLog.end_time < cutoff,
                CallLog.quota_charged_at.is_not(None),
                CallLog.caller_phone != "Redacted",
            )
            .limit(batch_size)
        )
        calls = (await db.scalars(query)).all()
        if not calls:
            return 0

        for call in calls:
            await db.execute(
                delete(VoiceCallTurn).where(
                    VoiceCallTurn.org_id == call.org_id,
                    VoiceCallTurn.session_id == call.id,
                )
            )
            call.full_transcript = None
            call.turns = []
            call.booking_proposal = None
            call.booking_result = None
            call.caller_name = None
            call.caller_phone = "Redacted"
            summary = dict(call.telemetry_summary or {})
            summary["transcript_redacted_at"] = now.isoformat()
            call.telemetry_summary = summary
            redacted_count += 1

        await db.commit()
    return redacted_count


async def run_daily_retention_sweep() -> dict:
    purged_audio = await purge_expired_audio_recordings()
    redacted_phi = await redact_expired_transcripts()
    await prune_limit_windows()
    return {"purged_audio": purged_audio, "redacted_transcripts": redacted_phi}


async def apply_demo_retention():
    await run_daily_retention_sweep()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run retention sweep")
    parser.add_argument("--apply", action="store_true", required=True)
    parser.parse_args()
    asyncio.run(run_daily_retention_sweep())
