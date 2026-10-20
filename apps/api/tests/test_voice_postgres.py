"""Regression tests for voice postgres."""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.call_session import CallLog
from app.models.call_turn import VoiceCallTurn
from app.models.organization import Organization
from app.services.billing.voice_quota import allowance_snapshot, enforce_voice_demo_allowance
from app.services.voice.provider_budget import reserve_budget

pytestmark = pytest.mark.voice_db


DB_URL = os.getenv("VOICE_TEST_DATABASE_URL", "")


@pytest.fixture(scope="module", autouse=True)
def schema():
    if not DB_URL:
        pytest.skip("VOICE_TEST_DATABASE_URL is required")
    target = make_url(DB_URL)
    if (
        target.host not in {"127.0.0.1", "localhost", "dispatch-voice-tests-postgres"}
        or target.database != "dispatch_voice_tests"
    ):
        raise RuntimeError("Only the local disposable dispatch_voice_tests database is permitted")

    async def setup():
        conn = await asyncpg.connect(DB_URL)
        try:
            await conn.execute("""
                create schema if not exists auth;
                create schema if not exists private;
                create table if not exists auth.users(id uuid primary key, email text,
                  raw_user_meta_data jsonb default '{}'::jsonb);
                create or replace function auth.uid() returns uuid language sql as 'select null::uuid';
                create or replace function private.current_org_id() returns uuid language sql as 'select null::uuid';
                do $$ begin
                  if not exists (select from pg_roles where rolname='anon') then create role anon; end if;
                  if not exists (select from pg_roles where rolname='authenticated') then create role authenticated; end if;
                  if not exists (select from pg_roles where rolname='service_role') then create role service_role bypassrls; end if;
                end $$;
            """)
            await conn.execute(Path("database/schemas/schema.sql").read_text(encoding="utf-8-sig"))
        finally:
            await conn.close()

    asyncio.run(setup())


def maker():
    engine = create_async_engine(
        DB_URL.replace("postgresql://", "postgresql+asyncpg://"),
        poolclass=NullPool,
        connect_args={"statement_cache_size": 0},
    )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def organization(sessions, consumed=0):
    org_id = uuid4()
    async with sessions() as db:
        db.add(
            Organization(
                id=org_id,
                slug=str(org_id),
                name="Synthetic test clinic",
                timezone="Asia/Kolkata",
                country="India",
                country_code="IN",
                currency_code="INR",
                currency_symbol="₹",
                voice_seconds_used=consumed,
            )
        )
        await db.commit()
    return org_id


def test_parallel_admission_only_reserves_the_last_second(monkeypatch):
    monkeypatch.setattr(settings, "VOICE_GLOBAL_CONCURRENCY", 100)

    async def run():
        engine, sessions = maker()
        org_id = await organization(sessions, consumed=1799)

        async def admit():
            async with sessions() as db:
                try:
                    budget = await enforce_voice_demo_allowance(db, org_id)
                    db.add(
                        CallLog(
                            org_id=org_id,
                            caller_phone="Synthetic",
                            call_budget_seconds=budget,
                            admission_expires_at=datetime.now(timezone.utc) + timedelta(seconds=45),
                        )
                    )
                    await db.commit()
                    return budget
                except HTTPException as exc:
                    assert exc.status_code in {402, 409}
                    return 0

        try:
            assert sum(await asyncio.gather(*(admit() for _ in range(20)))) == 1
            async with sessions() as db:
                state = await allowance_snapshot(db, org_id)
                assert state["remaining_seconds"] == 0 and state["reserved_seconds"] == 1
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_settlement_is_idempotent_and_history_deletion_preserves_usage():
    async def run():
        engine, sessions = maker()
        org_id = await organization(sessions)
        now = datetime.now(timezone.utc)
        async with sessions() as db:
            call = CallLog(
                org_id=org_id,
                caller_phone="Synthetic",
                provider_started_at=now - timedelta(seconds=1.2),
                call_budget_seconds=120,
            )
            db.add(call)
            await db.commit()
            call_id = call.id
        async with sessions() as db:
            call = await db.get(CallLog, call_id)
            call.end_time = now
            call.media_terminated_at = now
            await db.commit()
        async with sessions() as db:
            call = await db.get(CallLog, call_id)
            assert call.charged_seconds == 2
            call.end_time = now + timedelta(seconds=100)
            await db.commit()
        async with sessions() as db:
            assert (await db.get(Organization, org_id)).voice_seconds_used == 2
            await db.delete(await db.get(CallLog, call_id))
            await db.commit()
        async with sessions() as db:
            assert (await db.get(Organization, org_id)).voice_seconds_used == 2
        await engine.dispose()

    asyncio.run(run())


