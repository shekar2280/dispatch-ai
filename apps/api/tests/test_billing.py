"""Regression tests for billing."""

import asyncio
import zoneinfo
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.security import get_current_tenant_org, get_current_user
from app.main import app
from app.models.appointment import Appointment
from app.models.clinic_membership import ClinicMembership
from app.models.organization import Organization
from app.models.patient import Patient
from app.models.payment_receipt import PaymentReceipt
from app.models.user import User
from app.schemas.appointment import BillItem, ClinicCheckInRequest, ClinicPaymentUpdate, ClinicWalkinBookingRequest
from app.services.appointments.booking_service import build_capacity_blocks, capacity_window
from app.services.appointments.intake import validate_intake
from app.services.appointments.queue_service import get_ordered_active_queue
from app.services.billing.payment_service import (
    calculate_bill,
    collect_appointment_fee,
    get_clinic_revenue_data,
    list_visit_payment_receipts_service,
    money,
)


def _make_test_org(org_id=None):
    return Organization(
        id=org_id or uuid4(),
        name="Apex Diagnostics & Clinic",
        timezone="Asia/Kolkata",
        booking_settings={
            "consultation_fee": 500,
            "booking_mode": "hybrid",
        },
    )


def _make_test_user(user_id=None, org_id=None):
    return User(
        id=user_id or uuid4(),
        email="cashier@apexclinic.com",
        full_name="Pooja Sharma",
        role="receptionist",
        org_id=org_id or uuid4(),
        is_active=True,
    )


@pytest.mark.anyio
async def test_collect_fee_consultation_plus_diagnostic_receipt_e2e():
    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    today = datetime.now(tz).date()
    org_id = uuid4()
    cashier_id = uuid4()
    org = _make_test_org(org_id)
    cashier = _make_test_user(cashier_id, org_id)

    patient = Patient(
        id=uuid4(),
        org_id=org_id,
        first_name="Ananya",
        last_name="Rao",
        phone_number="+919876511111",
    )

    start_dt = datetime(today.year, today.month, today.day, 10, 30, tzinfo=tz)
    end_dt = start_dt + timedelta(minutes=15)
    appointment = Appointment(
        id=uuid4(),
        org_id=org_id,
        patient_id=patient.id,
        start_time=start_dt,
        end_time=end_dt,
        source="walk_in",
        status="completed",
        queue_state="served",
        encounter_state="completed",
    )
    appointment.fee = 500
    appointment.payment_status = "pending"
    appointment.booking_metadata = {}

    db = AsyncMock()

    async def _mock_get(model, obj_id):
        if model is Appointment and obj_id == appointment.id:
            return appointment
        if model is Organization and obj_id == org_id:
            return org
        return None

    db.get.side_effect = _mock_get
    db.scalar.side_effect = [appointment, 0.0]

    recorded_receipts = []

    def _sync_add(instance):
        if isinstance(instance, PaymentReceipt):
            instance.id = uuid4()
            instance.received_at = datetime.now(tz)
            recorded_receipts.append(instance)

    db.add = MagicMock(side_effect=_sync_add)

    req = ClinicPaymentUpdate(
        idempotency_key="test-step3-pay-1",
        payment_status="paid",
        payment_method="UPI",
        fee=800.0,
        amount_received=800.0,
        reference="UPI-REF-9928172",
        bill_items=[
            BillItem(name="Consultation", amount=500.0, category="consultation"),
            BillItem(name="CBC Blood Test", amount=300.0, category="diagnostic"),
        ],
    )

    res = await collect_appointment_fee(
        db=db,
        appointment_id=appointment.id,
        req=req,
        org_id=org_id,
        received_by_id=cashier.id,
    )

    assert appointment.fee == 800
    assert appointment.payment_status == "paid"
    assert appointment.payment_method == "UPI"
    assert len(recorded_receipts) == 1
    receipt = recorded_receipts[0]
    assert receipt.amount == 800.0
    assert receipt.method == "UPI"
    assert receipt.reference == "UPI-REF-9928172"
    assert receipt.received_by == cashier.id
    assert appointment.booking_metadata.get("collected_at") is not None
    assert len(appointment.booking_metadata.get("bill_items", [])) == 2


