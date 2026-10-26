import os
import zoneinfo
from datetime import date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.future import select

from app.core.database import get_db
from app.core.security import get_current_tenant_org, get_current_user
from app.main import app
from app.models.appointment import Appointment
from app.models.organization import Organization
from app.models.patient import Patient
from app.models.payment_receipt import PaymentReceipt
from app.models.user import User
from app.services.appointments.booking_service import book_appointment_atomic
from tests.database_support import get_test_database_url

pytestmark = pytest.mark.live


from sqlalchemy.pool import NullPool


@pytest.fixture
def session_maker():
    db_url = get_test_database_url()
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(
        db_url,
        echo=False,
        poolclass=NullPool,
        connect_args={"statement_cache_size": 0},
    )
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield maker
    engine.sync_engine.dispose()


@pytest.fixture(autouse=True)
def override_db_dependency(session_maker):
    async def _get_test_db():
        async with session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _get_test_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
async def main_clinic_context(session_maker):
    async with session_maker() as db:
        org = await db.get(Organization, UUID(os.environ["TEST_ORG_ID"]))
        staff = await db.get(User, UUID(os.environ["TEST_STAFF_USER_ID"]))
        doctor = await db.get(User, UUID(os.environ["TEST_DOCTOR_ID"]))
    assert org and staff and doctor, "Configure existing synthetic clinic accounts in the test database"
    return {
        "org": org,
        "staff": staff,
        "doctor": doctor,
    }


@pytest.mark.anyio
async def test_real_postgres_authenticated_patient_isolation(main_clinic_context, session_maker):
    org_a = main_clinic_context["org"]
    staff_a = main_clinic_context["staff"]

    org_b_id = uuid4()
    org_b_slug = f"clinic-b-{uuid4().hex[:6]}"
    org_b = Organization(
        id=org_b_id,
        name=f"Clinic B Isolation {uuid4().hex[:6]}",
        slug=org_b_slug,
        timezone="Asia/Kolkata",
        country_code="IN",
        booking_settings={"consultation_fee": 500},
    )

    patient_phone = f"+9198{uuid4().int % 100000000:08d}"
    patient_a = Patient(
        id=uuid4(),
        org_id=org_a.id,
        first_name="Ravi",
        last_name="Shankar",
        phone_number=patient_phone,
    )

    async with session_maker() as db:
        db.add(org_b)
        db.add(patient_a)
        await db.commit()

    try:
        mock_staff_b = User(
            id=staff_a.id,
            email="receptionist_b@clinicb.test",
            full_name="Staff Tenant B",
            role="receptionist",
            org_id=org_b.id,
            is_active=True,
        )

        app.dependency_overrides[get_current_tenant_org] = lambda: org_b.id
        app.dependency_overrides[get_current_user] = lambda: mock_staff_b

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp_phone = await client.get(f"/api/v1/patients/lookup?phone_number={patient_phone}")
            assert resp_phone.status_code == 404

            resp_id = await client.get(f"/api/v1/patients/{patient_a.id}")
            assert resp_id.status_code == 404

        app.dependency_overrides[get_current_tenant_org] = lambda: org_a.id
        app.dependency_overrides[get_current_user] = lambda: staff_a

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp_found = await client.get(f"/api/v1/patients/lookup?phone_number={patient_phone}")
            assert resp_found.status_code == 200
            assert resp_found.json()["id"] == str(patient_a.id)
            assert resp_found.json()["first_name"] == "Ravi"
    finally:
        app.dependency_overrides.pop(get_current_tenant_org, None)
        app.dependency_overrides.pop(get_current_user, None)
        async with session_maker() as cleanup_db:
            await cleanup_db.execute(text("DELETE FROM patients WHERE id = :id"), {"id": patient_a.id})
            await cleanup_db.execute(text("DELETE FROM organizations WHERE id = :id"), {"id": org_b.id})
            await cleanup_db.commit()


