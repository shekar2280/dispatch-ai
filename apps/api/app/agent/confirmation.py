import re


def is_explicit_confirmation(text):
    value = " ".join(re.sub(r"[^a-z ]", "", text.casefold()).split())
    return value in {"yes", "yes please", "yes thats correct", "thats correct", "correct",
                     "yes correct", "yes book it", "please book it", "go ahead", "yes go ahead",
                     "confirm", "yes confirm", "that is correct", "yes that is correct",
                     "okay", "ok", "okay please", "ok please", "okay go ahead"}


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

