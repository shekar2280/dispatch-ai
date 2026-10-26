import asyncio
import logging
import math
import uuid
from datetime import UTC, datetime, timedelta
from sqlalchemy import select, or_
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.call_session import CallEndReason, CallLog, normalize_call_end_reason

logger = logging.getLogger(__name__)


async def activate_call(call_id, org_id):
    async with AsyncSessionLocal() as db:
        call = await db.scalar(select(CallLog).where(CallLog.id == call_id, CallLog.org_id == org_id).with_for_update())
        now = datetime.now(UTC)
        if not call or call.end_time or call.provider_started_at:
            raise ValueError("Call is closed or already activated")
        if not call.admission_expires_at or call.admission_expires_at <= now:
            raise ValueError("Call admission expired")
        call.provider_started_at = now
        call.deadline_at = now + timedelta(seconds=call.call_budget_seconds)
        call.call_status = "in_progress"
        call.triage_status = "IN_PROGRESS"
        call.call_outcome = "in_progress"
        await db.commit()
        return call.deadline_at


async def _cleanup_livekit(room: str | None) -> bool:
    if not room:
        return True
    try:
        from livekit.api import LiveKitAPI, DeleteRoomRequest, TwirpError
        async with LiveKitAPI(settings.LIVEKIT_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET) as api:
            await asyncio.wait_for(api.room.delete_room(DeleteRoomRequest(room=room)), 5)
            return True
    except TwirpError as exc:
        if exc.code == "not_found":
            return True
        logger.warning("LiveKit room deletion failed for room %s: %s", room, exc)
        return False
    except Exception as exc:
        logger.warning("LiveKit room deletion error for room %s: %s", room, exc)
        return False


async def _cleanup_twilio(sid: str | None) -> bool:
    if not sid or not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        return True
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Calls/{sid}.json",
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
                data={"Status": "completed"},
            )
            response.raise_for_status()
            return True
    except Exception as exc:
        logger.warning("Twilio call completion failed for sid %s: %s", sid, exc)
        return False


async def claim_reconciliation_batch(worker_id: str, batch_size: int = 20, lease_duration_seconds: int = 30) -> list[dict]:
    now = datetime.now(UTC)
    claimed: list[dict] = []
    async with AsyncSessionLocal() as db:
        query = (
            select(CallLog)
            .where(
                CallLog.media_terminated_at.is_(None),
                or_(
                    CallLog.deadline_at <= now,
                    CallLog.end_time.is_not(None),
                    (CallLog.provider_started_at.is_(None) & (CallLog.admission_expires_at <= now)),
                ),
            )
            .order_by(CallLog.deadline_at.asc().nulls_first())
            .with_for_update(skip_locked=True)
            .limit(batch_size)
        )
        calls = (await db.scalars(query)).all()
        for call in calls:
            summary = dict(call.telemetry_summary or {})
            reconcile_data = dict(summary.get("reconcile_lease") or {})

            next_retry_str = reconcile_data.get("next_retry_at")
            if next_retry_str:
                try:
                    if datetime.fromisoformat(next_retry_str) > now:
                        continue
                except ValueError:
                    pass

            lease_until_str = reconcile_data.get("lease_until")
            if lease_until_str:
                try:
                    if datetime.fromisoformat(lease_until_str) > now and reconcile_data.get("owner"):
                        continue
                except ValueError:
                    pass

            attempts = reconcile_data.get("attempts", 0) + 1
            reconcile_data["owner"] = worker_id
            reconcile_data["lease_until"] = (now + timedelta(seconds=lease_duration_seconds)).isoformat()
            reconcile_data["attempts"] = attempts
            summary["reconcile_lease"] = reconcile_data
            call.telemetry_summary = summary

            claimed.append({
                "call_id": call.id,
                "org_id": call.org_id,
                "room_name": call.room_name,
                "provider_call_sid": call.provider_call_sid,
                "livekit_cleaned": bool(reconcile_data.get("livekit_cleaned", False)),
                "twilio_cleaned": bool(reconcile_data.get("twilio_cleaned", False)),
                "attempts": attempts,
            })
        await db.commit()
    return claimed