def test_unactivated_failures_cost_zero_and_active_rows_cannot_be_deleted():
    async def run():
        conn = await asyncpg.connect(DB_URL)
        try:
            org_id = uuid4()
            await conn.execute(
                """insert into organizations(id,slug,name,timezone,country,country_code,currency_code,currency_symbol)
                values ($1,$2,'Synthetic','Asia/Kolkata','India','IN','INR','INR')""",
                org_id,
                str(org_id),
            )
            call_id = await conn.fetchval(
                "insert into call_logs(org_id,caller_phone) values ($1,'Synthetic') returning id", org_id
            )
            with pytest.raises(asyncpg.RaiseError):
                await conn.execute("delete from call_logs where id=$1", call_id)
            await conn.execute("update call_logs set end_time=now() where id=$1", call_id)
            assert await conn.fetchval("select voice_seconds_used from organizations where id=$1", org_id) == 0
        finally:
            await conn.close()

    asyncio.run(run())


def test_shared_provider_reservations_enforce_rpm_across_parallel_sessions():
    async def run():
        engine, sessions = maker()
        scope = "test:" + str(uuid4())

        async def request():
            async with sessions() as db:
                try:
                    await reserve_budget(scope, 100, rpm=12, tpm=200000, rpd=400, db=db)
                    await db.commit()
                    return 1
                except HTTPException as exc:
                    assert exc.status_code == 429
                    return 0

        assert sum(await asyncio.gather(*(request() for _ in range(20)))) == 12
        await engine.dispose()

    asyncio.run(run())


def test_migration_rerun_does_not_double_charge_and_permissions_protect_counters():
    async def run():
        conn = await asyncpg.connect(DB_URL)
        try:
            before = await conn.fetchval("select sum(voice_seconds_used) from organizations")
            await conn.execute(Path("database/migrations/20261012_voice_hardening.sql").read_text(encoding="utf-8-sig"))
            assert await conn.fetchval("select sum(voice_seconds_used) from organizations") == before
            assert not await conn.fetchval(
                "select has_column_privilege('authenticated','public.organizations','voice_seconds_used','UPDATE')"
            )
            assert not await conn.fetchval(
                "select has_column_privilege('authenticated','public.organizations','inbound_voice_number','UPDATE')"
            )
        finally:
            await conn.close()

    asyncio.run(run())


