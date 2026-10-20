"""Durable reservations; terminal updates settle through a database trigger."""
import math
from fastapi import HTTPException
from sqlalchemy import select, func, text, BigInteger
from app.core.config import settings
from app.models.call_session import CallLog
from app.models.organization import Organization
from app.models.audit_log import SystemAuditLog

VOICE_DEMO_MINUTES = 30


def charge_seconds(start, end, allocation):
    if start is None:
        return 0
    return min(allocation, max(0, math.ceil((end - start).total_seconds())))


async def allowance_snapshot(db, org_id):
    credits_query = select(func.coalesce(func.sum(
        SystemAuditLog.new_state["seconds"].astext.cast(BigInteger)), 0)).where(
        SystemAuditLog.org_id == org_id,
        SystemAuditLog.action_type == "VOICE_CREDIT_GRANTED").scalar_subquery()
    held_query = select(func.coalesce(func.sum(func.greatest(
        CallLog.call_budget_seconds - CallLog.charged_seconds, 0)), 0)).where(
        CallLog.org_id == org_id, CallLog.media_terminated_at.is_(None)).scalar_subquery()
    snapshot = (await db.execute(select(Organization.voice_seconds_used, held_query, credits_query).where(
        Organization.id == org_id))).one_or_none()
    if snapshot is None:
        raise HTTPException(404, "Organization not found")
    consumed, held = int(snapshot[0] or 0), int(snapshot[1] or 0)
    bonus = int(snapshot[2] or 0)
    base = VOICE_DEMO_MINUTES * 60
    limit = base + bonus
    return {"limit_seconds": limit, "base_seconds": base, "bonus_seconds": bonus, "used_seconds": consumed,
            "reserved_seconds": int(held or 0),
            "remaining_seconds": max(0, limit - consumed - int(held or 0)),
            "max_call_seconds": max(1, min(120, settings.VOICE_MAX_CALL_SECONDS))}


async def enforce_voice_demo_allowance(db, org_id):
    if not settings.VOICE_ENABLED:
        raise HTTPException(503, "Voice testing is temporarily paused")
    await db.execute(text("select pg_advisory_xact_lock(hashtextextended('voice-admission', 0))"))
    org = await db.scalar(select(Organization).where(Organization.id == org_id))
    if not org:
        raise HTTPException(404, "Organization not found")
    snapshot = await allowance_snapshot(db, org_id)
    if snapshot["remaining_seconds"] < 1:
        raise HTTPException(402, {"code": "VOICE_DEMO_LIMIT_REACHED", **snapshot,
                                 "message": "This clinic has used or reserved its available voice minutes."})
    if snapshot["reserved_seconds"]:
        raise HTTPException(409, "This clinic already has a call connecting or in progress")
    active = await db.scalar(select(func.count()).select_from(CallLog).where(CallLog.media_terminated_at.is_(None)))
    if active >= max(1, settings.VOICE_GLOBAL_CONCURRENCY):
        raise HTTPException(429, "The demo voice line is busy. Please try again shortly.", headers={"Retry-After": "15"})
    from app.services.voice.provider_budget import reserve_budget
    budget = min(snapshot["max_call_seconds"], snapshot["remaining_seconds"])
    await reserve_budget("voice-seconds", budget, daily_units=settings.VOICE_GLOBAL_DAILY_SECONDS, db=db)
    return budget
