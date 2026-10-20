"""
prompt_builder.py

Structured system prompt builder for the Voice AI Agent.

Replaces the ad-hoc string-append pattern in agent_worker.py.
Composes the final system prompt from three clearly separated layers:

  Layer 1 — Platform Core:   Immutable HIPAA + voice formatting rules (agent_prompts.py)
  Layer 2 — Org Directives:  DB-sourced, admin-editable instructions for this clinic
  Layer 3 — Session State:   Call-time context (dispatcher availability, emergency mode)

Each layer is delimited so the LLM receives a structured, consistent document
regardless of how many org directives or session overrides are active.
"""

import logging
from datetime import date, timedelta
from typing import Optional
from uuid import UUID

logger = logging.getLogger("dispatch-prompt-builder")


def format_friendly_date(date_str: str) -> str:
    try:
        d = date.fromisoformat(date_str.strip())
        today = date.today()
        if d == today:
            return "today"
        if d == today + timedelta(days=1):
            return "tomorrow"
        if d == today - timedelta(days=1):
            return "yesterday"
        diff = (d - today).days
        if 0 < diff < 7:
            return d.strftime("%A, %B %d")
        return d.strftime("%B %d")
    except Exception:
        return date_str


async def build_system_prompt(
    db,
    org_id: Optional[UUID],
    clinic_name: str,
    tz_name: str,
    caller_name: Optional[str],
    caller_phone: Optional[str],
    closure_notice: Optional[str],
    available_dispatchers: int = 0,
    clinic_specialty: Optional[str] = None,
    lead_doctor_name: Optional[str] = None,
    emergency_deflection_phone: Optional[str] = None,
    custom_greeting: Optional[str] = None,
) -> str:
    from app.agent.agent_prompts import get_system_prompt

    core_prompt = get_system_prompt(
        clinic_name=clinic_name,
        tz_name=tz_name,
        caller_name=caller_name,
        caller_phone=caller_phone,
        closure_notice=closure_notice,
        custom_greeting=custom_greeting,
        clinic_specialty=clinic_specialty,
        lead_doctor_name=lead_doctor_name,
        emergency_phone=emergency_deflection_phone or "",
    )

    org_directives_block = await _load_org_directives_block(db, org_id)

    sections = [core_prompt.strip()]

    if org_directives_block:
        sections.append(
            "--- CLINIC CUSTOM DIRECTIVES (set by your clinic admin) ---\n"
            + org_directives_block.strip()
        )

    return "\n\n".join(sections)


async def _load_org_directives_block(db, org_id: Optional[UUID]) -> str:
    # Clinic facts and greeting come from organizations.voice_ai_settings.
    # No optional SQL table or lower-priority arbitrary instructions.
    return ""


async def build_clinic_prompt(
    db,
    org_id: Optional[UUID],
    clinic_name: str,
    tz_name: str,
    caller_name: Optional[str],
    caller_phone: Optional[str],
    closure_notice: Optional[str],
    clinic_specialty: Optional[str] = None,
    lead_doctor_name: Optional[str] = None,
    emergency_deflection_phone: Optional[str] = None,
    custom_greeting: Optional[str] = None,
) -> str:
    return await build_system_prompt(
        db=db,
        org_id=org_id,
        clinic_name=clinic_name,
        tz_name=tz_name,
        caller_name=caller_name,
        caller_phone=caller_phone,
        closure_notice=closure_notice,
        available_dispatchers=0,
        clinic_specialty=clinic_specialty,
        lead_doctor_name=lead_doctor_name,
        emergency_deflection_phone=emergency_deflection_phone,
        custom_greeting=custom_greeting,
    )


__all__ = [
    "build_system_prompt",
    "build_clinic_prompt",
    "format_friendly_date",
]
