"""Read-only schema/config readiness check. Never prints credentials."""
import asyncio
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from app.core.config import settings
from app.core.database import AsyncSessionLocal

REQUIRED = {
    "organizations": {"voice_seconds_used", "inbound_voice_number"},
    "call_logs": {"caller_identity", "provider_call_sid", "provider_started_at", "deadline_at",
                  "admission_expires_at", "quota_charged_at", "charged_seconds", "media_terminated_at",
                  "booking_proposal", "booking_result", "telemetry_summary", "call_budget_seconds"},
    "voice_call_turns": {"event_id", "interrupted", "speech_id"},
    "voice_token_rate_limits": {"tokens"},
    "appointments": {"booking_metadata", "queue_state", "encounter_state", "called_at", "call_count"},
}


async def check():
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(text("select table_name,column_name from information_schema.columns where table_schema='public'"))).all()
        columns = {}
        for table, column in rows:
            columns.setdefault(table, set()).add(column)
        missing = {table: sorted(required-columns.get(table, set())) for table, required in REQUIRED.items()
                   if required-columns.get(table, set())}
        triggers = set((await db.execute(text("select tgname from pg_trigger where not tgisinternal"))).scalars().all())
    result = {"missing_columns": missing,
        "missing_triggers": sorted({"settle_voice_allowance", "protect_active_voice_call", "validate_voice_booking_call"}-triggers),
        "configured": {key: bool(getattr(settings, key)) for key in
                       ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "GEMINI_API_KEY", "DEEPGRAM_API_KEY")},
        "model": settings.GEMINI_MODEL,
        "gemini_limits": {"rpm": settings.VOICE_GEMINI_RPM, "tpm": settings.VOICE_GEMINI_TPM, "rpd": settings.VOICE_GEMINI_RPD}}
    print(json.dumps(result, indent=2))
    return 1 if missing or result["missing_triggers"] or not all(result["configured"].values()) else 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(check()))
    except Exception as exc:
        print(json.dumps({"status": "unavailable", "error_type": type(exc).__name__}))
        raise SystemExit(1)
