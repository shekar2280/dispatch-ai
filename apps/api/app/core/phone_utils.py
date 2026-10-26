import logging
from typing import Optional, Tuple
import phonenumbers
from phonenumbers import PhoneNumberFormat, NumberParseException
from phonenumbers.timezone import time_zones_for_number

from app.schemas.patient import PhoneNormalizationResult

logger = logging.getLogger("app.core.phone_utils")

def normalize_phone_e164(
    raw_phone: str,
    default_country: Optional[str] = None
) -> PhoneNormalizationResult:
    if not raw_phone or not str(raw_phone).strip():
        return PhoneNormalizationResult(
            raw_phone=raw_phone or "",
            e164_phone="",
            country_code=default_country or "",
            country_calling_code=0,
            is_valid=False,
            error_message="Empty or null phone string provided",
        )

    clean_str = str(raw_phone).strip()

    try:
        parsed = phonenumbers.parse(clean_str, default_country)
        is_valid = phonenumbers.is_valid_number(parsed)
        e164_phone = phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
        country_code = phonenumbers.region_code_for_number(parsed) or default_country or ""
        country_calling_code = parsed.country_code

        return PhoneNormalizationResult(
            raw_phone=clean_str,
            e164_phone=e164_phone,
            country_code=country_code,
            country_calling_code=country_calling_code,
            is_valid=is_valid,
        )
    except NumberParseException as e:
        logger.warning("Failed to parse phone number: %s", e)
        return PhoneNormalizationResult(
            raw_phone=clean_str,
            e164_phone="",
            country_code=default_country or "",
            country_calling_code=0,
            is_valid=False,
            error_message=str(e),
        )


def resolve_phone_timezone(e164_phone: str, fallback_tz: str) -> str:
    if not e164_phone:
        return fallback_tz

    try:
        parsed = phonenumbers.parse(e164_phone, None)
        tzs = time_zones_for_number(parsed)
        if tzs and len(tzs) > 0:
            return tzs[0]
    except Exception as e:
        logger.debug("Timezone lookup error: %s", e)

    return fallback_tz
