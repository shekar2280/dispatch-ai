import json
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ParticipantCallContext:
    org_id: UUID | None
    caller_phone: str
    caller_name: str | None
    stt_provider: str
    call_id: UUID | None


def parse_participant_call_context(metadata: str, attributes: dict) -> ParticipantCallContext:
    try:
        meta = json.loads(metadata or "{}")
    except (ValueError, TypeError):
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    attrs = attributes or {}

    def value(key, *aliases):
        for name in (key, *aliases):
            candidate = attrs.get(name) or meta.get(name)
            if candidate:
                return str(candidate)
        return ""

    def identifier(raw):
        return UUID(raw) if raw else None

    return ParticipantCallContext(
        org_id=identifier(value("org_id", "organization_id", "sip.h.x-org-id")),
        caller_phone=value("caller_phone", "phone_number", "phone", "sip.h.x-caller-phone", "sip.phoneNumber"),
        caller_name=value("caller_name", "participant_name", "sip.h.x-caller-name") or None,
        stt_provider=value("stt_provider") or "deepgram",
        call_id=identifier(value("call_id", "sip.h.x-call-id")),
    )
