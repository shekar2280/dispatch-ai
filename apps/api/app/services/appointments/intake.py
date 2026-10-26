from datetime import date
from fastapi import HTTPException
from app.core.phone_utils import normalize_phone_e164


def validate_intake(patient, request, today: date):
    requested_name = getattr(request, "patient_name", None)
    if requested_name is not None:
        normalized_name = " ".join(requested_name.split())
        if not normalized_name:
            raise HTTPException(422, "Enter the patient's name before checking in")
        # Voice transcription is only a starting point. Reception confirms the
        # identity in person and may correct the patient profile at check-in.
        first_name, *remaining_name = normalized_name.split(" ", 1)
        patient.first_name = first_name
        patient.last_name = remaining_name[0] if remaining_name else ""
    phone = getattr(request, "patient_phone", None) or patient.phone_number
    normalized = normalize_phone_e164(phone or "")
    if not normalized.is_valid:
        raise HTTPException(422, "A valid patient or guardian contact number is required")
    requested_dob = getattr(request, "dob", None)
    if requested_dob and patient.dob and requested_dob != patient.dob:
        raise HTTPException(409, "Date of birth differs from the selected patient profile")
    dob = requested_dob or patient.dob
    history = dict(patient.medical_history or {})
    age = getattr(request, "reported_age", None)
    unit = getattr(request, "age_unit", None) or "years"
    if dob:
        if dob > today or (today.year - dob.year) > 130:
            raise HTTPException(422, "Enter a valid date of birth")
        snapshot = {"dob": dob.isoformat(), "recorded_at": today.isoformat()}
    elif age is not None:
        if age < 0 or age > (1560 if unit == "months" else 130) or unit not in {"months", "years"}:
            raise HTTPException(422, "Enter a valid age and unit")
        snapshot = {"value": age, "unit": unit, "recorded_at": today.isoformat()}
        history["reported_age"] = snapshot
    else:
        raise HTTPException(422, "Age or date of birth is required at check-in")
    patient.phone_number = normalized.e164_phone
    patient.dob = dob
    patient.medical_history = history
    for field in ("gender", "blood_group", "address"):
        value = getattr(request, field, None)
        if value and value.strip():
            setattr(patient, field, value.strip())
    return snapshot
