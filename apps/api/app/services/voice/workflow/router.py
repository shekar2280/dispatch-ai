import re
from typing import Any


AFFIRMATIVE_TERMS = {
    "yes", "yeah", "yep", "sure", "correct", "please", "confirm",
    "book it", "sounds good", "okay", "ok", "go ahead", "that works",
    "fine", "perfect", "definitely", "absolutely", "yes please", "yes book it"
}

NEGATIVE_TERMS = {
    "no", "nope", "cancel", "don't", "dont", "not that", "neither",
    "wrong", "change it", "nevermind", "never mind", "no thanks"
}

EMERGENCY_TERMS = {
    "chest pain", "can't breathe", "cannot breathe", "difficulty breathing",
    "severe bleeding", "bleeding heavily", "stroke", "unconscious", "heart attack",
    "overdose", "suicide", "dying", "emergency", "ambulance", "call 911", "call 112"
}

TRANSFER_TERMS = {
    "speak to reception", "speak with reception", "talk to human", "speak to staff",
    "transfer me", "real person", "receptionist", "human operator", "talk to someone"
}

FAREWELL_TERMS = {
    "goodbye", "bye", "that's all", "thats all", "thank you bye",
    "have a good day", "have a nice day", "no that's all", "no thats all", "that is all"
}

WORD_TO_NUMBER = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "eleven": "11", "twelve": "12", "thirty": "30", "fifteen": "15", "forty-five": "45"
}


def normalize_utterance(text: str) -> str:
    cleaned = re.sub(r"[^\w\s:]", " ", (text or "").lower())
    return " ".join(cleaned.split())


def match_yes_no(text: str) -> bool | None:
    norm = normalize_utterance(text)
    if not norm:
        return None
    words = set(norm.split())
    has_aff = (norm in AFFIRMATIVE_TERMS
               or any(term in norm for term in ("book it", "sounds good", "go ahead", "yes please", "yes book", "yes cancel", "cancel it", "please cancel"))
               or any(word in AFFIRMATIVE_TERMS for word in words))
    neg_words = set(NEGATIVE_TERMS)
    if any(aff in norm for aff in ("yes cancel", "cancel it", "please cancel")):
        neg_words.discard("cancel")
    has_neg = (norm in neg_words
               or any(term in norm for term in ("never mind", "no thanks", "not that", "cancel that", "no cancel"))
               or any(word in neg_words for word in words)
               or "but" in words)
    if has_aff and not has_neg:
        return True
    if has_neg and not has_aff:
        return False
    if has_aff and has_neg:
        return False
    return None


def _extract_time_tuple(val: str) -> tuple[int, int] | None:
    norm = val.lower()
    for word, num in WORD_TO_NUMBER.items():
        norm = re.sub(rf"\b{word}\b", num, norm)
    m = re.search(r"(\d{1,2})(?:[:\s](\d{2}))?\s*(am|pm)?", norm)
    if not m:
        return None
    hr = int(m.group(1))
    mn = int(m.group(2) or 0)
    meridiem = m.group(3)
    if meridiem == "pm" and hr < 12:
        hr += 12
    elif meridiem == "am" and hr == 12:
        hr = 0
    return (hr, mn)


def match_offered_slot(text: str, candidate_slots: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidate_slots:
        return None
    norm = normalize_utterance(text)
    if not norm:
        return None
    if any(p in norm for p in ("first", "the first", "number one", "1st")):
        return candidate_slots[0]
    if len(candidate_slots) > 1 and any(p in norm for p in ("second", "the second", "number two", "2nd")):
        return candidate_slots[1]
    input_time = _extract_time_tuple(norm)
    for slot in candidate_slots:
        label = str(slot.get("label", ""))
        slot_time = _extract_time_tuple(label)
        if input_time and slot_time:
            if input_time == slot_time:
                return slot
            if input_time[0] % 12 == slot_time[0] % 12 and input_time[1] == slot_time[1]:
                return slot
        if normalize_utterance(label) in norm or norm in normalize_utterance(label):
            return slot
    return None


def match_emergency(text: str) -> bool:
    norm = normalize_utterance(text)
    return any(term in norm for term in EMERGENCY_TERMS)


def match_transfer(text: str) -> bool:
    norm = normalize_utterance(text)
    return any(term in norm for term in TRANSFER_TERMS)


def match_farewell(text: str) -> bool:
    norm = normalize_utterance(text)
    return any(term in norm for term in FAREWELL_TERMS)


def match_cancellation(text: str) -> bool:
    norm = normalize_utterance(text)
    return any(p in norm for p in ("cancel my appointment", "cancel appointment", "cancel booking"))


def match_reschedule(text: str) -> bool:
    norm = normalize_utterance(text)
    return any(p in norm for p in ("reschedule", "reschedule appointment", "change my appointment", "move my appointment"))


def match_faq(text: str) -> str | None:
    norm = normalize_utterance(text)
    if not norm:
        return None
    if any(k in norm for k in ("what are your hours", "what time do you open", "closing time", "opening hours", "when are you open")):
        return "hours"
    if any(k in norm for k in ("where are you located", "clinic address", "what is your address", "how to get there", "directions")):
        return "location"
    if any(k in norm for k in ("phone number", "contact number", "call reception")):
        return "phone"
    if any(k in norm for k in ("consultation fee", "how much is consultation", "cost of appointment", "doctor fee", "appointment fee")):
        return "fee"
    return None
