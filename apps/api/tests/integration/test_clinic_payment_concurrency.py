import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.appointment import Appointment
from app.models.payment_receipt import PaymentReceipt
from app.schemas.appointment import ClinicPaymentUpdate
from app.services.billing.payment_service import collect_appointment_fee

pytestmark = pytest.mark.live


def test_postgres_concurrent_collection_and_lost_response_retry():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires an isolated TEST_DATABASE_URL")
    parsed = make_url(url)
    if parsed.host not in {"localhost", "127.0.0.1"} or "test" not in (parsed.database or ""):
        pytest.fail("Use a local disposable test database")
    asyncio.run(exercise_transactions(url))


async def exercise_transactions(url):
    schema = "clinic_test_" + uuid4().hex
    admin = create_async_engine(url)
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        async with engine.begin() as conn:
            for statement in [
                "CREATE TYPE appointment_status AS ENUM ('scheduled','arrived','in_progress','completed','cancelled','no_show','skipped')",
                "CREATE TYPE appointment_source AS ENUM ('ai_voice','walk_in','manual')",
                "CREATE TYPE payment_status AS ENUM ('paid','pending','refunded')",
                "CREATE TABLE appointments (id uuid PRIMARY KEY, org_id uuid NOT NULL, patient_id uuid NOT NULL, doctor_id uuid, start_time timestamptz NOT NULL, end_time timestamptz NOT NULL, status appointment_status, queue_state varchar(20), encounter_state varchar(20), called_at timestamptz, call_count integer, chief_complaint varchar, doctor_notes varchar, source appointment_source, call_session_id uuid, cancellation_reason varchar, created_at timestamptz DEFAULT now(), token_number integer, display_token varchar(10), shift_type varchar(10), booking_metadata jsonb, checked_in_at timestamptz, checked_in_by uuid, consultation_started_at timestamptz, consultation_ended_at timestamptz, actual_duration_seconds integer)",
                "CREATE TABLE payments (id uuid PRIMARY KEY, org_id uuid NOT NULL, appointment_id uuid NOT NULL REFERENCES appointments(id), amount numeric(12,2) NOT NULL CHECK (amount > 0), status payment_status, method varchar(20), reference varchar(120), received_by uuid, received_at timestamptz DEFAULT now())",
            ]:
                await conn.execute(text(statement))
        org_id, visit_id = uuid4(), uuid4()
        now = datetime.now(timezone.utc)
        async with sessions() as db:
            db.add(
                Appointment(
                    id=visit_id,
                    org_id=org_id,
                    patient_id=uuid4(),
                    status="completed",
                    start_time=now,
                    end_time=now + timedelta(minutes=15),
                    fee=100,
                )
            )
            await db.commit()

        async def collect(key):
            async with sessions() as db:
                try:
                    return await collect_appointment_fee(
                        db,
                        visit_id,
                        ClinicPaymentUpdate(
                            idempotency_key=key, payment_status="paid", payment_method="Cash", amount_received=60
                        ),
                        org_id,
                    )
                except HTTPException as error:
                    await db.rollback()
                    return error.status_code

        same_key = "same-payment-" + uuid4().hex
        first, retry = await asyncio.gather(collect(same_key), collect(same_key))
        assert first == retry
        assert first["balance_due"] == 40
        assert await collect("different-payment-" + uuid4().hex) == 422
        async with sessions() as db:
            assert await db.scalar(select(func.count(PaymentReceipt.id))) == 1
            assert await db.scalar(select(func.sum(PaymentReceipt.amount))) == 60
        second_visit = uuid4()
        async with sessions() as db:
            db.add(
                Appointment(
                    id=second_visit,
                    org_id=org_id,
                    patient_id=uuid4(),
                    status="completed",
                    start_time=now,
                    end_time=now + timedelta(minutes=15),
                    fee=100,
                )
            )
            await db.commit()
        visit_id = second_visit
        results = await asyncio.gather(collect("cashier-one-" + uuid4().hex), collect("cashier-two-" + uuid4().hex))
        assert sum(isinstance(result, dict) for result in results) == 1
        assert 422 in results
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin.dispose()
