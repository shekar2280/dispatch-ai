import os
from typing import Annotated

from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def parse_origins(v: str | list[str]) -> list[str]:
    if isinstance(v, str):
        v = v.strip()
        if not v:
            return []
        if v.startswith("[") and v.endswith("]"):
            try:
                import json

                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [
                        str(i).strip().strip("'\"")
                        for i in parsed
                        if str(i).strip().strip("'\"")
                    ]
            except Exception:
                pass
        return [i.strip().strip("'\"") for i in v.split(",") if i.strip().strip("'\"")]
    return v


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    PROJECT_NAME: str = "DispatchAI"
    API_V1_STR: str = "/api/v1"
    ALLOWED_ORIGINS: Annotated[
        list[str] | str, BeforeValidator(parse_origins)
    ] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    CORS_ORIGINS: list[str] | str | None = None

    NEXT_PUBLIC_SUPABASE_URL: str = ""
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: str = ""
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    ADMIN_SECRET_KEY: str = ""

    PRIMARY_LLM_PROVIDER: str = "groq"
    VOICE_ENABLED: bool = True
    VOICE_GLOBAL_CONCURRENCY: int = Field(default=1, ge=1, le=5)
    VOICE_GLOBAL_DAILY_SECONDS: int = Field(default=1800, ge=1)
    VOICE_ADMISSION_TTL_SECONDS: int = Field(default=45, ge=15, le=180)
    VOICE_MAX_CALL_SECONDS: int = Field(default=120, ge=1, le=120)
    VOICE_GEMINI_RPM: int = 15
    VOICE_GEMINI_TPM: int = 250000
    VOICE_GEMINI_RPD: int = 500
    VOICE_GROQ_RPM: int = Field(default=30, ge=1)
    VOICE_GROQ_TPM: int = Field(default=30000, ge=1)
    VOICE_GROQ_RPD: int = Field(default=1000, ge=1)
    VOICE_GROQ_MAX_COMPLETION_TOKENS: int = Field(default=128, ge=32, le=512)
    VOICE_GROQ_REASONING_EFFORT: str = "low"
    VOICE_LLM_MAX_OUTPUT_TOKENS: int = Field(default=128, ge=32, le=512)
    VOICE_LLM_MAX_HISTORY_TURNS: int = Field(default=4, ge=0, le=12)
    VOICE_TTS_DAILY_CHARACTERS: int = Field(default=100000, ge=1)
    VOICE_PREVIEW_RPM: int = Field(default=3, ge=1)
    VOICE_STT_MODEL: str = "nova-3"
    VOICE_STT_LANGUAGE: str = "en-US"
    VOICE_AUDIO_RETENTION_DAYS: int = Field(default=7, ge=1)
    VOICE_TRANSCRIPT_RETENTION_DAYS: int = Field(default=30, ge=1)
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    GEMINI_FALLBACK_MODEL: str = "gemini-3.1-flash-lite"
    GROQ_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    ELEVEN_LABS_API_KEY: str = ""
    ELEVENLABS_API_KEY: str = ""
    ELEVENLABS_VOICE_ID: str = ""
    DEEPGRAM_API_KEY: str = ""

    NGROK_AUTHTOKEN: str = ""
    NGROK_DOMAIN: str = ""

    LIVEKIT_URL: str = ""
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""

    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""
    LIVEKIT_SIP_DOMAIN: str = "sip.livekit.cloud"

    REDIS_URL: str | None = None

    DATABASE_URL: str = ""
    DATABASE_POOL_SIZE: int = Field(default=10, ge=1)
    DATABASE_MAX_OVERFLOW: int = Field(default=5, ge=0)
    DATABASE_POOL_TIMEOUT: float = Field(default=10.0, ge=1.0)
    DATABASE_POOL_RECYCLE: int = Field(default=300, ge=60)
    DATABASE_POOL_PRE_PING: bool = True

    VOICE_MAX_CONCURRENT_CALLS_PER_ORG: int = Field(default=50, ge=1)
    VOICE_MAX_CONCURRENT_CALLS_GLOBAL: int = Field(default=500, ge=1)
    VOICE_RECOVERY_ENABLED: bool = True
    VOICE_ROLLOUT_STAGE: str = "active"
    VOICE_ROLLOUT_PERCENTAGE: int = Field(default=100, ge=0, le=100)

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=None if os.environ.get("ENVIRONMENT") == "test" else ".env",
        extra="allow",
    )


settings = Settings()
