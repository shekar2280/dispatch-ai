import asyncio
import logging
import time
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger(__name__)


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class ProviderHealth:
    provider: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    consecutive_successes: int = 0
    last_failure_time: float = 0.0
    retry_after: float = 60.0
    failure_threshold: int = 2
    recovery_threshold: int = 2


class CircuitBreaker:
    def __init__(self):
        self._providers: dict[str, ProviderHealth] = {}

    def get_health(self, provider: str) -> ProviderHealth:
        if provider not in self._providers:
            self._providers[provider] = ProviderHealth(provider=provider)
        return self._providers[provider]

    def is_available(self, provider: str) -> bool:
        health = self.get_health(provider)
        now = time.monotonic()
        if health.state == CircuitState.CLOSED:
            return True
        if health.state == CircuitState.OPEN:
            if now - health.last_failure_time >= health.retry_after:
                health.state = CircuitState.HALF_OPEN
                return True
            return False
        return True

    async def is_available_async(self, provider: str) -> bool:
        health = self.get_health(provider)
        try:
            from app.services.infra.redis_cache import redis_service
            client = await redis_service.get_client()
            if client:
                key = f"voice:circuit:{provider}"
                data = await client.hgetall(key)
                if data:
                    st = data.get("state", CircuitState.CLOSED.value)
                    if st == CircuitState.CLOSED.value:
                        health.state = CircuitState.CLOSED
                        return True
                    if st == CircuitState.OPEN.value:
                        last_fail = float(data.get("last_failure_time", 0.0))
                        retry_after = float(data.get("retry_after", 60.0))
                        if time.time() - last_fail >= retry_after and data.get("half_open_probed") != "1":
                            await client.hset(key, mapping={"half_open_probed": "1", "state": CircuitState.HALF_OPEN.value})
                            health.state = CircuitState.HALF_OPEN
                            return True
                        health.state = CircuitState.OPEN
                        return False
                    if st == CircuitState.HALF_OPEN.value:
                        return False
        except Exception:
            pass
        return self.is_available(provider)

    def record_success(self, provider: str):
        health = self.get_health(provider)
        if health.state == CircuitState.HALF_OPEN:
            health.consecutive_successes += 1
            if health.consecutive_successes >= health.recovery_threshold:
                health.state = CircuitState.CLOSED
                health.failure_count = 0
                health.consecutive_successes = 0
        elif health.state == CircuitState.CLOSED:
            health.failure_count = 0
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.record_success_async(provider))
        except RuntimeError:
            pass

    async def record_success_async(self, provider: str):
        health = self.get_health(provider)
        if health.state == CircuitState.HALF_OPEN:
            health.consecutive_successes += 1
            if health.consecutive_successes >= health.recovery_threshold:
                health.state = CircuitState.CLOSED
                health.failure_count = 0
                health.consecutive_successes = 0
        elif health.state == CircuitState.CLOSED:
            health.failure_count = 0
        try:
            from app.services.infra.redis_cache import redis_service
            client = await redis_service.get_client()
            if client:
                key = f"voice:circuit:{provider}"
                await client.delete(key)
        except Exception:
            pass

    def record_failure(self, provider: str, status_code: int | None = None, retry_after: float | None = None):
        health = self.get_health(provider)
        health.last_failure_time = time.monotonic()
        health.retry_after = float(retry_after) if retry_after is not None else 60.0
        health.failure_count += 1
        health.consecutive_successes = 0
        if status_code == 429 or health.failure_count >= health.failure_threshold:
            health.state = CircuitState.OPEN
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.record_failure_async(provider, status_code=status_code, retry_after=retry_after))
        except RuntimeError:
            pass

    async def record_failure_async(self, provider: str, status_code: int | None = None, retry_after: float | None = None):
        health = self.get_health(provider)
        health.last_failure_time = time.monotonic()
        effective_retry = float(retry_after) if retry_after is not None else 60.0
        health.retry_after = effective_retry
        health.failure_count += 1
        health.consecutive_successes = 0
        should_open = status_code == 429 or health.failure_count >= health.failure_threshold
        if should_open:
            health.state = CircuitState.OPEN
        try:
            from app.services.infra.redis_cache import redis_service
            client = await redis_service.get_client()
            if client:
                key = f"voice:circuit:{provider}"
                now_epoch = time.time()
                mapping = {
                    "state": CircuitState.OPEN.value if should_open else CircuitState.CLOSED.value,
                    "failure_count": str(health.failure_count),
                    "last_failure_time": str(now_epoch),
                    "retry_after": str(effective_retry),
                    "half_open_probed": "0",
                }
                await client.hset(key, mapping=mapping)
                await client.expire(key, int(effective_retry) + 120)
        except Exception:
            pass


circuit_breaker = CircuitBreaker()
