import logging
import re
import time
import uuid
import asyncio
from contextlib import suppress

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.router import api_router

from contextlib import asynccontextmanager
from app.services.appointments.booking_service import booking_queue
from app.services.voice.call_logger_service import (
    start_turn_flush_worker,
    stop_turn_flush_worker,
)
from app.core.logging_config import configure_logging

configure_logging()
logger = logging.getLogger("app.http")


@asynccontextmanager
async def lifespan(app: FastAPI):
    booking_queue.start_worker()
    await start_turn_flush_worker()
    from app.services.voice.lifecycle import reconciliation_loop
    reconciliation = asyncio.create_task(reconciliation_loop())
    try:
        yield
    finally:
        reconciliation.cancel()
        with suppress(asyncio.CancelledError):
            await reconciliation
        await stop_turn_flush_worker()


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = request.headers.get("x-request-id", "")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", request_id):
        request_id = uuid.uuid4().hex
    request.state.request_id = request_id
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled_request_exception", extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
        })
        response = JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
        )
    response.headers["X-Request-ID"] = request_id
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    extra = {
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "duration_ms": elapsed,
    }
    if response.status_code >= 500:
        logger.error("request_failed", extra=extra)
    elif response.status_code >= 400:
        logger.warning("request_rejected", extra=extra)
    else:
        logger.info("request_completed", extra=extra)
    return response

origins = list(settings.ALLOWED_ORIGINS)
if getattr(settings, "CORS_ORIGINS", None):
    extra = settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else [settings.CORS_ORIGINS]
    for o in extra:
        if o and o not in origins:
            origins.append(o)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "triage_gate": "active",
    }


if settings.ENVIRONMENT == "development":
    @app.get("/debug-routes")
    async def debug_routes():
        return [
            {"path": r.path, "name": getattr(r, "name", None), "type": type(r).__name__}
            for r in app.routes
        ]
