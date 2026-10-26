import json
import logging
import re
from typing import Any
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)


def parse_extracted_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    cleaned = text.strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None


async def extract_booking_entities(
    utterance: str,
    provider: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> dict[str, Any] | None:
    selected_provider = provider or settings.PRIMARY_LLM_PROVIDER
    if selected_provider == "groq" and (api_key or settings.GROQ_API_KEY):
        return await _extract_groq(utterance, api_key or settings.GROQ_API_KEY, model or settings.GROQ_MODEL)
    if api_key or settings.GEMINI_API_KEY:
        return await _extract_gemini(utterance, api_key or settings.GEMINI_API_KEY, model or settings.GEMINI_MODEL)
    return None


async def _extract_groq(utterance: str, api_key: str, model: str) -> dict[str, Any] | None:
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Extract booking entities as JSON with keys: doctor, date, time, name, intent. Return ONLY valid JSON.",
            },
            {"role": "user", "content": utterance},
        ],
        "max_tokens": 64,
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                body = resp.json()
                raw = body["choices"][0]["message"]["content"]
                return parse_extracted_json(raw)
    except Exception:
        logger.exception("Groq compact extractor failed")
    return None


async def _extract_gemini(utterance: str, api_key: str, model: str) -> dict[str, Any] | None:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    prompt = f"Extract booking entities from this utterance as JSON with keys: doctor, date, time, name, intent. Return ONLY valid JSON.\nUtterance: {utterance}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 64, "responseMimeType": "application/json"},
    }
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                body = resp.json()
                raw = body["candidates"][0]["content"]["parts"][0]["text"]
                return parse_extracted_json(raw)
    except Exception:
        logger.exception("Gemini compact extractor failed")
    return None
