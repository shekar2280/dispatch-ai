import hashlib
from datetime import datetime, timezone

from fastapi import HTTPException, Request
from sqlalchemy import text

TOKEN_REQUESTS_PER_MINUTE = 10


def client_window(client_host, now):
    return hashlib.sha256(client_host.encode()).hexdigest(), now.astimezone(timezone.utc).replace(second=0, microsecond=0)


async def limit_voice_token_requests(request: Request, db):
    if not request.client:
        raise HTTPException(400, "Client address unavailable")
    now = datetime.now(timezone.utc)
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
