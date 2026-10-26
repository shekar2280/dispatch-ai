import re


AFFIRMATIVE_TOKENS = {
    "yes", "yeah", "yep", "yup", "sure", "correct", "right", "confirm",
    "ok", "okay", "ahead", "please", "book", "fine", "perfect",
}


DISQUALIFYING_SUBSTRINGS = (
    "ignore instruction", "ignore previous", "system prompt",
)

DISQUALIFYING_WORDS = {
    "no", "nope", "not", "dont", "don't", "cancel", "wrong", "neither",
    "never", "nevermind", "but", "except", "instead", "change", "different",
    "probably", "maybe", "tomorrow", "yesterday",
}


def is_explicit_confirmation(text):
    if not text:
        return False
    lower = text.strip().lower()
    for sub in DISQUALIFYING_SUBSTRINGS:
        if sub in lower:
            return False
    words = re.sub(r"[^a-z ]", " ", lower).split()
    if not words:
        return False
    word_set = set(words)
    if word_set & DISQUALIFYING_WORDS:
        return False
    from app.services.voice.workflow.router import match_yes_no
    yn = match_yes_no(text)
    if yn is True:
        return True
    if yn is False:
        return False
    return bool(word_set & AFFIRMATIVE_TOKENS)


def matches_proposal_readback(proposal, text):
    if not proposal or not text:
        return False
    lower = text.lower()
    matches = 0
    name = str(proposal.get("name", "")).strip().lower()
    if name and len(name) > 1 and name in lower:
        matches += 1
    first = str(proposal.get("first_name", "")).strip().lower()
    if first and len(first) > 1 and first in lower:
        matches += 1
    last = str(proposal.get("last_name", "")).strip().lower()
    if last and len(last) > 1 and last in lower:
        matches += 1
    time_val = str(proposal.get("slot_time") or proposal.get("time", "")).strip().lower()
    if time_val:
        clean_time = time_val.lstrip("0")
        if clean_time and (clean_time in lower or time_val in lower):
            matches += 1
    date_val = str(proposal.get("slot_date") or proposal.get("date", "")).strip().lower()
    if date_val and (date_val in lower or "today" in lower or "tomorrow" in lower):
        matches += 1
    doc = str(proposal.get("doctor_name", "")).strip().lower()
    for prefix in ("dr. ", "dr ", "doctor "):
        if doc.startswith(prefix):
            doc = doc[len(prefix):]
            break
    if doc and len(doc) > 1 and doc in lower:
        matches += 1
    mode = str(proposal.get("booking_mode", "")).strip().lower()
    if mode == "queue" and any(k in lower for k in ("queue", "walk-in", "token", "today")):
        matches += 1
    return matches >= 2


class ConfirmationGate:
    def __init__(self):
        self.turn_id = None
        self.text = ""
        self.proposal = None
        self.proposal_turn = None
        self.readback_turn = None

    def observe(self, turn_id, text):
        self.turn_id, self.text = turn_id, text

    def propose(self, payload):
        self.proposal, self.proposal_turn = dict(payload), self.turn_id
        self.readback_turn = None

    def readback(self, event_id, spoken_text=None, interrupted=False):
        if self.proposal and not interrupted:
            if spoken_text is not None and not matches_proposal_readback(self.proposal, spoken_text):
                return
            self.readback_turn = event_id

    def permits(self, payload):
        return (self.proposal == payload and self.readback_turn is not None and self.turn_id is not None
                and self.turn_id != self.proposal_turn and is_explicit_confirmation(self.text))

