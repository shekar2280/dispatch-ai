import re
import time
import logging
from typing import Optional, List, Dict, Any
from datetime import date as dt_date
import datetime
from app.schemas.triage import TriageRequest, TriageResponse
from app.schemas.voice_assistant import ExtractedCallIntent
from app.services.infra.llm_client import generate_llm_json, generate_llm_json_with_history

logger = logging.getLogger(__name__)

EMERGENCY_PATTERNS = [
    r"\bemergency\b",
    r"\bchest pain\b",
    r"\bheart attack\b",
    r"\bcan'?t breathe\b",
    r"\bbreathing difficulty\b",
    r"\bunconscious\b",
    r"\bbleeding\b",
    r"\bstroke\b",
    r"\bseizure\b",
    r"\bhead injury\b",
    r"\baccident\b",
    r"\bcall (an )?ambulance\b",
    r"\bmedical emergency\b",
    r"\blife threatening\b",
    r"\bhelp me\b",
    r"\bsave me\b",
    r"\bcollapsed\b",
    r"\bdying\b",
]

EMERGENCY_REGEX = re.compile("|".join(EMERGENCY_PATTERNS), re.IGNORECASE)

ADMIN_PATTERNS = [
    r"\bappointment\b",
    r"\bbook(ing)?\b",
    r"\bslots?\b",
    r"\bschedule\b",
    r"\bdoctor\b",
    r"\btimings?\b",
    r"\bhours?\b",
    r"\bopd\b",
    r"\bconsult(ation)?\b",
    r"\bcheckup\b",
    r"\bclinic\b",
    r"\breports?\b",
    r"\blab\b",
    r"\btest(s)?\b",
    r"\bstatus\b",
    r"\bgeneral checkup\b",
    r"\bcancel\b",
    r"\breschedule\b",
    r"\broutine\b",
]

ADMIN_REGEX = re.compile("|".join(ADMIN_PATTERNS), re.IGNORECASE)


