"""Streaming completions and structured responses with provider fallback."""

import logging
import asyncio
import json
import httpx
import re
import ast
from typing import Dict, Any, Optional, List, AsyncGenerator
from datetime import datetime
from app.core.config import settings

logger = logging.getLogger(__name__)

PRIMARY_MODELS = [settings.GEMINI_MODEL]


async def _reserve_gemini(payload):
    from app.services.voice.provider_budget import reserve_llm
    await reserve_llm(len(json.dumps(payload, default=str).encode()))


async def _gemini_post(client, url, payload, headers):
    await _reserve_gemini(payload)
    return await client.post(url, json=payload, headers=headers)


async def stream_agentic_response(
    system_prompt: str,
    conversation_history: List[Dict[str, str]],
    db: Any,
    org_id: Any,
    temperature: float = 0.5,
    max_tokens: int = 400,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Stream model output and execute requested clinic tools.
    Streams text tokens directly from Groq/Gemini.
    If the LLM emits a tool_call frame, pauses stream, executes backend tool,
    appends result to conversation history, and re-prompts the LLM.
    """
    from app.services.voice.tool_execution_service import (
        generate_dynamic_voice_tools,
        execute_tool_call,
    )
    from app.models.organization import Organization
    from sqlalchemy.future import select

    required_fields = None
    try:
        org_res = await db.execute(
            select(Organization).where(Organization.id == org_id)
        )
        org_obj = org_res.scalar_one_or_none()
        if org_obj:
            required_fields = getattr(org_obj, "required_booking_fields", None)
    except Exception as e:
        try:
            await db.rollback()
        except Exception:
            pass

    dynamic_tools = generate_dynamic_voice_tools(required_fields)

    groq_key = settings.GROQ_API_KEY
    messages = [{"role": "system", "content": system_prompt}]
    for h in conversation_history:
        role = "assistant" if h.get("role") in ["model", "assistant"] else "user"
        text_val = h.get("content") or h.get("text") or ""
        if text_val:
            messages.append({"role": role, "content": text_val})

    providers = []
    if settings.GEMINI_API_KEY:
        providers.append(
            {
                "name": "Gemini 3.5 Flash Lite",
                "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                "headers": {
                    "Authorization": f"Bearer {settings.GEMINI_API_KEY}",
                    "Content-Type": "application/json",
                },
                "model": settings.GEMINI_MODEL,
            }
        )
    if settings.GROQ_API_KEY:
        providers.append(
            {
                "name": "Groq Llama-3.3",
                "url": "https://api.groq.com/openai/v1/chat/completions",
                "headers": {
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                "model": "llama-3.3-70b-versatile",
            }
        )

    for provider in providers:
        p_name = provider["name"]
        url = provider["url"]
        headers = provider["headers"]
        model_name = provider["model"]

        payload = {
            "model": model_name,
            "messages": messages,
            "tools": dynamic_tools,
            "tool_choice": "auto",
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            tool_calls_requested = []
            async with httpx.AsyncClient(timeout=10.0) as client:
                if "generativelanguage.googleapis.com" in url:
                    await _reserve_gemini(payload)
                async with client.stream(
                    "POST", url, headers=headers, json=payload
                ) as response:
                    if response.status_code == 200:
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                data_str = line[6:].strip()
                                if data_str == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data_str)
                                    if not chunk.get("choices"):
                                        continue
                                    delta = chunk["choices"][0].get("delta", {})

                                    content_text = delta.get("content")
                                    if content_text:
                                        yield {"type": "token", "content": content_text}

                                    tc_delta = delta.get("tool_calls")
                                    if tc_delta:
                                        for tc in tc_delta:
                                            index = tc.get("index", 0)
                                            while len(tool_calls_requested) <= index:
                                                tool_calls_requested.append(
                                                    {
                                                        "name": "",
                                                        "arguments_str": "",
                                                        "id": "call_1",
                                                    }
                                                )
                                            if tc.get("id"):
                                                tool_calls_requested[index]["id"] = tc[
                                                    "id"
                                                ]
                                            fn = tc.get("function", {})
                                            if fn.get("name"):
                                                tool_calls_requested[index]["name"] = (
                                                    fn["name"]
                                                )
                                            if fn.get("arguments"):
                                                tool_calls_requested[index][
                                                    "arguments_str"
                                                ] += fn["arguments"]
                                except Exception:
                                    continue
                    else:
                        logger.warning(
                            f"[LLM SERVICE] {p_name} HTTP {response.status_code}. Trying next provider..."
                        )
                        continue

            if tool_calls_requested:
                for tc in tool_calls_requested:
                    t_name = tc.get("name")
                    t_id = tc.get("id", "call_1")
                    try:
                        t_args = json.loads(tc.get("arguments_str", "{}"))
                    except Exception:
                        t_args = {}

                    if t_name:
                        tool_start = datetime.now()
                        tool_res = await execute_tool_call(
                            t_name, t_args, db=db, org_id=org_id
                        )
                        elapsed_ms = (
                            datetime.now() - tool_start
                        ).total_seconds() * 1000

                        if elapsed_ms > 600:
                            yield {
                                "type": "filler",
                                "content": "Checking that for you...",
                            }

                        messages.append(
                            {
                                "role": "assistant",
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": t_id,
                                        "type": "function",
                                        "function": {
                                            "name": t_name,
                                            "arguments": json.dumps(t_args),
                                        },
                                    }
                                ],
                            }
                        )
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": t_id,
                                "content": json.dumps(tool_res),
                            }
                        )

                        payload["messages"] = messages
                        payload["tools"] = dynamic_tools
                        payload["tool_choice"] = "none"

                        has_yielded_token = False
                        async with httpx.AsyncClient(timeout=10.0) as client2:
                            async with client2.stream(
                                "POST", url, headers=headers, json=payload
                            ) as res2:
                                if res2.status_code == 200:
                                    async for line in res2.aiter_lines():
                                        if line.startswith("data: "):
                                            d_str = line[6:].strip()
                                            if d_str == "[DONE]":
                                                break
                                            try:
                                                c2 = json.loads(d_str)
                                                if c2.get("choices"):
                                                    tok = c2["choices"][0]["delta"].get(
                                                        "content", ""
                                                    )
                                                    if tok:
                                                        has_yielded_token = True
                                                        yield {
                                                            "type": "token",
                                                            "content": tok,
                                                        }
                                            except Exception:
                                                continue
                                else:
                                    logger.warning(
                                        f"[LLM LOOP 2 ERROR] {p_name} HTTP {res2.status_code}"
                                    )

                        if not has_yielded_token:
                            fallback_msg = tool_res.get("message") or (
                                f"I have checked the schedule for you. {tool_res.get('doctor_name', 'The doctor')} is available."
                                if tool_res.get("available")
                                else "I checked the schedule and saved your request."
                            )
                            yield {"type": "token", "content": fallback_msg}
            return
        except Exception as e:
            logger.warning(f"[LLM SERVICE] {p_name} stream error ({type(e).__name__}). Trying next provider...")

    yield {
        "type": "token",
        "content": "I am here to assist you with your appointment. How can I help you?",
    }


async def generate_llm_json(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.0,
    max_tokens: int = 200,
) -> Optional[Dict[str, Any]]:
    """
    Primary: Gemini 2.5 Flash via OpenAI REST API.
    Fallback: Groq Llama 3.3 70B.
    """
    gemini_key = settings.GEMINI_API_KEY
    if gemini_key:
        for model in PRIMARY_MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            payload = {
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "generationConfig": {
                    "response_mime_type": "application/json",
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                },
            }
            async with httpx.AsyncClient(timeout=4.0) as client:
                for attempt in range(1):
                    try:
                        res = await _gemini_post(client, url, payload, {"x-goog-api-key": gemini_key})
                        if res.status_code == 200:
                            data = res.json()
                            candidates = data.get("candidates", [])
                            if candidates:
                                parts = (
                                    candidates[0].get("content", {}).get("parts", [])
                                )
                                if parts:
                                    content = parts[0].get("text", "")
                                    return _clean_and_parse_json(content)
                        elif res.status_code == 429 and attempt == 0:
                            await asyncio.sleep(1.0)
                            continue
                        else:
                            logger.warning(
                                f"[LLM SERVICE] Gemini {model} returned HTTP {res.status_code}"
                            )
                            break
                    except Exception as e:
                        logger.warning(
                            f"[LLM SERVICE] Gemini {model} failed ({type(e).__name__}). Trying next model..."
                        )
                        break

    groq_key = settings.GROQ_API_KEY
    if groq_key:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {groq_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=4.0) as client:
            try:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    content = data["choices"][0]["message"]["content"]
                    return _clean_and_parse_json(content)
            except Exception as e:
                logger.warning(f"[LLM SERVICE] Groq fallback failed ({type(e).__name__}).")

    return None


def _clean_and_parse_json(raw: str) -> dict:
    if not raw:
        raise ValueError("Empty response string")
    text = raw.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    codeblock = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if codeblock:
        try:
            return json.loads(codeblock.group(1))
        except Exception:
            pass

    json_match = re.search(r"(\{[\s\S]*\})", text)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except Exception:
            pass

    raise ValueError(f"Could not parse JSON: {text[:100]}")


async def generate_llm_json_with_history(
    system_prompt: str,
    conversation_history: list,
    temperature: float = 0.0,
    max_tokens: int = 1000,
) -> Optional[Dict[str, Any]]:
    """
    Conversation-aware structured JSON extraction.
    Primary: Gemini 2.5 Flash.
    Fallback: Groq Llama 3.3 70B.
    """
    messages = [{"role": "system", "content": system_prompt}]
    for h in conversation_history:
        role = "assistant" if h.get("role") in ["model", "assistant"] else "user"
        text_val = h.get("content") or h.get("text") or ""
        if text_val:
            messages.append({"role": role, "content": text_val})

    gemini_key = settings.GEMINI_API_KEY
    if gemini_key:
        for model in PRIMARY_MODELS:
            url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
            headers = {
                "Authorization": f"Bearer {gemini_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model,
                "messages": messages,
                "response_format": {"type": "json_object"},
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            async with httpx.AsyncClient(timeout=4.0) as client:
                try:
                    res = await _gemini_post(client, url, payload, headers)
                    if res.status_code == 200:
                        data = res.json()
                        content_str = data["choices"][0]["message"]["content"]
                        return _clean_and_parse_json(content_str)
                    elif res.status_code == 429:
                        continue
                except Exception:
                    continue

    groq_key = settings.GROQ_API_KEY
    if groq_key:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {groq_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=4.0) as client:
            try:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    content_str = data["choices"][0]["message"]["content"]
                    return _clean_and_parse_json(content_str)
            except Exception:
                pass

    return None


async def generate_llm_text(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 150,
) -> Optional[str]:
    gemini_key = settings.GEMINI_API_KEY
    if gemini_key:
        async with httpx.AsyncClient(timeout=4.0) as client:
            for model in PRIMARY_MODELS:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                payload = {
                    "system_instruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                    "generationConfig": {
                        "temperature": temperature,
                        "maxOutputTokens": max_tokens,
                    },
                }
                try:
                    res = await _gemini_post(client, url, payload, {"x-goog-api-key": gemini_key})
                    if res.status_code == 200:
                        data = res.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                text_content = parts[0].get("text", "").strip()
                                if text_content:
                                    return text_content
                except Exception as e:
                    logger.warning(
                        f"[LLM SERVICE] Gemini {model} text failed ({type(e).__name__}). Trying next fallback..."
                    )

    groq_key = settings.GROQ_API_KEY
    if groq_key:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {groq_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=4.0) as client:
            try:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    return data["choices"][0]["message"]["content"].strip()
            except Exception as e:
                logger.warning(f"[LLM SERVICE] Groq text fallback failed: {type(e).__name__}")

    return None