def test_parallel_confirmations_create_one_appointment_and_one_replay_result():
    async def run():
        from unittest.mock import AsyncMock, patch

        from sqlalchemy import func, select

        from app.models.appointment import Appointment
        from app.models.user import User
        from app.services.voice.handlers.clinic_tool_handler import _confirm_booking

        engine, sessions = maker()
        org_id = await organization(sessions)
        doctor_id, call_id = uuid4(), uuid4()
        now = datetime.now(timezone.utc)
        details = dict(
            first_name="Synthetic",
            last_name="Booking",
            slot_date=(now + timedelta(days=1)).date().isoformat(),
            slot_time="10:00 AM",
            doctor_name="Test Doctor",
            chief_complaint="",
            booking_mode="appointment",
        )
        async with sessions() as db:
            from sqlalchemy import text

            await db.execute(
                text("insert into auth.users(id,email) values (:id,'synthetic@example.invalid')"), {"id": doctor_id}
            )
            org = await db.get(Organization, org_id)
            org.booking_settings = {
                "default_slot_duration_minutes": 15,
                "slot_buffer_minutes": 0,
                "booking_quota_per_window": 2,
                "window_duration_minutes": 30,
                "max_daily_patients": 100,
                "consultation_fee": 500,
                "weekly_schedule": {
                    day: {"isOpen": True, "windows": [{"start": "08:00", "end": "18:00"}]}
                    for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
                },
            }
            db.add(
                User(
                    id=doctor_id,
                    org_id=org_id,
                    email="synthetic@example.invalid",
                    full_name="Test Doctor",
                    role="doctor",
                    is_active=True,
                )
            )
            db.add(
                CallLog(
                    id=call_id,
                    org_id=org_id,
                    caller_phone="+919876543210",
                    provider_started_at=now,
                    deadline_at=now + timedelta(seconds=120),
                    booking_proposal={"details": details, "caller_event_id": "u1", "readback_event_id": "a1"},
                )
            )
            await db.flush()
            db.add_all(
                [
                    VoiceCallTurn(
                        session_id=call_id, org_id=org_id, event_id="u1", turn_number=1, user_transcript="Book tomorrow"
                    ),
                    VoiceCallTurn(
                        session_id=call_id,
                        org_id=org_id,
                        event_id="a1",
                        turn_number=2,
                        ai_response_text="Synthetic Booking tomorrow at 10 AM?",
                    ),
                    VoiceCallTurn(
                        session_id=call_id, org_id=org_id, event_id="u2", turn_number=3, user_transcript="Yes please"
                    ),
                ]
            )
            await db.commit()
        barrier = asyncio.Barrier(2)

        async def confirm():
            async with sessions() as db:
                # Deliberately pre-load stale state like the tool dispatcher does.
                await db.get(CallLog, call_id)
                await barrier.wait()
                org = await db.get(Organization, org_id)
                return await _confirm_booking(details, db, org_id, org, "+919876543210", call_id)

        with patch("app.services.infra.websocket_manager.ws_manager.broadcast_to_org", new_callable=AsyncMock):
            results = await asyncio.gather(confirm(), confirm())
        assert all(result["status"] == "confirmed" for result in results), results
        assert results[0]["appointment_id"] == results[1]["appointment_id"]
        async with sessions() as db:
            assert (
                await db.scalar(select(func.count(Appointment.id)).where(Appointment.call_session_id == call_id)) == 1
            )
        await engine.dispose()

    asyncio.run(run())


async def recipient(sessions):
    org_id = await organization(sessions, consumed=1800)
    user_id = uuid4()
    email = f"credit-{user_id}@example.test"
    async with sessions() as db:
        await db.execute(text("insert into auth.users(id,email) values (:id,:email)"), {"id": user_id, "email": email})
        await db.execute(
            text("insert into public.users(id,org_id,email,full_name) values (:id,:org,:email,'Credit test')"),
            {"id": user_id, "org": org_id, "email": email},
        )
        await db.commit()
    return org_id, email


def test_grants_are_additive_tenant_scoped_and_retry_safe():
    async def run():
        engine, sessions = maker()
        try:
            org_id, email = await recipient(sessions)
            other = await organization(sessions)
            request_id = uuid4()

            async def grant():
                async with sessions() as db:
                    await db.execute(
                        text("select public.grant_voice_minutes(:email,60,'Testing',:id)"),
                        {"email": f" {email.upper()} ", "id": request_id},
                    )
                    await db.commit()

            await asyncio.gather(*(grant() for _ in range(5)))
            async with sessions() as db:
                state = await allowance_snapshot(db, org_id)
                assert state["limit_seconds"] == 5400
                assert state["bonus_seconds"] == 3600
                assert state["used_seconds"] == 1800
                assert state["remaining_seconds"] == 3600
                assert (await allowance_snapshot(db, other))["limit_seconds"] == 1800
                await db.execute(
                    text("select public.grant_voice_minutes(:email,15,'More testing',:id)"),
                    {"email": email, "id": uuid4()},
                )
                await db.commit()
                assert (await allowance_snapshot(db, org_id))["remaining_seconds"] == 4500
            async with sessions() as db:
                with pytest.raises(Exception, match="different grant"):
                    await db.execute(
                        text("select public.grant_voice_minutes(:email,61,'Testing',:id)"),
                        {"email": email, "id": request_id},
                    )
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_credit_permissions_validation_and_migration_rerun():
    async def run():
        conn = await asyncpg.connect(DB_URL)
        try:
            await conn.execute(Path("database/migrations/20261016_consolidate_voice_credits.sql").read_text())
            for role in ("anon", "authenticated"):
                assert not await conn.fetchval(
                    "select has_function_privilege($1, 'public.grant_voice_minutes(text,integer,text,uuid)', 'execute')",
                    role,
                )
                assert not await conn.fetchval(
                    "select has_table_privilege($1,'public.system_audit_logs','insert')", role
                )
            assert await conn.fetchval("select to_regclass('public.voice_credit_grants')") is None
            assert await conn.fetchval("select to_regclass('public.voice_call_sessions')") is None
            assert await conn.fetchval(
                "select has_function_privilege('service_role','public.grant_voice_minutes(text,integer,text,uuid)','execute')"
            )
            with pytest.raises(asyncpg.RaiseError, match="No active clinic account"):
                await conn.execute("select public.grant_voice_minutes('missing@example.test',60,'Test',$1)", uuid4())
            for minutes in (0, -1, 100001):
                with pytest.raises(asyncpg.RaiseError, match="Provide"):
                    await conn.execute(
                        "select public.grant_voice_minutes('missing@example.test',$1,'Test',$2)", minutes, uuid4()
                    )
        finally:
            await conn.close()

    asyncio.run(run())


