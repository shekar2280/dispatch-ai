"""Regression tests for voice providers."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.clinic.tools import ClinicVoiceAgent
from app.services.voice.diagnostics import ErrorCategory, classify_provider_error, sanitize_error_message


@pytest.mark.asyncio
async def test_llm_node_yields_apology_on_initial_error():
    agent = ClinicVoiceAgent(system_prompt="Test prompt")
    chat_ctx = MagicMock()
    chat_ctx.to_dict.return_value = {"messages": []}

    with patch("livekit.agents.voice.Agent.default.llm_node") as mock_node:

        async def failing_node(*args, **kwargs):
            raise RuntimeError("API connection failed")
            yield "chunk"

        mock_node.side_effect = failing_node
        with patch("app.services.voice.provider_budget.reserve_llm", new_callable=AsyncMock):
            chunks = []
            async for chunk in agent.llm_node(chat_ctx, [], None):
                chunks.append(chunk)
            assert len(chunks) == 1
            assert "Pardon me" in chunks[0]
            assert agent.state["service_unavailable"] is True


@pytest.mark.asyncio
async def test_tts_node_catches_synthesis_failure():
    agent = ClinicVoiceAgent(system_prompt="Test prompt")
    with patch("livekit.agents.voice.Agent.default.tts_node") as mock_tts:

        async def failing_tts(*args, **kwargs):
            raise RuntimeError("TTS connection dropped")
            yield b"frame"

        mock_tts.side_effect = failing_tts
        with patch("app.services.voice.provider_budget.reserve_budget", new_callable=AsyncMock):

            async def text_gen():
                yield "Hello there"

            frames = []
            async for frame in agent.tts_node(text_gen(), None):
                frames.append(frame)
            assert len(frames) == 0
            assert agent.state["service_unavailable"] is True


class DummyUnderlying(Exception):
    def __init__(self, message, status_code=None, request_id=None, retry_after=None):
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id
        self.retry_after = retry_after


class DummyWrapper(Exception):
    def __init__(self, error):
        super().__init__(str(error))
        self.error = error


def test_sanitize_error_message_redacts_credentials():
    raw = "Failed with key AIzaSyDfakeKey1234567890abcdefghijklm and secret dg_0123456789abcdef0123456789abcdef01234567"
    cleaned = sanitize_error_message(raw)
    assert "AIza" not in cleaned
    assert "dg_" not in cleaned
    assert "[REDACTED_KEY]" in cleaned


def test_sanitize_error_message_redacts_phone_and_email():
    raw = "User john.doe@example.com with phone +15551234567 failed"
    cleaned = sanitize_error_message(raw)
    assert "john.doe@example.com" not in cleaned
    assert "+15551234567" not in cleaned
    assert "[REDACTED_EMAIL]" in cleaned
    assert "[REDACTED_PHONE]" in cleaned


@pytest.mark.parametrize(
    "raw,secret",
    [
        ("https://provider.example/generate?key=private-query-value&alt=sse", "private-query-value"),
        ('{"api_key": "private-json-value"}', "private-json-value"),
        ("postgresql://user:private-db-value@localhost/db", "private-db-value"),
        ("Bearer private-token-with-padding==", "private-token-with-padding"),
    ],
)
def test_sanitize_error_message_removes_credentials_in_provider_errors(raw, secret):
    assert secret not in sanitize_error_message(raw)


def test_classify_transient_network_timeout():
    err = DummyWrapper(
        DummyUnderlying("Connection to api.deepgram.com timed out", status_code=504, request_id="req-123")
    )
    result = classify_provider_error(err)
    assert result.category == ErrorCategory.TRANSIENT_NETWORK
    assert result.recoverable is True
    assert result.status_code == 504
    assert result.request_id == "req-123"
    assert result.wrapper_type == "DummyWrapper"
    assert result.underlying_type == "DummyUnderlying"


def test_classify_rate_limited_with_retry_after():
    err = DummyWrapper(DummyUnderlying("Rate limit exceeded", status_code=429, retry_after=1.5))
    result = classify_provider_error(err)
    assert result.category == ErrorCategory.RATE_LIMITED
    assert result.recoverable is True
    assert result.retry_after == 1.5

    err_high = DummyWrapper(DummyUnderlying("Quota exhausted for the day", status_code=429, retry_after=60.0))
    result_high = classify_provider_error(err_high)
    assert result_high.category == ErrorCategory.RATE_LIMITED
    assert result_high.recoverable is False


def test_classify_authentication_error():
    err = DummyWrapper(DummyUnderlying("Invalid API key provided", status_code=401))
    result = classify_provider_error(err)
    assert result.category == ErrorCategory.AUTHENTICATION
    assert result.recoverable is False


def test_classify_invalid_argument_schema():
    err = DummyWrapper(DummyUnderlying("Invalid tool schema provided to model", status_code=400))
    result = classify_provider_error(err)
    assert result.category == ErrorCategory.INVALID_ARGUMENT
    assert result.recoverable is False


def test_classify_asyncio_cancelled():
    err = DummyWrapper(asyncio.CancelledError())
    result = classify_provider_error(err)
    assert result.category == ErrorCategory.CANCELED
    assert result.recoverable is False


def test_classify_no_response_generated_is_recoverable():
    class LiveKitAPIStatusError(Exception):
        def __init__(self, message, status_code=-1, retryable=True):
            super().__init__(message)
            self.status_code = status_code
            self.retryable = retryable

    err = DummyWrapper(LiveKitAPIStatusError("no response generated", status_code=-1, retryable=True))
    result = classify_provider_error(err)
    assert result.category == ErrorCategory.TRANSIENT_NETWORK
    assert result.recoverable is True


def test_classify_substring_rate_not_misidentified():
    err = DummyWrapper(DummyUnderlying("accurate response generated successfully"))
    result = classify_provider_error(err)
    assert result.category != ErrorCategory.RATE_LIMITED


def test_circuit_breaker_transitions_to_open_on_429():
    from app.services.voice.circuit_breaker import CircuitBreaker, CircuitState

    cb = CircuitBreaker()
    assert cb.is_available("groq") is True

    cb.record_failure("groq", status_code=429, retry_after=30.0)
    health = cb.get_health("groq")
    assert health.state == CircuitState.OPEN
    assert cb.is_available("groq") is False


def test_provider_router_falls_back_when_groq_is_open(monkeypatch):
    from app.services.voice.circuit_breaker import circuit_breaker
    from app.services.voice.provider_router import ProviderRouter
    from app.core.config import settings

    monkeypatch.setattr(settings, "PRIMARY_LLM_PROVIDER", "groq")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-groq-key")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-gemini-key")

    router = ProviderRouter(primary_provider="groq")
    circuit_breaker.get_health("groq").state = circuit_breaker.get_health("groq").state.__class__.CLOSED
    circuit_breaker.get_health("gemini").state = circuit_breaker.get_health("gemini").state.__class__.CLOSED

    initial_route = router.select_route()
    assert initial_route.provider == "groq"
    assert initial_route.is_fallback is False

    circuit_breaker.record_failure("groq", status_code=429, retry_after=60.0)
    fallback_route = router.select_route()
    assert fallback_route.provider == "gemini"
    assert fallback_route.is_fallback is True
    assert fallback_route.degraded is False

    circuit_breaker.get_health("groq").state = circuit_breaker.get_health("groq").state.__class__.CLOSED


def test_circuit_breaker_recovers_after_successes():
    from app.services.voice.circuit_breaker import CircuitBreaker, CircuitState

    cb = CircuitBreaker()
    cb.record_failure("groq", status_code=429, retry_after=0.01)
    health = cb.get_health("groq")
    assert health.state == CircuitState.OPEN

    health.last_failure_time -= 1.0
    assert cb.is_available("groq") is True
    assert health.state == CircuitState.HALF_OPEN

    cb.record_success("groq")
    cb.record_success("groq")
    assert health.state == CircuitState.CLOSED