@pytest.mark.anyio
async def test_real_postgres_concurrent_advisory_lock_capacity_conflict(main_clinic_context, session_maker):
    import asyncio

    org = main_clinic_context["org"]
    doctor = main_clinic_context["doctor"]

    pat1_id = uuid4()
    pat2_id = uuid4()
    p1 = Patient(
        id=pat1_id,
        org_id=org.id,
        first_name="Contender1",
        last_name="A",
        phone_number=f"+9197{uuid4().int % 100000000:08d}",
    )
    p2 = Patient(
        id=pat2_id,
        org_id=org.id,
        first_name="Contender2",
        last_name="B",
        phone_number=f"+9197{uuid4().int % 100000000:08d}",
    )

    async with session_maker() as s:
        s.add_all([p1, p2])
        await s.commit()

    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    slot_time = datetime.now(tz) + timedelta(days=25, hours=10)
    slot_start = slot_time.replace(minute=0, second=0, microsecond=0)
    slot_end = slot_start + timedelta(minutes=30)

    created_appointment_ids = []

    async def _try_book(p_id, seq):
        async with session_maker() as s:
            try:
                res = await book_appointment_atomic(
                    db=s,
                    org_id=org.id,
                    patient_id=p_id,
                    doctor_id=doctor.id,
                    start_time=slot_start,
                    end_time=slot_end,
                    chief_complaint=f"Contender {seq}",
                    session_id=f"concurrent_test_seq_{seq}_{uuid4().hex[:4]}",
                )
                if res:
                    await s.commit()
                    created_appointment_ids.append(res.id)
                    return True
                return False
            except Exception:
                return False

    task1 = asyncio.create_task(_try_book(pat1_id, 1))
    task2 = asyncio.create_task(_try_book(pat2_id, 2))
    outcomes = await asyncio.gather(task1, task2)

    try:
        assert True in outcomes

        async with session_maker() as s:
            booked_appts = (
                (
                    await s.execute(
                        select(Appointment).where(
                            Appointment.org_id == org.id,
                            Appointment.doctor_id == doctor.id,
                            Appointment.start_time >= slot_start,
                            Appointment.start_time < slot_end,
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(booked_appts) <= 2
    finally:
        async with session_maker() as cleanup_db:
            for appt_id in created_appointment_ids:
                await cleanup_db.execute(text("DELETE FROM visit_events WHERE visit_id = :id"), {"id": appt_id})
                await cleanup_db.execute(text("DELETE FROM system_audit_logs WHERE target_id = :id"), {"id": appt_id})
                await cleanup_db.execute(text("DELETE FROM payments WHERE appointment_id = :id"), {"id": appt_id})
                await cleanup_db.execute(text("DELETE FROM appointments WHERE id = :id"), {"id": appt_id})
            await cleanup_db.execute(
                text("DELETE FROM patients WHERE id IN (:id1, :id2)"), {"id1": pat1_id, "id2": pat2_id}
            )
            await cleanup_db.commit()


@pytest.mark.anyio
async def test_real_postgres_walkin_to_completion_e2e(main_clinic_context, session_maker):
    org = main_clinic_context["org"]
    staff = main_clinic_context["staff"]

    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    today_local = datetime.now(tz).date()
    doctor = main_clinic_context["doctor"]

    pat_phone = f"+9199{uuid4().int % 100000000:08d}"
    app.dependency_overrides[get_current_tenant_org] = lambda: org.id
    app.dependency_overrides[get_current_user] = lambda: staff

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        walkin_payload = {
            "patient_name": "Kavya Patel",
            "patient_phone": pat_phone,
            "appointment_date": today_local.isoformat(),
            "chief_complaint": "Persistent headache",
            "fee": 500,
        }
        create_resp = await client.post("/api/v1/appointments/walkin", json=walkin_payload)
        assert create_resp.status_code == 201, create_resp.text
        data = create_resp.json()
        appt_id = UUID(data["id"])

        attending_doctor = User(
            id=doctor.id,
            email=doctor.email,
            full_name=doctor.full_name,
            role="doctor",
            org_id=org.id,
            is_active=True,
        )
        app.dependency_overrides[get_current_user] = lambda: attending_doctor

        call_resp = await client.post(f"/api/v1/appointments/{appt_id}/call")
        assert call_resp.status_code == 200
        assert call_resp.json()["queue_state"] == "called"

        start_resp = await client.post(f"/api/v1/appointments/{appt_id}/start-consultation")
        assert start_resp.status_code == 200
        assert start_resp.json()["status"] == "in_progress"

        comp_resp = await client.post(f"/api/v1/appointments/{appt_id}/complete")
        assert comp_resp.status_code == 200
        assert comp_resp.json()["status"] == "completed"

    app.dependency_overrides.pop(get_current_tenant_org, None)
    app.dependency_overrides.pop(get_current_user, None)

    try:
        async with session_maker() as db:
            saved_appt = await db.get(Appointment, appt_id)
            assert saved_appt is not None
            assert saved_appt.status == "completed"
            assert saved_appt.queue_state == "served"
            assert saved_appt.encounter_state == "completed"
            assert saved_appt.consultation_started_at is not None
            assert saved_appt.consultation_ended_at is not None
            assert saved_appt.actual_duration_seconds is not None
            assert saved_appt.actual_duration_seconds >= 0
    finally:
        async with session_maker() as cleanup_db:
            await cleanup_db.execute(text("DELETE FROM visit_events WHERE visit_id = :id"), {"id": appt_id})
            await cleanup_db.execute(text("DELETE FROM system_audit_logs WHERE target_id = :id"), {"id": appt_id})
            await cleanup_db.execute(text("DELETE FROM payments WHERE appointment_id = :id"), {"id": appt_id})
            await cleanup_db.execute(text("DELETE FROM appointments WHERE id = :id"), {"id": appt_id})
            await cleanup_db.execute(
                text("DELETE FROM patients WHERE phone_number = :phone AND org_id = :org_id"),
                {"phone": pat_phone, "org_id": org.id},
            )
            await cleanup_db.commit()


@pytest.mark.anyio
async def test_real_postgres_payment_persisted_and_read_back_via_receipt_and_revenue_endpoints(
    main_clinic_context, session_maker
):
    org = main_clinic_context["org"]
    staff = main_clinic_context["staff"]

    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    now_local = datetime.now(tz)
    patient_phone = f"+9198{uuid4().int % 100000000:08d}"
    patient = Patient(
        id=uuid4(),
        org_id=org.id,
        first_name="Ananya",
        last_name="Rao",
        phone_number=patient_phone,
    )
    appointment = Appointment(
        id=uuid4(),
        org_id=org.id,
        patient_id=patient.id,
        start_time=now_local,
        end_time=now_local + timedelta(minutes=15),
        source="walk_in",
        status="completed",
        queue_state="served",
        encounter_state="completed",
        fee=800,
        payment_status="pending",
    )
    async with session_maker() as db:
        db.add(patient)
        await db.flush()
        db.add(appointment)
        await db.commit()

    app.dependency_overrides[get_current_tenant_org] = lambda: org.id
    app.dependency_overrides[get_current_user] = lambda: staff

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payment_payload = {
                "payment_status": "paid",
                "payment_method": "UPI",
                "fee": 800.0,
                "amount_received": 800.0,
                "reference": "UPI-E2E-TEST-9921",
                "bill_items": [
                    {"name": "Consultation", "amount": 500.0, "category": "consultation"},
                    {"name": "CBC Blood Test", "amount": 300.0, "category": "diagnostic"},
                ],
            }
            collect_resp = await client.patch(
                f"/api/v1/clinic/{appointment.id}/collect-fee",
                json=payment_payload,
            )
            assert collect_resp.status_code == 200, collect_resp.text
            assert collect_resp.json()["payment_status"] == "paid"
            assert collect_resp.json()["amount_paid"] == 800.0

            receipts_resp = await client.get(f"/api/v1/clinic/{appointment.id}/payments")
            assert receipts_resp.status_code == 200
            receipts = receipts_resp.json()
            assert len(receipts) == 1
            assert receipts[0]["amount"] == 800.0
            assert receipts[0]["method"] == "UPI"
            assert receipts[0]["reference"] == "UPI-E2E-TEST-9921"
            assert receipts[0]["received_by_name"] == staff.full_name

            revenue_resp = await client.get("/api/v1/clinic/revenue?period=today")
            assert revenue_resp.status_code == 200
            rev_data = revenue_resp.json()
            assert rev_data["total_settled"] >= 800.0
            assert rev_data["upi_total"] >= 800.0
            matching_txns = [t for t in rev_data["transactions"] if t["id"] == str(appointment.id)]
            assert len(matching_txns) == 1
            assert matching_txns[0]["patient_name"] == "Ananya Rao"
            assert matching_txns[0]["fee_amount"] == 800
    finally:
        app.dependency_overrides.pop(get_current_tenant_org, None)
        app.dependency_overrides.pop(get_current_user, None)
        async with session_maker() as cleanup_db:
            await cleanup_db.execute(text("DELETE FROM visit_events WHERE visit_id = :id"), {"id": appointment.id})
            await cleanup_db.execute(
                text("DELETE FROM system_audit_logs WHERE target_id = :id"), {"id": appointment.id}
            )
            await cleanup_db.execute(text("DELETE FROM payments WHERE appointment_id = :id"), {"id": appointment.id})
            await cleanup_db.execute(text("DELETE FROM appointments WHERE id = :id"), {"id": appointment.id})
            await cleanup_db.execute(text("DELETE FROM patients WHERE id = :id"), {"id": patient.id})
            await cleanup_db.commit()
