from enum import StrEnum
from dataclasses import dataclass
from typing import Any
import re
import asyncio


class ErrorCategory(StrEnum):
    TRANSIENT_NETWORK = "transient_network"
    RATE_LIMITED = "rate_limited"
    AUTHENTICATION = "authentication"
    INVALID_ARGUMENT = "invalid_argument"
    NOT_FOUND = "not_found"
    FATAL_PROVIDER = "fatal_provider"
    CANCELED = "canceled"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SanitizedProviderError:
    category: ErrorCategory
    recoverable: bool
    wrapper_type: str
    underlying_type: str
    status_code: int | None
    request_id: str | None
    retry_after: float | None
    sanitized_message: str


def sanitize_error_message(raw: str) -> str:
    if not raw:
        return ""
    cleaned = re.sub(r"Bearer\s+[^\s\"'&,]+", "Bearer [REDACTED]", raw, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"(?i)([?&](?:key|api_key|token|access_token|secret)=)[^&\s\"']+",
        r"\1[REDACTED]", cleaned,
    )
    cleaned = re.sub(
        r"(?i)([\"']?(?:api_key|api_secret|auth_token|access_token|password|service_role_key)[\"']?\s*[:=]\s*)[\"']?[^\s,}\"']+",
        r"\1[REDACTED]", cleaned,
    )
    cleaned = re.sub(r"(\w+://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", cleaned)
    cleaned = re.sub(
        r"\b(AIza[0-9A-Za-z_-]{20,}|dg_[0-9a-fA-F]{20,}|gsk_[0-9A-Za-z]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{20,}|sb_secret_[A-Za-z0-9_-]{20,}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b",
        "[REDACTED_KEY]", cleaned,
    )
    cleaned = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[REDACTED_EMAIL]", cleaned)
    cleaned = re.sub(r"(?<![A-Za-z0-9])\+?[1-9]\d{7,14}(?![A-Za-z0-9])", "[REDACTED_PHONE]", cleaned)
    return " ".join(cleaned.split())[:200]


def _extract_status_code(error: Any) -> int | None:
    status = getattr(error, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(error, "response", None)
    if response is not None:
        resp_status = getattr(response, "status_code", None)
        if isinstance(resp_status, int):
            return resp_status
    code = getattr(error, "code", None)
    if isinstance(code, int):
        return code
    return None


def _extract_request_id(error: Any) -> str | None:
    req_id = getattr(error, "request_id", None)
    if req_id and isinstance(req_id, str):
        return req_id
    response = getattr(error, "response", None)
    if response is not None:
        headers = getattr(response, "headers", {})
        if hasattr(headers, "get"):
            header_id = headers.get("x-request-id") or headers.get("x-dg-request-id")
            if header_id and isinstance(header_id, str):
                return header_id
    return None


def _extract_retry_after(error: Any) -> float | None:
    val = getattr(error, "retry_after", None)
    if isinstance(val, (int, float)):
        return float(val)
    response = getattr(error, "response", None)
    if response is not None:
        headers = getattr(response, "headers", {})
        if hasattr(headers, "get"):
            header_val = headers.get("retry-after")
            if header_val:
                try:
                    return float(header_val)
                except ValueError:
                    return None
    return None


def unwrap_root_cause(error: Any) -> Any:
    current = error
    for _ in range(5):
        nested = getattr(current, "error", None) or getattr(current, "__cause__", None) or getattr(current, "__context__", None)
        if nested is None or nested is current:
            break
        current = nested
    return current


def classify_provider_error(error: Any) -> SanitizedProviderError:
    wrapper_type = type(error).__name__
    underlying = unwrap_root_cause(error)
    underlying_type = type(underlying).__name__

    if isinstance(underlying, asyncio.CancelledError):
        return SanitizedProviderError(
            category=ErrorCategory.CANCELED,
            recoverable=False,
            wrapper_type=wrapper_type,
            underlying_type=underlying_type,
            status_code=None,
            request_id=None,
            retry_after=None,
            sanitized_message="Operation cancelled",
        )

    status_code = _extract_status_code(underlying) or _extract_status_code(error)
    request_id = _extract_request_id(underlying) or _extract_request_id(error)
    retry_after = _extract_retry_after(underlying) or _extract_retry_after(error)
    raw_message = str(getattr(underlying, "message", None) or getattr(underlying, "body", None) or underlying)
    sanitized_msg = sanitize_error_message(raw_message)

    is_explicit_retryable = bool(
        getattr(underlying, "retryable", False)
        or getattr(error, "retryable", False)
        or getattr(underlying, "recoverable", False)
        or getattr(error, "recoverable", False)
    )

    category = ErrorCategory.UNKNOWN
    recoverable = False

    name_lower = f"{underlying_type.lower()} {wrapper_type.lower()} {raw_message.lower()}"

    rate_limit_patterns = (r"\brate[_\s-]?limit", r"\bquota\b", r"resourceexhausted")
    is_rate_limited = status_code == 429 or any(re.search(pat, name_lower) for pat in rate_limit_patterns)

    if is_rate_limited:
        category = ErrorCategory.RATE_LIMITED
        recoverable = (retry_after is not None and retry_after <= 3.0) or is_explicit_retryable
    elif status_code in (401, 403) or any(k in name_lower for k in ("unauthorized", "unauthenticated", "permissiondenied")):
        category = ErrorCategory.AUTHENTICATION
        recoverable = False
    elif status_code == 404 or "notfound" in name_lower or "not found" in name_lower:
        category = ErrorCategory.NOT_FOUND
        recoverable = False
    elif status_code == 400 or any(k in name_lower for k in ("invalidargument", "schema", "bad request")):
        category = ErrorCategory.INVALID_ARGUMENT
        recoverable = False
    elif (
        status_code in (502, 503, 504)
        or is_explicit_retryable
        or any(k in name_lower for k in ("timeout", "connection", "unavailable", "timed out", "econnreset", "econnrefused", "no response generated"))
    ):
        category = ErrorCategory.TRANSIENT_NETWORK
        recoverable = True
    elif status_code == 500 or "internal" in name_lower:
        category = ErrorCategory.FATAL_PROVIDER
        recoverable = False

    return SanitizedProviderError(
        category=category,
        recoverable=recoverable,
        wrapper_type=wrapper_type,
        underlying_type=underlying_type,
        status_code=status_code,
        request_id=request_id,
        retry_after=retry_after,
        sanitized_message=sanitized_msg,
    )
