import time
from typing import Dict, Any, Optional, List
import phonenumbers
from phonenumbers import timezone as phone_timezone

_call_sessions: Dict[str, Dict[str, Any]] = {}
_specialties_cache: Dict[str, List[str]] = {}
SESSION_TTL_SECONDS = 600

IANA_CANONICAL_MAP = {
    "Asia/Calcutta": "Asia/Kolkata",
    "Asia/Katmandu": "Asia/Kathmandu",
    "Asia/Rangoon": "Asia/Yangon",
    "Asia/Saigon": "Asia/Ho_Chi_Minh",
}


def resolve_caller_timezone(phone_str: str, default_tz: str) -> str:
    if not phone_str:
        return default_tz
    try:
        clean_phone = _normalize_phone(phone_str, default_tz)
        parsed_num = phonenumbers.parse(clean_phone, None)
        tz_list = phone_timezone.time_zones_for_number(parsed_num)
        if tz_list and len(tz_list) > 0:
            raw_tz = tz_list[0]
            return IANA_CANONICAL_MAP.get(raw_tz, raw_tz)
    except Exception:
        pass
    return default_tz


def get_cached_specialties(org_id: str) -> Optional[List[str]]:
    return _specialties_cache.get(str(org_id))


def set_cached_specialties(org_id: str, specialties: List[str]) -> None:
    _specialties_cache[str(org_id)] = specialties


def invalidate_specialties_cache(org_id: Optional[str] = None) -> None:
    if org_id:
        _specialties_cache.pop(str(org_id), None)
    else:
        _specialties_cache.clear()


def _normalize_phone(phone: str, tz_name: Optional[str] = None) -> str:
    digits = "".join(filter(str.isdigit, phone))
    prefix = "1" if (tz_name and "America" in tz_name) else "91"

    if len(digits) == 10:
        return f"+{prefix}{digits}"
    if len(digits) == 12 and digits.startswith(prefix):
        return f"+{digits}"
    return f"+{digits}" if not phone.startswith("+") else phone


def get_session_context(caller_phone: str) -> Dict[str, Any]:
    clean_phone = _normalize_phone(caller_phone)
    session = _call_sessions.get(clean_phone)

    if not session:
        session = {
            "caller_name": None,
            "dob": None,
            "chief_complaint": None,
            "disambiguated_patient_id": None,
            "conversation_history": [],
            "created_at": time.time(),
        }
        _call_sessions[clean_phone] = session
        return session

    if time.time() - session.get("created_at", 0) > SESSION_TTL_SECONDS:
        _call_sessions.pop(clean_phone, None)
        return get_session_context(caller_phone)

    return session


def update_session_context(caller_phone: str, allow_correction: bool = False, **kwargs) -> Dict[str, Any]:
    ctx = get_session_context(caller_phone)
    for key, value in kwargs.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        ctx[key] = value
    ctx["created_at"] = time.time()
    _call_sessions[_normalize_phone(caller_phone)] = ctx
    return ctx


def append_conversation_turn(caller_phone: str, role: str, text: str) -> None:
    ctx = get_session_context(caller_phone)
    history: List[dict] = ctx.get("conversation_history", [])
    history.append({"role": role, "text": text})
    if len(history) > 20:
        history = history[-20:]
    ctx["conversation_history"] = history
    ctx["created_at"] = time.time()
    _call_sessions[_normalize_phone(caller_phone)] = ctx


def get_conversation_history(caller_phone: str) -> List[dict]:
    return get_session_context(caller_phone).get("conversation_history", [])


def lock_patient_identity(caller_phone: str, patient_id: str) -> None:
    ctx = get_session_context(caller_phone)
    ctx["disambiguated_patient_id"] = patient_id
    ctx["created_at"] = time.time()
    _call_sessions[_normalize_phone(caller_phone)] = ctx


def clear_call_session(caller_phone: str) -> None:
    _call_sessions.pop(_normalize_phone(caller_phone), None)
