import hashlib
import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.call_session import CallLog

logger = logging.getLogger(__name__)

TOKEN_REQUESTS_PER_MINUTE = 10


def client_window(client_host, now):
    return hashlib.sha256(client_host.encode()).hexdigest(), now.astimezone(UTC).replace(second=0, microsecond=0)


async def limit_voice_token_requests(request: Request, db):
    if not request.client:
        raise HTTPException(400, "Client address unavailable")
    now = datetime.now(UTC)
    client_hash, window = client_window(request.client.host, now)
    attempts = await db.scalar(text("""
        insert into public.voice_token_rate_limits(client_hash, window_start, attempts)
        values (:client_hash, :window, 1)
        on conflict (client_hash, window_start) do update
        set attempts = voice_token_rate_limits.attempts + 1
        returning attempts
    """), {"client_hash": client_hash, "window": window})
    await db.commit()
    if attempts > TOKEN_REQUESTS_PER_MINUTE:
        raise HTTPException(429, "Too many voice token requests. Please try again shortly.",
                            headers={"Retry-After": str(60 - now.second)})


class AdmissionRejectionReason:
    ORG_CAPACITY_EXCEEDED = "org_capacity_exceeded"
    GLOBAL_CAPACITY_EXCEEDED = "global_capacity_exceeded"
    DATABASE_POOL_SATURATED = "database_pool_saturated"


ADMISSION_REJECTIONS: dict[str, int] = {
    AdmissionRejectionReason.ORG_CAPACITY_EXCEEDED: 0,
    AdmissionRejectionReason.GLOBAL_CAPACITY_EXCEEDED: 0,
    AdmissionRejectionReason.DATABASE_POOL_SATURATED: 0,
}


def record_rejection(reason: str):
    if reason in ADMISSION_REJECTIONS:
        ADMISSION_REJECTIONS[reason] += 1


def get_admission_rejections() -> dict[str, int]:
    return dict(ADMISSION_REJECTIONS)


async def check_voice_call_admission(
    db: AsyncSession,
    org_id: UUID,
) -> bool:
    try:
        from app.core.database import engine
        pool = getattr(engine, "pool", None)
        if pool and hasattr(pool, "checkedout") and hasattr(pool, "size") and pool.checkedout() >= pool.size() + getattr(pool, "max_overflow", 0):
            logger.warning("Voice admission rejected: database pool saturated")
            record_rejection(AdmissionRejectionReason.DATABASE_POOL_SATURATED)
            raise HTTPException(
                status_code=503,
                detail="Database connection pool saturated. Please retry shortly.",
                headers={"Retry-After": "5", "X-Admission-Reason": AdmissionRejectionReason.DATABASE_POOL_SATURATED},
            )
    except HTTPException:
        raise
    except Exception:
        pass

    global_active_query = select(func.count(CallLog.id)).where(CallLog.end_time.is_(None))
    global_active_res = await db.scalar(global_active_query)
    global_active = int(global_active_res) if isinstance(global_active_res, (int, float)) else 0
    if global_active >= settings.VOICE_MAX_CONCURRENT_CALLS_GLOBAL:
        logger.warning(
            "Voice admission rejected: global concurrency limit reached (%s/%s)",
            global_active,
            settings.VOICE_MAX_CONCURRENT_CALLS_GLOBAL,
        )
        record_rejection(AdmissionRejectionReason.GLOBAL_CAPACITY_EXCEEDED)
        raise HTTPException(
            status_code=503,
            detail="Voice service platform capacity reached. Please try again shortly.",
            headers={"Retry-After": "15", "X-Admission-Reason": AdmissionRejectionReason.GLOBAL_CAPACITY_EXCEEDED},
        )

    org_active_query = select(func.count(CallLog.id)).where(CallLog.org_id == org_id, CallLog.end_time.is_(None))
    org_active_res = await db.scalar(org_active_query)
    org_active = int(org_active_res) if isinstance(org_active_res, (int, float)) else 0
    if org_active >= settings.VOICE_MAX_CONCURRENT_CALLS_PER_ORG:
        logger.warning(
            "Voice admission rejected: org %s concurrency limit reached (%s/%s)",
            org_id,
            org_active,
            settings.VOICE_MAX_CONCURRENT_CALLS_PER_ORG,
        )
        record_rejection(AdmissionRejectionReason.ORG_CAPACITY_EXCEEDED)
        raise HTTPException(
            status_code=429,
            detail="Organization voice concurrent limit reached. Please try again shortly.",
            headers={"Retry-After": "10", "X-Admission-Reason": AdmissionRejectionReason.ORG_CAPACITY_EXCEEDED},
        )

    return True