@pytest.mark.anyio
async def test_revenue_endpoint_increments_and_aggregates_properly():
    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    today = datetime.now(tz).date()
    org_id = uuid4()
    org = _make_test_org(org_id)
    cashier = _make_test_user(org_id=org_id)

    patient = Patient(
        id=uuid4(),
        org_id=org_id,
        first_name="Ananya",
        last_name="Rao",
        phone_number="+919876511111",
    )

    now_local = datetime.now(tz)
    start_dt = datetime(today.year, today.month, today.day, 10, 30, tzinfo=tz)
    end_dt = start_dt + timedelta(minutes=15)
    appointment = Appointment(
        id=uuid4(),
        org_id=org_id,
        patient_id=patient.id,
        start_time=start_dt,
        end_time=end_dt,
        source="walk_in",
        status="completed",
    )
    appointment.fee = 800
    appointment.payment_status = "paid"
    appointment.payment_method = "UPI"
    appointment.booking_metadata = {
        "collected_at": now_local.isoformat(),
        "bill_items": [
            {"name": "Consultation", "amount": 500.0},
            {"name": "Diagnostic", "amount": 300.0},
        ],
    }

    receipt = PaymentReceipt(
        id=uuid4(),
        org_id=org_id,
        visit_id=appointment.id,
        amount=800.0,
        method="UPI",
        reference="UPI-REF-9928172",
        received_at=now_local,
        received_by=cashier.id,
    )

    db = AsyncMock()

    async def _mock_get(model, obj_id):
        if model is Organization and obj_id == org_id:
            return org
        return None

    db.get.side_effect = _mock_get

    mock_execute_query = MagicMock()
    mock_execute_query.all.return_value = [(appointment, patient)]

    mock_execute_receipts = MagicMock()
    mock_execute_receipts.scalars.return_value.all.return_value = [receipt]

    db.execute.side_effect = [mock_execute_query, mock_execute_receipts]

    rev_data = await get_clinic_revenue_data(db, org_id=org_id, period="today")

    assert rev_data["total_settled"] == 800.0
    assert rev_data["upi_total"] == 800.0
    assert rev_data["cash_total"] == 0.0
    assert rev_data["total_pending"] == 0.0
    assert len(rev_data["transactions"]) == 1
    txn = rev_data["transactions"][0]
    assert txn["id"] == str(appointment.id)
    assert txn["patient_name"] == "Ananya Rao"
    assert txn["fee_amount"] == 800
    assert txn["amount_paid"] == 800.0
    assert txn["balance_due"] == 0.0
    assert txn["status"] == "settled"
    assert txn["payment_method"] == "UPI"


