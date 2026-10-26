import json
from pathlib import Path

_RESOURCE_PATH = Path(__file__).resolve().parent.parent.parent / "resources" / "emergency_numbers.json"

try:
    with open(_RESOURCE_PATH, encoding="utf-8") as _f:
        _EMERGENCY_TABLE = json.load(_f)
except Exception:
    _EMERGENCY_TABLE = {}


def resolve_emergency_phone(configured_phone: str | None, country_code: str | None) -> str:
    if configured_phone and str(configured_phone).strip():
        return str(configured_phone).strip()
    code = (country_code or "").strip().upper()
    entry = _EMERGENCY_TABLE.get(code)
    if entry and isinstance(entry, dict):
        number = entry.get("ambulance") or entry.get("police") or entry.get("fire")
        if number:
            return str(number)
    return ""
