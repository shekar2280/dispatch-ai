import os
from typing import List, Union, Optional
from pydantic import BeforeValidator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing_extensions import Annotated


def parse_origins(v: Union[str, List[str]]) -> List[str]:
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
        Union[List[str], str], BeforeValidator(parse_origins)
    ] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    CORS_ORIGINS: Optional[Union[List[str], str]] = None

    NEXT_PUBLIC_SUPABASE_URL: str = ""
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: str = ""
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    ADMIN_SECRET_KEY: str = ""

    PRIMARY_LLM_PROVIDER: str = "gemini"
    VOICE_ENABLED: bool = True
    VOICE_GLOBAL_CONCURRENCY: int = Field(default=1, ge=1, le=5)
    VOICE_GLOBAL_DAILY_SECONDS: int = Field(default=1800, ge=1)
    VOICE_ADMISSION_TTL_SECONDS: int = Field(default=45, ge=15, le=180)
    VOICE_MAX_CALL_SECONDS: int = Field(default=120, ge=1, le=120)
    VOICE_GEMINI_RPM: int = 15
    VOICE_GEMINI_TPM: int = 250000
    VOICE_GEMINI_RPD: int = 500
    VOICE_LLM_MAX_OUTPUT_TOKENS: int = Field(default=256, ge=64, le=512)
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

    REDIS_URL: Optional[str] = None

    DATABASE_URL: str = ""

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=None if os.environ.get("ENVIRONMENT") == "test" else ".env",
        extra="allow",
    )


settings = Settings()
