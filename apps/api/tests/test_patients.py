"""Regression tests for patients."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.api.v1.clinic_dashboard import _redact_clinical
from app.models.call_session import CallLog
from app.models.patient import Patient
from app.services.appointments.booking_service import _resolve_patient
from app.services.appointments.schedule_service import lookup_patients
from app.services.patients.notes_service import save_patient_ehr_note_service
from app.services.patients.patient_service import get_patient_by_phone
from app.services.telephony.call_session_service import get_daily_call_logs
from app.services.voice.handlers import clinic_tool_handler as handler


def _create_mock_patient(org_id, first_name, last_name, phone="+919876543210", dob=None):
    return Patient(
        id=uuid4(),
        org_id=org_id,
        first_name=first_name,
        last_name=last_name,
        phone_number=phone,
        dob=dob,
        medical_history={"visits": ["Routine Checkup"]},
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.anyio
async def test_shared_phone_family_members_create_distinct_patient_records():
    org_id = uuid4()
    mother = _create_mock_patient(org_id, "Sunita", "Sharma")

    db = AsyncMock()
    first_query = MagicMock()
    first_query.scalars.return_value.all.return_value = [mother]
    db.execute.return_value = first_query
    db.add = MagicMock()
    db.flush = AsyncMock()

    req_son = SimpleNamespace(
        patient_id=None,
        patient_name="Rohan Sharma",
        dob=None,
    )

    resolved_son = await _resolve_patient(db, org_id, req_son, "+919876543210")

    assert db.add.called
    added_patient = db.add.call_args[0][0]
    assert added_patient.first_name == "Rohan"
    assert added_patient.last_name == "Sharma"
    assert added_patient.phone_number == "+919876543210"
    assert added_patient.id != mother.id
    assert mother.first_name == "Sunita"


@pytest.mark.anyio
async def test_repeat_visit_links_to_existing_patient_without_duplication():
    org_id = uuid4()
    patient_a = _create_mock_patient(org_id, "Sunita", "Sharma")

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [patient_a]
    db.execute.return_value = mock_result
    db.add = MagicMock()

    req_repeat = SimpleNamespace(
        patient_id=None,
        patient_name="Sunita Sharma",
        dob=None,
    )

    resolved = await _resolve_patient(db, org_id, req_repeat, "+919876543210")

    assert resolved.id == patient_a.id
    assert resolved.first_name == "Sunita"
    assert not db.add.called


@pytest.mark.anyio
async def test_cross_tenant_isolation_prevents_patient_leak():
    clinic_a_id = uuid4()
    clinic_b_id = uuid4()

    patient_clinic_a = _create_mock_patient(clinic_a_id, "Sunita", "Sharma")

    db_clinic_b = AsyncMock()
    mock_res_empty = MagicMock()
    mock_res_empty.scalars.return_value.all.return_value = []
    db_clinic_b.execute.return_value = mock_res_empty
    db_clinic_b.scalar.return_value = None

    req_lookup_b = SimpleNamespace(
        patient_id=patient_clinic_a.id,
        patient_name="Sunita Sharma",
        dob=None,
    )

    with pytest.raises(HTTPException) as exc:
        await _resolve_patient(db_clinic_b, clinic_b_id, req_lookup_b, "+919876543210")

    assert exc.value.status_code == 404
    assert "not found in this clinic" in exc.value.detail


@pytest.mark.anyio
async def test_name_whitespace_and_casing_normalization():
    org_id = uuid4()
    patient = _create_mock_patient(org_id, "Sunita", "Sharma")

    db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [patient]
    db.execute.return_value = mock_res
    db.add = MagicMock()

    req_normalized = SimpleNamespace(
        patient_id=None,
        patient_name="   suNiTA     shARma   ",
        dob=None,
    )

    resolved = await _resolve_patient(db, org_id, req_normalized, "+919876543210")
    assert resolved.id == patient.id
    assert not db.add.called


@pytest.mark.anyio
async def test_duplicate_matching_profiles_triggers_conflict_exception():
    org_id = uuid4()
    profile_1 = _create_mock_patient(org_id, "Sunita", "Sharma")
    profile_2 = _create_mock_patient(org_id, "Sunita", "Sharma")

    db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [profile_1, profile_2]
    db.execute.return_value = mock_res

    req = SimpleNamespace(
        patient_id=None,
        patient_name="Sunita Sharma",
        dob=None,
    )

    with pytest.raises(HTTPException) as exc:
        await _resolve_patient(db, org_id, req, "+919876543210")

    assert exc.value.status_code == 409
    assert "Multiple patient profiles match" in exc.value.detail


@pytest.mark.anyio
async def test_single_name_patient_handled_safely():
    org_id = uuid4()
    db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    db.execute.return_value = mock_res
    db.add = MagicMock()
    db.flush = AsyncMock()

    req = SimpleNamespace(
        patient_id=None,
        patient_name="Kabir",
        dob=None,
    )

    resolved = await _resolve_patient(db, org_id, req, "+919876543210")
    assert db.add.called
    added = db.add.call_args[0][0]
    assert added.first_name == "Kabir"
    assert added.last_name == ""


@pytest.mark.anyio
async def test_same_name_and_phone_differentiated_by_dob():
    org_id = uuid4()
    senior = _create_mock_patient(org_id, "Raj", "Malhotra", dob=date(1965, 5, 12))
    junior = _create_mock_patient(org_id, "Raj", "Malhotra", dob=date(1995, 8, 24))

    db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [senior, junior]
    db.execute.return_value = mock_res

    req_junior = SimpleNamespace(
        patient_id=None,
        patient_name="Raj Malhotra",
        dob=date(1995, 8, 24),
    )

    resolved = await _resolve_patient(db, org_id, req_junior, "+919876543210")
    assert resolved.id == junior.id
    assert resolved.dob == date(1995, 8, 24)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_patient_note_has_author_and_date_without_changing_a_visit():
    org_id, patient_id, author_id = uuid4(), uuid4(), uuid4()
    patient = SimpleNamespace(id=patient_id, org_id=org_id, medical_history={"notes": ["Earlier note"]})
    db = SimpleNamespace(scalar=AsyncMock(return_value=patient), commit=AsyncMock(), refresh=AsyncMock())
    result = await save_patient_ehr_note_service(
        db, org_id, patient_id, "  Follow up next week.  ", author_id, "Dr. Test"
    )
    entry = patient.medical_history["note_entries"][0]
    assert entry["text"] == "Follow up next week."
    assert entry["author_id"] == str(author_id)
    assert entry["author_name"] == "Dr. Test"
    assert datetime.fromisoformat(entry["created_at"]).tzinfo is not None
    assert patient.medical_history["notes"] == ["Follow up next week.", "Earlier note"]
    query = db.scalar.call_args.args[0].compile(dialect=postgresql.dialect())
    assert query.params["org_id_1"] == org_id
    assert query.params["id_1"] == patient_id
    assert "FOR UPDATE" in str(query)
    db.scalar.assert_awaited_once()  # No arbitrary latest-appointment lookup or mutation.
    assert result["status"] == "saved"


@pytest.mark.anyio
async def test_retried_note_does_not_create_duplicate_entries():
    patient = SimpleNamespace(id=uuid4(), medical_history={})
    db = SimpleNamespace(scalar=AsyncMock(return_value=patient), commit=AsyncMock(), refresh=AsyncMock())
    await save_patient_ehr_note_service(db, uuid4(), patient.id, "Care plan")
    await save_patient_ehr_note_service(db, uuid4(), patient.id, "Care plan")
    assert len(patient.medical_history["note_entries"]) == 1
    assert patient.medical_history["notes"] == ["Care plan"]


@pytest.mark.anyio
@pytest.mark.parametrize("note", ["   ", "x" * 5001])
async def test_invalid_notes_are_rejected_without_commit(note):
    patient = SimpleNamespace(id=uuid4(), medical_history={})
    db = SimpleNamespace(scalar=AsyncMock(return_value=patient), commit=AsyncMock())
    with pytest.raises(HTTPException) as error:
        await save_patient_ehr_note_service(db, uuid4(), patient.id, note)
    assert error.value.status_code == 422
    db.commit.assert_not_awaited()


def test_note_metadata_and_visit_clinical_fields_are_redacted_for_non_clinicians():
    data = {
        "note_entries": [{"text": "Private note", "author_name": "Doctor"}],
        "visit_history": [
            {"date": "2026-10-17", "status": "completed", "doctor_notes": "Private", "diagnosis": "Private"}
        ],
    }
    redacted = _redact_clinical(data)
    assert "note_entries" not in redacted
    assert redacted["visit_history"] == [{"date": "2026-10-17", "status": "completed"}]


PHONE = "+919876543210"


def rows(items):
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    return result


@pytest.mark.anyio
async def test_phone_only_lookup_refuses_shared_contact():
    db = SimpleNamespace(execute=AsyncMock(return_value=rows([object(), object()])))
    with pytest.raises(HTTPException) as error:
        await get_patient_by_phone(db, PHONE, uuid4())
    assert error.value.status_code == 409


@pytest.mark.anyio
@pytest.mark.parametrize(
    "names,expected",
    [
        (["Marcus", "Maya"], "Marcus"),
        (["Maya", "Marcus"], "Marcus"),
        (["Marcus", "Marcus"], None),
    ],
)
async def test_voice_matches_person_not_first_result_at_phone(names, expected):
    patients = [SimpleNamespace(id=uuid4(), first_name=name, last_name="Rashford") for name in names]
    db = SimpleNamespace(execute=AsyncMock(return_value=rows(patients)))
    patient, ambiguous = await handler._find_named_patient(db, uuid4(), PHONE, "Marcus", "Rashford")
    assert (patient.first_name if patient else None) == expected
    assert ambiguous is (expected is None)


@pytest.mark.anyio
@pytest.mark.parametrize("same_patient", [True, False])
async def test_voice_changes_require_specific_verified_patient(same_patient):
    patient_id = uuid4()
    call = SimpleNamespace(patient_id=patient_id if same_patient else uuid4(), caller_phone=PHONE)
    db = SimpleNamespace(scalar=AsyncMock(return_value=call))
    assert await handler._call_has_verified_patient(db, uuid4(), uuid4(), patient_id, PHONE) is same_patient


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["_reschedule", "_cancel"])
async def test_shared_phone_does_not_authorize_other_patient_appointment(operation):
    appt = SimpleNamespace(patient_id=uuid4(), id=uuid4())
    result = MagicMock()
    result.scalar_one_or_none.return_value = appt
    call = SimpleNamespace(patient_id=uuid4(), caller_phone=PHONE)
    db = SimpleNamespace(execute=AsyncMock(return_value=result), scalar=AsyncMock(return_value=call))
    args = {
        "appointment_id": str(appt.id),
        "new_date": (date.today() + timedelta(days=5)).isoformat(),
        "new_time": "10:00",
    }
    with (
        patch.object(handler, "reschedule_clinic_appointment", new_callable=AsyncMock) as reschedule,
        patch.object(handler, "cancel_clinic_appointment", new_callable=AsyncMock) as cancel,
    ):
        if operation == "_reschedule":
            response = await handler._reschedule(
                args, db, uuid4(), SimpleNamespace(timezone="Asia/Kolkata"), PHONE, uuid4()
            )
        else:
            response = await handler._cancel(args, db, uuid4(), PHONE, uuid4())
        assert response["status"] == "verification_required"
        reschedule.assert_not_awaited()
        cancel.assert_not_awaited()


@pytest.mark.anyio
async def test_verified_patient_is_bound_to_call_without_renaming_caller():
    patient = SimpleNamespace(id=uuid4(), first_name="Marcus", last_name="Rashford", dob=None)
    call = SimpleNamespace(patient_id=None, caller_phone=PHONE, caller_name="Family Contact")
    db = SimpleNamespace(
        execute=AsyncMock(return_value=rows([])), scalar=AsyncMock(return_value=call), commit=AsyncMock()
    )
    with patch.object(handler, "_find_named_patient", new_callable=AsyncMock, return_value=(patient, False)):
        response = await handler._verify_patient(
            {"first_name": "Marcus", "last_name": "Rashford"},
            db,
            uuid4(),
            SimpleNamespace(timezone="Asia/Kolkata"),
            PHONE,
            uuid4(),
        )
    assert response["verified"] is True
    assert call.patient_id == patient.id
    assert call.caller_name == "Family Contact"
    db.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_call_logs_preserve_each_caller_and_join_patient_by_id():
    org_id, marcus_id, maya_id = uuid4(), uuid4(), uuid4()
    calls = [
        CallLog(
            id=uuid4(),
            org_id=org_id,
            caller_phone=PHONE,
            caller_name=name,
            patient_id=patient_id,
            start_time=datetime.now(timezone.utc),
            duration_seconds=0,
            call_outcome="caller_abandoned",
            triage_status="missed",
        )
        for name, patient_id in [("Marcus Rashford", None), ("Maya Rashford", maya_id), ("Family Contact", marcus_id)]
    ]
    patients = [
        Patient(id=maya_id, org_id=org_id, first_name="Maya", last_name="Rashford"),
        Patient(id=marcus_id, org_id=org_id, first_name="Marcus", last_name="Rashford"),
    ]
    db = SimpleNamespace(execute=AsyncMock(return_value=rows(patients)))
    maker = MagicMock()
    maker.return_value.__aenter__ = AsyncMock(return_value=db)
    maker.return_value.__aexit__ = AsyncMock(return_value=False)
    with patch(
        "app.services.telephony.call_session_service.load_call_page",
        new_callable=AsyncMock,
        return_value=(calls, set(), {}, {"all": 3}),
    ):
        result = await get_daily_call_logs(str(org_id), session_factory=maker)
    assert [item["caller_name"] for item in result["logs"]] == ["Marcus Rashford", "Maya Rashford", "Family Contact"]
    assert [item["patient_name"] for item in result["logs"]] == [None, "Maya Rashford", "Marcus Rashford"]
    assert result["logs"][0]["patient_id"] is None
