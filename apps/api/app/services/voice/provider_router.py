from dataclasses import dataclass

from app.core.config import settings
from app.services.voice.circuit_breaker import circuit_breaker


@dataclass(frozen=True)
class ProviderRoute:
    provider: str
    model: str
    api_key: str
    is_fallback: bool
    degraded: bool


class ProviderRouter:
    def __init__(self, primary_provider: str | None = None):
        self.primary_provider = primary_provider or settings.PRIMARY_LLM_PROVIDER

    def select_route(self) -> ProviderRoute:
        if self.primary_provider == "groq" and settings.GROQ_API_KEY and circuit_breaker.is_available("groq"):
            return ProviderRoute(
                provider="groq",
                model=settings.GROQ_MODEL,
                api_key=settings.GROQ_API_KEY,
                is_fallback=False,
                degraded=False,
            )
        if settings.GEMINI_API_KEY and circuit_breaker.is_available("gemini"):
            return ProviderRoute(
                provider="gemini",
                model=settings.GEMINI_MODEL,
                api_key=settings.GEMINI_API_KEY,
                is_fallback=self.primary_provider != "gemini",
                degraded=False,
            )
        return ProviderRoute(
            provider="degraded",
            model="",
            api_key="",
            is_fallback=True,
            degraded=True,
        )

    async def select_route_async(self) -> ProviderRoute:
        if self.primary_provider == "groq" and settings.GROQ_API_KEY and await circuit_breaker.is_available_async("groq"):
            return ProviderRoute(
                provider="groq",
                model=settings.GROQ_MODEL,
                api_key=settings.GROQ_API_KEY,
                is_fallback=False,
                degraded=False,
            )
        if settings.GEMINI_API_KEY and await circuit_breaker.is_available_async("gemini"):
            return ProviderRoute(
                provider="gemini",
                model=settings.GEMINI_MODEL,
                api_key=settings.GEMINI_API_KEY,
                is_fallback=self.primary_provider != "gemini",
                degraded=False,
            )
        return ProviderRoute(
            provider="degraded",
            model="",
            api_key="",
            is_fallback=True,
            degraded=True,
        )


provider_router = ProviderRouter()
