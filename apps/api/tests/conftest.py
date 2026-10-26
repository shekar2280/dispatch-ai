"""Keep test collection independent of developer credentials and services."""

import os

import pytest

LIVE_SERVICES_ENABLED = os.environ.get("RUN_LIVE_TESTS") == "1"
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = (
    os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1:1/dispatch_tests")
    if LIVE_SERVICES_ENABLED
    else "postgresql+asyncpg://test:test@127.0.0.1:1/dispatch_tests"
)

if not LIVE_SERVICES_ENABLED:
    for name in list(os.environ):
        if any(part in name for part in ("SUPABASE", "LIVEKIT", "TWILIO", "GROQ", "GEMINI", "DEEPGRAM", "ELEVEN")):
            os.environ.pop(name)
    os.environ.update(
        ADMIN_SECRET_KEY="",
        REDIS_URL="redis://127.0.0.1:1/0",
    )

from app.core.config import settings

if not LIVE_SERVICES_ENABLED:
    for name in type(settings).model_fields:
        if any(
            part in name
            for part in ("API_KEY", "API_SECRET", "AUTH_TOKEN", "SERVICE_ROLE", "ADMIN_SECRET", "SUPABASE_URL")
        ):
            setattr(settings, name, "")
    settings.LIVEKIT_API_KEY = "unit-test-key"
    settings.LIVEKIT_API_SECRET = "unit-test-secret-with-at-least-32-characters"


def pytest_collection_modifyitems(items):
    if not LIVE_SERVICES_ENABLED:
        skip = pytest.mark.skip(reason="Set RUN_LIVE_TESTS=1 and configure an isolated staging environment")
        for item in items:
            if item.get_closest_marker("live"):
                item.add_marker(skip)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def block_unexpected_network(request, monkeypatch):
    if request.node.get_closest_marker("live") or request.node.get_closest_marker("voice_db"):
        return
    import socket
    import sys

    original_connect = socket.socket.connect

    def connect(sock, address):
        if sys._getframe(1).f_code.co_name == "_fallback_socketpair" and address[0] in {"127.0.0.1", "::1"}:
            return original_connect(sock, address)
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise RuntimeError("Unit tests must mock network connections; use a marked integration test")
        return original_connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