@pytest.mark.anyio
async def test_payment_audit_ledger_lists_receipt_with_timestamp_and_cashier():
    org_id = uuid4()
    appt_id = uuid4()
    cashier_id = uuid4()
    cashier_name = "Pooja Sharma"

    appointment = Appointment(
        id=appt_id,
        org_id=org_id,
        start_time=datetime(2026, 10, 6, 10, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Kolkata")),
        end_time=datetime(2026, 10, 6, 10, 15, tzinfo=zoneinfo.ZoneInfo("Asia/Kolkata")),
        source="walk_in",
    )

    receipt_timestamp = datetime(2026, 10, 6, 11, 15, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Kolkata"))
    receipt = PaymentReceipt(
        id=uuid4(),
        org_id=org_id,
        visit_id=appt_id,
        amount=800.0,
        method="UPI",
        reference="UPI-REF-9928172",
        received_at=receipt_timestamp,
        received_by=cashier_id,
    )

    db = AsyncMock()
    db.scalar.return_value = appointment

    mock_exec = MagicMock()
    mock_exec.all.return_value = [(receipt, cashier_name)]
    db.execute.return_value = mock_exec

    receipts = await list_visit_payment_receipts_service(db, org_id=org_id, appointment_id=appt_id)

    assert len(receipts) == 1
    r = receipts[0]
    assert r["id"] == str(receipt.id)
    assert r["visit_id"] == str(appt_id)
    assert r["amount"] == 800.0
    assert r["method"] == "UPI"
    assert r["reference"] == "UPI-REF-9928172"
    assert r["received_at"] == receipt_timestamp
    assert r["received_by"] == str(cashier_id)
    assert r["received_by_name"] == cashier_name


@pytest.mark.anyio
async def test_partial_payment_and_overpayment_protection():
    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    org_id = uuid4()
    org = _make_test_org(org_id)
    cashier = _make_test_user(org_id=org_id)

    appointment = Appointment(
        id=uuid4(),
        org_id=org_id,
        start_time=datetime.now(tz),
        end_time=datetime.now(tz) + timedelta(minutes=15),
    )
    appointment.status = "completed"
    appointment.fee = 800
    appointment.payment_status = "pending"
    appointment.booking_metadata = {}

    db = AsyncMock()

    async def _mock_get(model, obj_id):
        if model is Appointment:
            return appointment
        if model is Organization:
            return org
        return None

    db.get.side_effect = _mock_get
    db.scalar.side_effect = [appointment, 0.0, appointment, 0.0]

    recorded_receipts = []
    db.add = MagicMock(
        side_effect=lambda inst: recorded_receipts.append(inst) if isinstance(inst, PaymentReceipt) else None
    )

    overpay_req = ClinicPaymentUpdate(
        idempotency_key="test-step3-overpay-1",
        payment_status="paid",
        payment_method="Cash",
        amount_received=1000.0,
    )
    with pytest.raises(HTTPException) as exc_info:
        await collect_appointment_fee(
            db=db,
            appointment_id=appointment.id,
            req=overpay_req,
            org_id=org_id,
            received_by_id=cashier.id,
        )
    assert exc_info.value.status_code == 422
    assert "no more than the outstanding balance" in exc_info.value.detail

    partial_req = ClinicPaymentUpdate(
        idempotency_key="test-step3-partial-1",
        payment_status="paid",
        payment_method="Cash",
        amount_received=500.0,
    )
    res_partial = await collect_appointment_fee(
        db=db,
        appointment_id=appointment.id,
        req=partial_req,
        org_id=org_id,
        received_by_id=cashier.id,
    )
    assert appointment.payment_status == "pending"
    assert appointment.payment_method == "partial"
    assert len(recorded_receipts) == 1
    assert recorded_receipts[0].amount == 500.0


def run_async(coroutine):
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        return runner.run(coroutine)


def patient():
    return Patient(first_name="Anita", last_name="Rao", phone_number="+919876543210", medical_history={})


def test_reported_age_preserves_unknown_dob():
    record = patient()
    snapshot = validate_intake(record, ClinicCheckInRequest(reported_age=32), date(2026, 10, 6))
    assert record.dob is None
    assert snapshot == {"value": 32, "unit": "years", "recorded_at": "2026-10-06"}


@pytest.mark.parametrize(
    "payload", [{}, {"patient_phone": "123", "reported_age": 20}, {"dob": date(2099, 1, 1)}, {"reported_age": 131}]
)
def test_invalid_intake_rejected(payload):
    with pytest.raises(HTTPException):
        validate_intake(patient(), ClinicCheckInRequest(**payload), date(2026, 10, 6))


def test_infant_months_and_guardian_phone():
    record = patient()
    validate_intake(record, ClinicCheckInRequest(reported_age=3, age_unit="months"), date(2026, 10, 6))
    assert record.medical_history["reported_age"]["unit"] == "months"


def test_quarter_hour_choices_share_capacity():
    blocks = build_capacity_blocks(
        date(2026, 10, 6),
        {"tuesday": {"isOpen": True, "windows": [{"start": "07:00 PM", "end": "08:00 PM"}]}},
        30,
        ZoneInfo("Asia/Kolkata"),
        15,
    )
    assert len(blocks) == 4
    assert capacity_window(blocks[0]["start"], 30) == capacity_window(blocks[1]["start"], 30)


def test_fifo_ignores_booking_type_and_token_priority():
    now = datetime.now(timezone.utc)
    earlier = SimpleNamespace(
        id=uuid4(),
        status="arrived",
        queue_state="waiting",
        booking_metadata={},
        checked_in_at=now - timedelta(minutes=10),
        created_at=now,
        token_number=5,
    )
    later = SimpleNamespace(
        id=uuid4(),
        status="arrived",
        queue_state="waiting",
        booking_metadata={},
        checked_in_at=now,
        created_at=now,
        token_number=1,
    )
    db = MagicMock()
    db.get = AsyncMock(return_value=SimpleNamespace(timezone="Asia/Kolkata"))
    result = MagicMock()
    result.scalars.return_value.all.return_value = [later, earlier]
    db.execute = AsyncMock(return_value=result)
    assert run_async(get_ordered_active_queue(db, uuid4(), doctor_id=uuid4())) == [earlier, later]
    assert "doctor_id" in str(db.execute.call_args.args[0])


def test_decimal_bill_and_item_validation():
    total, _ = calculate_bill([BillItem(name="Medicine", amount=25.5, quantity=3, unit_price=8.5)])
    assert total == Decimal("25.50")
    with pytest.raises(HTTPException):
        calculate_bill([BillItem(name="Medicine", amount=30, quantity=3, unit_price=8.5)])
    with pytest.raises(HTTPException):
        money("1.001")


def billing_db(visit, paid=0):
    db = MagicMock()
    db.scalar = AsyncMock(side_effect=[visit, Decimal(str(paid))])
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.add.side_effect = lambda receipt: setattr(receipt, "id", uuid4())
    return db


def test_partial_collection_retry_does_not_duplicate_receipt():
    visit = Appointment(id=uuid4(), org_id=uuid4(), status="completed", fee=100)
    req = ClinicPaymentUpdate(
        idempotency_key=str(uuid4()), payment_status="paid", payment_method="Cash", amount_received=40
    )
    db = billing_db(visit)
    result = run_async(collect_appointment_fee(db, visit.id, req, visit.org_id))
    assert result["balance_due"] == 60
    assert result["payment_status"] == "pending"
    assert db.add.call_count == 1
    assert "FOR UPDATE" in str(db.scalar.call_args_list[0].args[0])
    retry_db = billing_db(visit)
    assert run_async(collect_appointment_fee(retry_db, visit.id, req, visit.org_id)) == result
    retry_db.add.assert_not_called()


def test_no_collection_before_completion_or_beyond_balance():
    visit = Appointment(id=uuid4(), org_id=uuid4(), status="arrived", fee=100)
    req = ClinicPaymentUpdate(
        idempotency_key=str(uuid4()), payment_status="paid", payment_method="Cash", amount_received=50
    )
    with pytest.raises(HTTPException):
        run_async(collect_appointment_fee(billing_db(visit), visit.id, req, visit.org_id))
    visit.status = "completed"
    with pytest.raises(HTTPException):
        run_async(collect_appointment_fee(billing_db(visit, 80), visit.id, req, visit.org_id))


def test_zero_bill_has_no_fake_receipt():
    visit = Appointment(id=uuid4(), org_id=uuid4(), status="completed", fee=0)
    db = billing_db(visit)
    result = run_async(
        collect_appointment_fee(
            db, visit.id, ClinicPaymentUpdate(idempotency_key=str(uuid4()), payment_status="paid"), visit.org_id
        )
    )
    assert result["payment_status"] == "paid"
    assert result["bill_finalized_at"]
    db.add.assert_not_called()


@pytest.mark.parametrize("request_type", [ClinicCheckInRequest, ClinicWalkinBookingRequest])
def test_optional_patient_details_are_saved_and_preserved(request_type):
    record = patient()
    details = {
        "patient_name": "Anita Rao",
        "patient_phone": record.phone_number,
        "reported_age": 32,
        "gender": "female",
        "blood_group": "O+",
        "address": "  12 Park Road, Pune  ",
    }
    if request_type is ClinicWalkinBookingRequest:
        details["appointment_date"] = date(2026, 10, 9)
    validate_intake(record, request_type(**details), date(2026, 10, 9))
    assert (record.gender, record.blood_group, record.address) == ("female", "O+", "12 Park Road, Pune")
    validate_intake(record, ClinicCheckInRequest(reported_age=32), date(2026, 10, 9))
    assert (record.gender, record.blood_group, record.address) == ("female", "O+", "12 Park Road, Pune")