def test_cleanup_preserves_legacy_grants_and_retry_identity():
    async def run():
        engine, sessions = maker()
        org_id, email = await recipient(sessions)
        conn = await asyncpg.connect(DB_URL)
        grant_id = uuid4()
        try:
            await conn.execute("""
                create table public.voice_credit_grants (
                  id uuid primary key, org_id uuid not null, recipient_email text not null,
                  seconds bigint not null, reason text not null, granted_by text not null,
                  created_at timestamptz not null default now());
                create view public.voice_call_sessions as select * from public.call_logs;
            """)
            await conn.execute(
                "insert into voice_credit_grants(id,org_id,recipient_email,seconds,reason,granted_by) values($1,$2,$3,3600,'Original grant','operator')",
                grant_id,
                org_id,
                email,
            )
            created = await conn.fetchval("select created_at from voice_credit_grants where id=$1", grant_id)
            migration = Path("database/migrations/20261016_consolidate_voice_credits.sql").read_text()
            await conn.execute(migration)
            await conn.execute(migration)
            row = await conn.fetchrow("select * from system_audit_logs where id=$1", grant_id)
            assert row["created_at"] == created and row["actor_email"] == "operator"
            assert await conn.fetchval("select to_regclass('public.voice_credit_grants')") is None
            assert await conn.fetchval("select to_regclass('public.voice_call_sessions')") is None
            await conn.execute("select public.grant_voice_minutes($1,60,'Original grant',$2)", email, grant_id)
            async with sessions() as db:
                assert (await allowance_snapshot(db, org_id))["bonus_seconds"] == 3600
        finally:
            await conn.close()
            await engine.dispose()

    asyncio.run(run())


def test_cleanup_rolls_back_if_existing_audit_id_conflicts():
    async def run():
        engine, sessions = maker()
        org_id, email = await recipient(sessions)
        conn = await asyncpg.connect(DB_URL)
        grant_id = uuid4()
        try:
            await conn.execute("""create table public.voice_credit_grants (
                id uuid primary key, org_id uuid, recipient_email text, seconds bigint,
                reason text, granted_by text, created_at timestamptz default now())""")
            await conn.execute(
                "insert into voice_credit_grants values($1,$2,$3,60,'Test','operator',now())", grant_id, org_id, email
            )
            await conn.execute(
                "insert into system_audit_logs(id,org_id,actor_email,action_type) values($1,$2,'operator','OTHER_EVENT')",
                grant_id,
                org_id,
            )
            with pytest.raises(asyncpg.RaiseError, match="verification failed"):
                await conn.execute(Path("database/migrations/20261016_consolidate_voice_credits.sql").read_text())
            await conn.execute("ROLLBACK")
            assert await conn.fetchval("select count(*) from voice_credit_grants where id=$1", grant_id) == 1
        finally:
            await conn.execute("drop table if exists public.voice_credit_grants")
            await conn.close()
            await engine.dispose()

    asyncio.run(run())