async def classify_intent_semantic(
    utterance: str, conversation_history: Optional[List[Dict[str, str]]] = None
) -> Dict[str, Any]:
    start_time = time.time()
    clean = (utterance or "").strip()
    if not clean:
        elapsed_ms = (time.time() - start_time) * 1000
        return {
            "intent": "ADMIN",
            "urgency_score": 1,
            "matched_trigger": None,
            "reason": "Empty utterance",
            "latency_ms": elapsed_ms,
        }

    em_match = EMERGENCY_REGEX.search(clean)
    has_past_reference = re.search(
        r"\b(last (year|month|week)|pichle (saal|mahine|hafte)|previously|history of|\d+\s*(years?|saal|months?|mahine)\s*ago|\d+\s*(years?|saal|months?|mahine)\s*pehle|past|purana)\b",
        clean,
        re.IGNORECASE,
    )
    has_negation = re.search(
        r"\b(no|not|neither|nor|don'?t have|abhi.*thik|fine now|ab thik)\b",
        clean,
        re.IGNORECASE,
    )
    if em_match and not has_negation and not has_past_reference:
        elapsed_ms = (time.time() - start_time) * 1000
        return {
            "intent": "EMERGENCY",
            "urgency_score": 5,
            "matched_trigger": em_match.group(0),
            "reason": "Immediate emergency keyword match",
            "latency_ms": elapsed_ms,
        }

    admin_match = ADMIN_REGEX.search(clean)
    if admin_match and not em_match:
        elapsed_ms = (time.time() - start_time) * 1000
        return {
            "intent": "ADMIN",
            "urgency_score": 1,
            "matched_trigger": None,
            "reason": "Administrative inquiry match",
            "latency_ms": elapsed_ms,
        }

    system_prompt = (
        "You are an ultra-fast real-time emergency medical intent classifier for a hospital voice telephony system.\n"
        "Classify the caller's spoken statement into EMERGENCY or ADMIN.\n"
        "EMERGENCY includes: accidents, bleeding ('rakta'), chest pain ('chest pain', 'chhati dard', 'nenju vali', 'gunde noppi', 'bukey batha'), "
        "cardiac arrest, stroke, unconsciousness/fainting ('behosh', 'mayangittaaru'), respiratory distress ('saans atak', 'moochu vida'), "
        "severe trauma ('mohta accident'), poisoning, seizures, panic distress in any language or dialect (English, Hindi, Hinglish, Marathi, Tamil, Telugu, Bengali, Gujarati, Kannada, Malayalam, Punjabi).\n"
        "ADMIN includes: appointment scheduling, doctor availability, clinic timings, lab reports, general inquiries, or past medical mentions with NO active crisis.\n"
        "CRITICAL: Translate Romanized phonemes from any Indian language to identify life-threatening medical distress. Pay close attention to negation (e.g., 'I do not have chest pain' is ADMIN).\n"
        "Respond ONLY with a valid JSON object matching:\n"
        "{\n"
        '  "intent": "EMERGENCY" | "ADMIN",\n'
        '  "urgency_score": 1 to 5,\n'
        '  "matched_trigger": "short description of trigger (e.g. cardiac, trauma, accident, none)",\n'
        '  "reason": "brief 1-sentence rationale"\n'
        "}"
    )

    user_prompt = f'Caller utterance: "{utterance.strip()}"'
    if conversation_history:
        history_context = "\n".join(
            [
                f"{m.get('role', 'user')}: {m.get('content', '')}"
                for m in conversation_history[-3:]
            ]
        )
        user_prompt = f'Recent context:\n{history_context}\n\nLatest utterance: "{utterance.strip()}"'

    content = await generate_llm_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.0,
        max_tokens=250,
    )

    elapsed_ms = (time.time() - start_time) * 1000

    if content and isinstance(content, dict):
        raw_intent = str(content.get("intent", "ADMIN")).upper()
        intent = "EMERGENCY" if "EMERGENCY" in raw_intent else "ADMIN"
        urgency = int(content.get("urgency_score", 1 if intent == "ADMIN" else 5))
        trigger = content.get("matched_trigger")
        reason = content.get("reason", "Semantic classification")

        return {
            "intent": intent,
            "urgency_score": urgency,
            "matched_trigger": trigger if intent == "EMERGENCY" else None,
            "reason": reason,
            "latency_ms": elapsed_ms,
        }

    return {
        "intent": "ADMIN",
        "urgency_score": 1,
        "matched_trigger": None,
        "reason": "Fallback default",
        "latency_ms": (time.time() - start_time) * 1000,
    }


async def classify_triage_intent(request: TriageRequest) -> TriageResponse:
    system_prompt = (
        "You are a medical triage classifier. Analyze the transcript and return JSON with keys:\n"
        "- intent: 'EMERGENCY' or 'ADMINISTRATIVE'\n"
        "- urgency_score: integer from 1 to 5\n"
        "- reason: short 1-sentence reason\n"
        "RULES:\n"
        "1. EMERGENCY (score 4-5): chest pain, heart attack, severe uncontrolled bleeding, "
        "stroke, unconsciousness, severe trauma, choking, car accident.\n"
        "2. ADMINISTRATIVE (score 1-2): general consultations, routine appointments, "
        "headaches, fever, cough, scheduling requests, follow-ups."
    )
    user_prompt = f"Patient Transcript: {request.speech_text}"
    content = await generate_llm_json(
        system_prompt, user_prompt, temperature=0.0, max_tokens=100
    )

    if content:
        intent = str(content.get("intent", "ADMINISTRATIVE")).upper()
        if intent not in ["EMERGENCY", "ADMINISTRATIVE"]:
            intent = "ADMINISTRATIVE"
        return TriageResponse(
            speech_text=request.speech_text,
            phone_number=request.phone_number,
            intent=intent,
            urgency_score=int(content.get("urgency_score", 3)),
            reason=str(content.get("reason", "Analyzed by AI triage engine")),
        )

    fast_res = classify_intent_semantic(request.speech_text)
    return TriageResponse(
        speech_text=request.speech_text,
        phone_number=request.phone_number,
        intent=fast_res["intent"],
        urgency_score=fast_res["urgency_score"],
        reason="Pattern keyword fallback",
    )


