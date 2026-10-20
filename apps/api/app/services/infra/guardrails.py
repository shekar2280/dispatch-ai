import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

PLATFORM_HARD_BLOCKS: list[tuple[str, str]] = [
    (r"\btake\s+\d+\s*mg\b", "DRUG_DOSAGE_INSTRUCTION"),
    (r"\bprescription\b", "PRESCRIPTION_MENTION"),
    (r"\byou\s+have\s+cancer\b", "CANCER_DIAGNOSIS"),
    (r"\byou\s+are\s+infected\b", "INFECTION_DIAGNOSIS"),
    (r"\btake\s+antibiotics\b", "ANTIBIOTIC_INSTRUCTION"),
    (r"\bsurgery\s+is\s+required\b", "SURGERY_REQUIRED_CLAIM"),
    (r"\byou\s+are\s+pregnant\b", "PREGNANCY_CLAIM"),
    (r"\byou\s+have\s+diabetes\b", "DIABETES_DIAGNOSIS"),
    (r"\byou\s+have\s+heart\s+failure\b", "HEART_FAILURE_DIAGNOSIS"),
    (r"\bdiagnosis\s*:\s*\w+", "DIAGNOSIS_COLON_PATTERN"),
    (r"\bi\s+diagnose\b", "AI_SELF_DIAGNOSIS"),
    (r"\bstop\s+taking\s+your\s+medication\b", "STOP_MEDICATION_INSTRUCTION"),
]

PLATFORM_SOFT_FLAGS: list[tuple[str, str]] = [
    (r"\bblood\s+pressure\s+of\s+\d+", "BP_VALUE_READING"),
    (r"\btake\s+\w+\s+tablet", "TABLET_INSTRUCTION"),
    (r"\binjection\b", "INJECTION_MENTION"),
    (r"\bx-?ray\b", "XRAY_MENTION"),
]

GUARDRAIL_FALLBACK_RESPONSE = (
    "I'm sorry, I'm not able to provide medical advice or diagnoses. "
    "Please consult with one of our doctors for specific medical questions. "
    "Shall I help you book an appointment?"
)

def check_platform_guardrails(
    response_text: str,
) -> tuple[bool, Optional[str], str]:
    lower_text = response_text.lower()

    for pattern, rule_name in PLATFORM_HARD_BLOCKS:
        if re.search(pattern, lower_text):
            return False, rule_name, "HARD_BLOCKED"

    for pattern, rule_name in PLATFORM_SOFT_FLAGS:
        if re.search(pattern, lower_text):
            return True, rule_name, "SOFT_FLAGGED"

    return True, None, "ALLOWED"

async def log_guardrail_violation(
    db,
    session_id: Optional[str],
    turn_number: int,
    ai_response_text: str,
    matched_rule: str,
    action: str,
) -> None:
    try:
        from sqlalchemy import text
        await db.execute(
            text("""
                INSERT INTO public.guardrail_violations
                    (session_id, turn_number, ai_response_text, matched_rule, action_taken)
                VALUES
                    (:session_id, :turn_number, :ai_response_text, :matched_rule, :action_taken)
            """),
            {
                "session_id": session_id,
                "turn_number": turn_number,
                "ai_response_text": ai_response_text[:2000],
                "matched_rule": matched_rule,
                "action_taken": action,
            },
        )
        await db.commit()
    except Exception as e:
        logger.warning(f"Could not log guardrail violation: {e}")