async def reconcile_claimed_call(item: dict, worker_id: str, reason: str = "time_limit") -> bool:
    room = item.get("room_name")
    sid = item.get("provider_call_sid")
    lk_ok = item.get("livekit_cleaned") or await _cleanup_livekit(room)
    tw_ok = item.get("twilio_cleaned") or await _cleanup_twilio(sid)

    async with AsyncSessionLocal() as db:
        call = await db.scalar(
            select(CallLog)
            .where(CallLog.id == item["call_id"], CallLog.org_id == item["org_id"])
            .with_for_update()
        )
        if not call or call.media_terminated_at:
            return True

        summary = dict(call.telemetry_summary or {})
        reconcile_data = dict(summary.get("reconcile_lease") or {})
        if reconcile_data.get("owner") != worker_id:
            logger.warning("Lease ownership lost for call %s during reconciliation", item["call_id"])
            return False

        now = datetime.now(UTC)
        reconcile_data["livekit_cleaned"] = lk_ok
        reconcile_data["twilio_cleaned"] = tw_ok

        if lk_ok and tw_ok:
            call.media_terminated_at = now
            reconcile_data.pop("owner", None)
            reconcile_data.pop("lease_until", None)
            reconcile_data.pop("next_retry_at", None)
            summary["reconcile_lease"] = reconcile_data
            call.telemetry_summary = summary

            if not call.end_time:
                call.end_time = now
                normalized_reason = normalize_call_end_reason(reason).value
                call.end_reason = normalized_reason
                call.duration_seconds = max(0, math.ceil((now - call.provider_started_at).total_seconds())) if call.provider_started_at else 0
                call.call_status = "completed" if call.provider_started_at else "missed"
                if call.recording_status == "processing" and call.recording_storage_path:
                    call.recording_status = "partial"
                if call.call_outcome in {"in_progress", "inquiry", "ringing"}:
                    call.call_outcome = normalized_reason
            await db.commit()
            return True
        else:
            attempts = reconcile_data.get("attempts", 1)
            backoff_seconds = min(300, 2 ** attempts)
            reconcile_data["next_retry_at"] = (now + timedelta(seconds=backoff_seconds)).isoformat()
            reconcile_data.pop("owner", None)
            reconcile_data.pop("lease_until", None)
            summary["reconcile_lease"] = reconcile_data
            call.telemetry_summary = summary
            await db.commit()
            return False


async def terminate_call(call_id, org_id, reason):
    direct_worker_id = f"direct_{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)
    room, sid = None, None
    livekit_cleaned, twilio_cleaned = False, False

    async with AsyncSessionLocal() as db:
        call = await db.scalar(
            select(CallLog)
            .where(CallLog.id == call_id, CallLog.org_id == org_id)
            .with_for_update()
        )
        if not call or call.media_terminated_at:
            return
        summary = dict(call.telemetry_summary or {})
        reconcile_data = dict(summary.get("reconcile_lease") or {})
        lease_until_str = reconcile_data.get("lease_until")
        if lease_until_str:
            try:
                if datetime.fromisoformat(lease_until_str) > now and reconcile_data.get("owner"):
                    return
            except ValueError:
                pass

        reconcile_data["owner"] = direct_worker_id
        reconcile_data["lease_until"] = (now + timedelta(seconds=15)).isoformat()
        summary["reconcile_lease"] = reconcile_data
        call.telemetry_summary = summary
        room, sid = call.room_name, call.provider_call_sid
        livekit_cleaned = bool(reconcile_data.get("livekit_cleaned", False))
        twilio_cleaned = bool(reconcile_data.get("twilio_cleaned", False))
        await db.commit()

    item = {
        "call_id": call_id,
        "org_id": org_id,
        "room_name": room,
        "provider_call_sid": sid,
        "livekit_cleaned": livekit_cleaned,
        "twilio_cleaned": twilio_cleaned,
    }
    await reconcile_claimed_call(item, direct_worker_id, reason)


async def reconcile_calls_once(worker_id: str | None = None) -> int:
    resolved_worker_id = worker_id or f"worker_{uuid.uuid4().hex[:8]}"
    claimed = await claim_reconciliation_batch(resolved_worker_id)
    if not claimed:
        return 0
    tasks = [reconcile_claimed_call(item, resolved_worker_id, CallEndReason.TIME_LIMIT.value) for item in claimed]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return sum(1 for r in results if r is True)


async def reconciliation_loop():
    last_prune = 0.0
    last_retention_sweep = 0.0
    worker_id = f"loop_{uuid.uuid4().hex[:8]}"
    while True:
        try:
            await reconcile_calls_once(worker_id)
            now = asyncio.get_running_loop().time()
            if now - last_prune > 3600:
                from app.services.voice.retention import prune_limit_windows
                await prune_limit_windows()
                last_prune = now
            if now - last_retention_sweep > 86400:
                from app.services.voice.retention import run_daily_retention_sweep
                await run_daily_retention_sweep()
                last_retention_sweep = now
        except Exception:
            logger.exception("Voice reconciliation unavailable")
        await asyncio.sleep(3)