async def extract_voice_call_intent(
    speech_text: str,
    current_date_str: str,
    available_specialties: Optional[List[str]] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> ExtractedCallIntent:
    specs_str = (
        ", ".join(available_specialties)
        if available_specialties
        else "General Medicine"
    )

    clinic_date = dt_date.fromisoformat(current_date_str)
    system_time_context = f"Current clinic date: {clinic_date.isoformat()}"

    system_prompt = (
        "You are an AI medical receptionist entity extractor. "
        "Extract intent, patient details, and appointment preferences from the patient's speech.\n"
        f"Available hospital specialties: [{specs_str}].\n"
        f"{system_time_context}.\n"
        "OUTPUT JSON SCHEMA:\n"
        "{\n"
        '  "intent": "ADMINISTRATIVE",\n'
        '  "action": "CHECK_AVAILABILITY",\n'
        '  "extracted_name": null,\n'
        '  "specialty_or_complaint": "General Consultation",\n'
        '  "target_date": "YYYY-MM-DD",\n'
        '  "target_time": "16:00",\n'
        '  "time_context": "afternoon"\n'
        "}\n"
        "RULES FOR SEMANTIC TIME RESOLUTION:\n"
        "- If user says 'today', set target_date to current date in YYYY-MM-DD format or string 'today'.\n"
        "- If user says 'tomorrow', set target_date to current date + 1 day in YYYY-MM-DD format or string 'tomorrow'.\n"
        "- Map spoken times ('4 PM', '4:00pm', 'afternoon') to strict 24-hour time ('16:00') or time_context.\n"
        "Return a JSON object matching ExtractedCallIntent schema."
    )

    if not speech_text or not speech_text.strip():
        return ExtractedCallIntent(
            intent="ADMINISTRATIVE",
            action="CHECK_AVAILABILITY",
            is_silent=True,
        )

    history = list(conversation_history or [])
    history.append({"role": "user", "content": speech_text})

    content = await generate_llm_json_with_history(
        system_prompt=system_prompt,
        conversation_history=history,
        temperature=0.1,
    )

    if not content:
        return ExtractedCallIntent(
            intent="ADMINISTRATIVE",
            action="CHECK_AVAILABILITY",
            is_silent=False,
        )

    intent_val = str(content.get("intent", "ADMINISTRATIVE")).upper()
    if intent_val not in ["EMERGENCY", "ADMINISTRATIVE"]:
        intent_val = "ADMINISTRATIVE"

    dob_val = None
    if content.get("dob"):
        try:
            dob_val = dt_date.fromisoformat(str(content["dob"]))
        except ValueError:
            dob_val = None

    target_date_val = None
    raw_date_str = (
        str(
            content.get("target_date")
            or content.get("date")
            or content.get("appointment_date")
            or ""
        )
        .lower()
        .strip()
    )

    if raw_date_str:
        if raw_date_str in ["today", "now"]:
            target_date_val = clinic_date
        elif raw_date_str in ["tomorrow"]:
            target_date_val = clinic_date + datetime.timedelta(days=1)
        else:
            try:
                target_date_val = dt_date.fromisoformat(raw_date_str)
            except ValueError:
                target_date_val = None

    raw_time_str = (
        content.get("target_time")
        or content.get("time")
        or content.get("appointment_time")
    )

    return ExtractedCallIntent(
        intent=intent_val,
        action=str(content.get("action", "CHECK_AVAILABILITY")).upper(),
        extracted_name=content.get("extracted_name"),
        dob=dob_val,
        booking_for=content.get("booking_for"),
        specialty_or_complaint=content.get("specialty_or_complaint"),
        specialty_matched=content.get("specialty_matched"),
        requested_doctor_name=content.get("requested_doctor_name"),
        target_date=target_date_val,
        target_time=raw_time_str,
        time_context=content.get("time_context"),
        is_silent=bool(content.get("is_silent", False)),
    )
