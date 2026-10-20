from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException


def require_clinic_timezone(org: Any) -> str:
    if org is None:
        raise HTTPException(status_code=404, detail="Clinic organization not found")
    timezone = getattr(org, "timezone", None)
    if not isinstance(timezone, str) or not timezone.strip():
        raise HTTPException(status_code=422, detail="Clinic timezone is not configured")
    timezone = timezone.strip()
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        raise HTTPException(status_code=422, detail="Clinic timezone is invalid")
    return timezone


def require_clinic_booking_integer(org: Any, key: str, *, allow_zero: bool = False) -> int:
    if org is None:
        raise HTTPException(status_code=404, detail="Clinic organization not found")
    value = getattr(org, key, None)
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = -1
    if number < (0 if allow_zero else 1):
        raise HTTPException(status_code=422, detail=f"Clinic {key} is not configured")
    return number
