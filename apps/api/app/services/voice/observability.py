import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import engine
from app.core.voice_admission import get_admission_rejections
from app.models.call_session import CallLog
from app.models.outbox_event import OutboxEvent
from app.models.voice_mutation_operation import VoiceMutationOperation
from app.models.voice_workflow_checkpoint import VoiceWorkflowCheckpoint
from app.services.voice.call_logger_service import _TURN_QUEUE
from app.services.voice.circuit_breaker import circuit_breaker

logger = logging.getLogger(__name__)


def get_database_pool_stats() -> dict[str, Any]:
    pool = getattr(engine, "pool", None)
    if not pool:
        return {"configured": False}
    return {
        "configured": True,
        "size": getattr(pool, "size", lambda: 0)(),
        "checked_in": getattr(pool, "checkedin", lambda: 0)(),
        "checked_out": getattr(pool, "checkedout", lambda: 0)(),
        "overflow": getattr(pool, "overflow", lambda: 0)(),
    }


def get_circuit_breaker_stats() -> dict[str, Any]:
    providers = ["groq", "gemini", "deepgram", "elevenlabs"]
    stats = {}
    for p in providers:
        health = circuit_breaker.get_health(p)
        stats[p] = {
            "state": health.state.value if hasattr(health.state, "value") else str(health.state),
            "failure_count": health.failure_count,
            "retry_after": health.retry_after,
        }
    return stats


def get_journal_buffer_stats() -> dict[str, Any]:
    return {
        "buffer_items": len(_TURN_QUEUE._items) if hasattr(_TURN_QUEUE, "_items") else 0,
        "buffer_bytes": getattr(_TURN_QUEUE, "current_bytes", 0),
        "shed_count": getattr(_TURN_QUEUE, "shed_count", 0),
    }


async def collect_voice_system_metrics(db: AsyncSession) -> dict[str, Any]:
    pool_stats = get_database_pool_stats()
    circuit_stats = get_circuit_breaker_stats()
    journal_stats = get_journal_buffer_stats()
    admission_rejections = get_admission_rejections()

    active_calls_count = (await db.scalar(select(func.count(CallLog.id)).where(CallLog.end_time.is_(None)))) or 0
    committed_unack_count = (await db.scalar(
        select(func.count(CallLog.id)).where(CallLog.call_outcome == "committed_but_not_acknowledged")
    )) or 0
    resumed_calls_count = (await db.scalar(
        select(func.count(CallLog.id)).where(CallLog.resumed_from_call_id.isnot(None))
    )) or 0

    pending_outbox = (await db.scalar(
        select(func.count(OutboxEvent.id)).where(OutboxEvent.status == "pending")
    )) or 0
    failed_outbox = (await db.scalar(
        select(func.count(OutboxEvent.id)).where(OutboxEvent.status == "failed")
    )) or 0
    dead_letter_outbox = (await db.scalar(
        select(func.count(OutboxEvent.id)).where(OutboxEvent.status == "dead_letter")
    )) or 0
    oldest_pending_outbox = await db.scalar(
        select(func.min(OutboxEvent.created_at)).where(OutboxEvent.status == "pending")
    )

    total_mutations = (await db.scalar(select(func.count(VoiceMutationOperation.id)))) or 0
    completed_mutations = (await db.scalar(
        select(func.count(VoiceMutationOperation.id)).where(VoiceMutationOperation.status == "completed")
    )) or 0

    checkpoints_count = (await db.scalar(select(func.count(VoiceWorkflowCheckpoint.id)))) or 0

    return {
        "database_pool": pool_stats,
        "circuits": circuit_stats,
        "journal_queue": journal_stats,
        "admission": {
            "active_calls": active_calls_count,
            "max_concurrent_global": settings.VOICE_MAX_CONCURRENT_CALLS_GLOBAL,
            "max_concurrent_per_org": settings.VOICE_MAX_CONCURRENT_CALLS_PER_ORG,
            "rejections": admission_rejections,
        },
        "outbox": {
            "pending_count": pending_outbox,
            "failed_count": failed_outbox,
            "dead_letter_count": dead_letter_outbox,
            "oldest_pending_at": oldest_pending_outbox.isoformat() if oldest_pending_outbox else None,
        },
        "mutations": {
            "total_count": total_mutations,
            "completed_count": completed_mutations,
            "committed_but_not_acknowledged_calls": committed_unack_count,
        },
        "recovery": {
            "enabled": settings.VOICE_RECOVERY_ENABLED,
            "rollout_stage": settings.VOICE_ROLLOUT_STAGE,
            "rollout_percentage": settings.VOICE_ROLLOUT_PERCENTAGE,
            "checkpoints_count": checkpoints_count,
            "resumed_calls_count": resumed_calls_count,
        },
    }
