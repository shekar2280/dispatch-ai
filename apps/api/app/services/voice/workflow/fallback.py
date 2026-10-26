import logging
from typing import Any
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)


async def generate_conversational_fallback(
    utterance: str,
    clinic_name: str = "the clinic",
    consecutive_failures: int = 0,
) -> str:
    if consecutive_failures >= 2:
        return "I want to ensure you get the right assistance. Would you like me to connect you with our reception team?"
    if settings.PRIMARY_LLM_PROVIDER == "groq" and settings.GROQ_API_KEY:
        reply = await _groq_fallback(utterance, clinic_name)
        if reply:
            return reply
    if settings.GEMINI_API_KEY:
        reply = await _gemini_fallback(utterance, clinic_name)
        if reply:
            return reply
    return f"I can help you check appointment availability, directions, or office hours for {clinic_name}. What would you like to know?"


async def _groq_fallback(utterance: str, clinic_name: str) -> str | None:
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    system_msg = f"You are the receptionist for {clinic_name}. Speak in 1-2 polite sentences. Do not invent medical advice or prices."
    payload = {
        "model": settings.GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": utterance},
        ],
        "max_tokens": 80,
        "temperature": 0.2,
    }
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                body = resp.json()
                return body["choices"][0]["message"]["content"].strip()
    except Exception:
        logger.exception("Groq fallback generation failed")
    return None


async def _gemini_fallback(utterance: str, clinic_name: str) -> str | None:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    prompt = f"You are the receptionist for {clinic_name}. Speak in 1-2 polite sentences without diagnosing or prescribing.\nCaller: {utterance}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 80},
    }
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                body = resp.json()
                return body["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        logger.exception("Gemini fallback generation failed")
    return None
