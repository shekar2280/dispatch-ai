import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import text
from app.core.config import settings
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


@dataclass
class BudgetReservation:
    key: str
    window_start: datetime
    units: int
    settled: bool = False


def budget_key(scope):
    return hashlib.sha256(("provider:" + scope).encode()).hexdigest()


def daily_start(now):
    return now.astimezone(ZoneInfo("America/Los_Angeles")).replace(
        hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def check_limits(recent_requests, recent_units, daily_requests, day_units,
                 units, rpm, tpm, rpd, daily_units):
    return not ((rpm and recent_requests + 1 > rpm) or (tpm and recent_units + units > tpm)
                or (rpd and daily_requests + 1 > rpd) or (daily_units and day_units + units > daily_units))


async def reserve_budget(scope, units=0, *, rpm=0, tpm=0, rpd=0, daily_units=0, db=None):
    if db is None:
        async with AsyncSessionLocal() as session:
            reservation = await reserve_budget(scope, units, rpm=rpm, tpm=tpm, rpd=rpd, daily_units=daily_units, db=session)
            await session.commit()
        return reservation
    now = datetime.now(timezone.utc)
    key = budget_key(scope)
    await db.execute(text("select pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key})
    row = (await db.execute(text("""
        select coalesce(sum(attempts) filter (where window_start >= :minute),0),
               coalesce(sum(tokens) filter (where window_start >= :minute),0),
               coalesce(sum(attempts) filter (where window_start >= :day),0),
               coalesce(sum(tokens) filter (where window_start >= :day),0)
        from public.voice_token_rate_limits where client_hash=:key and window_start >= :earliest
    """), {"key": key, "minute": now-timedelta(seconds=61), "day": daily_start(now),
           "earliest": min(daily_start(now), now-timedelta(seconds=61))})).one()
    if not check_limits(*row, units, rpm, tpm, rpd, daily_units):
        logger.warning("Provider budget refused scope=%s minute_requests=%s minute_units=%s requested_units=%s rpm=%s tpm=%s daily_requests=%s rpd=%s", scope, row[0], row[1], units, rpm, tpm, row[2], rpd)
        raise HTTPException(429, "Voice provider allowance is busy or exhausted. Please try again later.",
                            headers={"Retry-After": "60"})
    await db.execute(text("""
        insert into public.voice_token_rate_limits(client_hash,window_start,attempts,tokens)
        values (:key,:now,1,:units) on conflict (client_hash,window_start) do update
        set attempts=voice_token_rate_limits.attempts+1, tokens=voice_token_rate_limits.tokens+excluded.tokens
    """), {"key": key, "now": now.replace(microsecond=0), "units": max(0, int(units))})
    return BudgetReservation(key, now.replace(microsecond=0), max(0, int(units)))


async def settle_llm(reservation, actual_tokens):
    """Replace a conservative reservation with provider-reported usage.

    Request counts remain charged. Missing usage keeps the full reservation.
    """
    if not isinstance(reservation, BudgetReservation) or reservation.settled or actual_tokens <= 0:
        return
    async with AsyncSessionLocal() as db:
        await db.execute(text("select pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": reservation.key})
        await db.execute(text("""
            update public.voice_token_rate_limits
            set tokens=greatest(0, tokens + :delta)
            where client_hash=:key and window_start=:window
        """), {"key": reservation.key, "window": reservation.window_start,
                 "delta": int(actual_tokens) - reservation.units})
        await db.commit()
    reservation.settled = True


async def reserve_llm(input_upper_bound):
    if min(settings.VOICE_GEMINI_RPM, settings.VOICE_GEMINI_TPM, settings.VOICE_GEMINI_RPD) <= 0:
        raise HTTPException(503, "Gemini project limits are not configured")
    return await reserve_budget("gemini:" + settings.GEMINI_MODEL, input_upper_bound,
        rpm=max(1, int(settings.VOICE_GEMINI_RPM * .8)),
        tpm=max(1, int(settings.VOICE_GEMINI_TPM * .8)),
        rpd=max(1, int(settings.VOICE_GEMINI_RPD * .8)))
