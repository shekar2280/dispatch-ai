import re
from typing import Optional, AsyncGenerator
import httpx


def clean_speech_text_for_tts(text: str) -> str:
    cleaned = re.sub(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):\d{2}", r"\4:\5", text)
    cleaned = re.sub(r"(\d{2}):(\d{2}):\d{2}", r"\1:\2", cleaned)
    cleaned = cleaned.replace("Done!", "Great!").replace("done!", "great!")
    return cleaned.strip()


async def _synthesize_deepgram_audio(clean_text: str, model_id: str, api_key: str) -> Optional[bytes]:
    url = f"https://api.deepgram.com/v2/speak?model={model_id}" if model_id.startswith("flux-") else f"https://api.deepgram.com/v1/speak?model={model_id}"
    headers = {
        "Authorization": f"Token {api_key.strip()}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, headers=headers, json={"text": clean_text})
            if res.status_code == 200 and len(res.content) > 100:
                return res.content
    except Exception:
        pass
    return None


_tts_cache: dict[str, bytes] = {}
_TTS_CACHE_LIMIT = 256


def _cache_speech(cache_key: str, audio_bytes: bytes) -> None:
    _tts_cache.pop(cache_key, None)
    _tts_cache[cache_key] = audio_bytes
    while len(_tts_cache) > _TTS_CACHE_LIMIT:
        _tts_cache.pop(next(iter(_tts_cache)))


SUPPORTED_VOICE_CATALOG = [
    {
        "id": "aura-asteria-en",
        "name": "Asteria",
        "provider": "deepgram",
        "model": "aura",
        "gender": "female",
        "accent": "US English",
        "description": "Clear, professional, and conversational tone ideal for healthcare reception.",
        "sample_phrase": "Hello! Welcome to {clinic_name}. How can I help you today?",
    },
    {
        "id": "aura-luna-en",
        "name": "Luna",
        "provider": "deepgram",
        "model": "aura",
        "gender": "female",
        "accent": "US English",
        "description": "Calm, gentle, and empathetic cadence suitable for family care and pediatrics.",
        "sample_phrase": "Hello, thank you for calling {clinic_name}. How may I assist you today?",
    },
    {
        "id": "aura-athena-en",
        "name": "Athena",
        "provider": "deepgram",
        "model": "aura",
        "gender": "female",
        "accent": "UK English",
        "description": "Crisp, articulate, and formal voice tailored for specialist clinics.",
        "sample_phrase": "Good day, you have reached {clinic_name}. How may I assist you today?",
    },
    {
        "id": "aura-arcas-en",
        "name": "Arcas",
        "provider": "deepgram",
        "model": "aura",
        "gender": "male",
        "accent": "US English",
        "description": "Natural, confident, and approachable tone for general practice scheduling.",
        "sample_phrase": "Hello and welcome to {clinic_name}. I can help you schedule or manage an appointment.",
    },
    {
        "id": "aura-zeus-en",
        "name": "Zeus",
        "provider": "deepgram",
        "model": "aura",
        "gender": "male",
        "accent": "US English",
        "description": "Deep, authoritative, and steady voice for busy clinical centers.",
        "sample_phrase": "Thank you for calling {clinic_name}. Please let me know how I can help you today.",
    },
    {
        "id": "aura-stella-en",
        "name": "Stella",
        "provider": "deepgram",
        "model": "aura",
        "gender": "female",
        "accent": "US English",
        "description": "Bright, energetic, and engaging voice tailored for rapid triage.",
        "sample_phrase": "Hi there! Welcome to {clinic_name}. How can I assist you today?",
    },
    {
        "id": "aura-helios-en",
        "name": "Helios",
        "provider": "deepgram",
        "model": "aura",
        "gender": "male",
        "accent": "UK English",
        "description": "Polished, warm British English voice with composed demeanor.",
        "sample_phrase": "Good day, thank you for contacting {clinic_name}. How may I help you today?",
    },
]

VOICE_ALIASES = {
    "priya": "aura-asteria-en",
    "aria": "aura-asteria-en",
    "gemini-aoede": "aura-asteria-en",
    "meena": "aura-luna-en",
    "kavya": "aura-athena-en",
    "gemini-kore": "aura-athena-en",
    "rohan": "aura-arcas-en",
    "naveen": "aura-arcas-en",
    "gemini-puck": "aura-arcas-en",
    "zeus": "aura-zeus-en",
    "stella": "aura-stella-en",
    "helios": "aura-helios-en",
}

SUPPORTED_VOICE_IDS = {item["id"] for item in SUPPORTED_VOICE_CATALOG}


def resolve_voice(voice_id, strict: bool = False):
    value = (voice_id or "aura-asteria-en").lower().strip()
    resolved = VOICE_ALIASES.get(value, value)
    if resolved in SUPPORTED_VOICE_IDS:
        return resolved
    if strict:
        raise ValueError(f"Unsupported voice ID: {voice_id}")
    return "aura-asteria-en"


async def generate_voice_speech(text: str, voice_id=None, output_format="mp3_44100_128") -> bytes:
    from app.core.config import settings
    from app.services.voice.provider_budget import reserve_budget
    clean_text = clean_speech_text_for_tts(text)
    if not 1 <= len(clean_text) <= 400:
        raise ValueError("Voice previews must contain 1 to 400 characters")
    voice = resolve_voice(voice_id)
    cache_key = f"{voice}:{clean_text}"
    if cache_key in _tts_cache:
        return _tts_cache[cache_key]
    await reserve_budget("deepgram-preview", len(clean_text), rpm=settings.VOICE_PREVIEW_RPM)
    await reserve_budget("deepgram-tts-characters", len(clean_text), daily_units=settings.VOICE_TTS_DAILY_CHARACTERS)
    audio = await _synthesize_deepgram_audio(clean_text, voice, settings.DEEPGRAM_API_KEY)
    if not audio:
        raise RuntimeError("Voice preview unavailable")
    _cache_speech(cache_key, audio)
    return audio


async def generate_voice_speech_stream(
    sentence_generator: AsyncGenerator[str, None], voice_id: Optional[str] = None
) -> AsyncGenerator[bytes, None]:
    async for sentence in sentence_generator:
        if sentence and sentence.strip():
            audio_bytes = await generate_voice_speech(sentence, voice_id=voice_id)
            if audio_bytes:
                yield audio_bytes


async def semantic_text_chunker(
    text_token_generator: AsyncGenerator[str, None], max_words: int = 12
) -> AsyncGenerator[str, None]:
    buffer = ""
    delimiters = {".", ",", ";", "?", "!", "\n", "-"}

    async for token in text_token_generator:
        buffer += token
        words = buffer.strip().split()

        has_delimiter = any(d in token for d in delimiters)
        if (has_delimiter and len(words) >= 3) or len(words) >= max_words:
            yield buffer.strip()
            buffer = ""

    if buffer.strip():
        yield buffer.strip()
