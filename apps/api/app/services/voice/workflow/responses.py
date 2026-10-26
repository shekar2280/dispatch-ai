from app.agent.prompt_builder import format_friendly_date


def slot_search_response(result: dict) -> str:
    doctor = result.get("doctor") or "The doctor"
    raw_date = result.get("spoken_date") or result.get("date") or ""
    date = format_friendly_date(raw_date) if raw_date else "that day"
    offers = [str(item.get("label")) for item in result.get("offers", []) if item.get("label")]
    requested_time = result.get("requested_time")

    if result.get("reason") == "PAST_TIME" and offers:
        return f"That time has already passed today. {doctor} has openings at {' or '.join(offers)}. Would either work?"
    if result.get("status") == "available":
        if requested_time and result.get("requested_time_available") is True:
            return f"{doctor} is available {date} at {requested_time}. Would you like that time?"
        if offers:
            joined = " or ".join(offers)
            return f"{doctor} has openings {date} at {joined}. Would either work for you?"

    if result.get("reason") == "INVALID_DATE":
        return "Which day would you like to come?"
    return "I could not find an available appointment time for that request. Would you like to try another day or speak with reception?"


def booking_readback_response(details: dict) -> str:
    name = " ".join(part for part in (details.get("first_name"), details.get("last_name")) if part).strip()
    doctor = details.get("doctor_name") or "the doctor"
    raw_date = details.get("spoken_date") or details.get("slot_date") or ""
    date = format_friendly_date(raw_date) if raw_date else "that day"
    time = details.get("slot_time") or "that time"
    return f"I have {name or 'you'} with {doctor} on {date} at {time}. Shall I book it?"


def booking_success_response(details: dict) -> str:
    doctor = details.get("doctor_name") or "the doctor"
    raw_date = details.get("spoken_date") or details.get("slot_date") or ""
    date = format_friendly_date(raw_date) if raw_date else "that day"
    time = details.get("slot_time") or "that time"
    return f"Your appointment with {doctor} on {date} at {time} is confirmed. We look forward to seeing you."


def clarify_name_response() -> str:
    return "May I have your first and last name for the booking?"


def cancellation_readback_response(details: dict) -> str:
    doctor = details.get("doctor_name") or "the doctor"
    raw_date = details.get("spoken_date") or details.get("slot_date") or ""
    date = format_friendly_date(raw_date) if raw_date else "that day"
    time = details.get("slot_time") or "that time"
    return f"Shall I cancel your appointment with {doctor} on {date} at {time}?"


def cancellation_success_response() -> str:
    return "Your appointment has been successfully cancelled."


def emergency_response(phone: str) -> str:
    return f"Please hang up and call {phone} immediately or go to the nearest emergency room."


def transfer_response(available: bool) -> str:
    if available:
        return "Transferring you to a staff member right now. Please hold."
    return "Our staff members are currently assisting other patients. Please leave a message or call back shortly."


def farewell_response() -> str:
    return "Thank you for calling. Have a wonderful day. Goodbye."


def generic_clarification_response() -> str:
    return "I can help you book, reschedule, or cancel an appointment, or check clinic hours. How can I assist you today?"
