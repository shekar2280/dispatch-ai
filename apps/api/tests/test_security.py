"""Regression tests for security."""

import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from supabase import AuthApiError

from app.api.v1.patients import _visible_patient
from app.core import security
from app.models.call_session import CallLog, VoiceCallSession
from app.models.call_turn import CallTurn, VoiceCallTurn
from app.models.patient import Patient
from app.services.appointments.booking_service import _resolve_patient
from tests.database_support import get_test_database_url


def run(coroutine):
    if sys.platform != "win32":
        return asyncio.run(coroutine)
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    raise AssertionError("Unexpected asynchronous operation in isolated auth test")


def test_bearer_header_is_required():
    for authorization in (None, "", "Basic token", "Bearer "):
        with pytest.raises(HTTPException) as error:
            run(security.get_verified_auth_identity(authorization))
        assert error.value.status_code == 401


def test_expired_token_and_auth_outage_have_different_responses(monkeypatch):
    monkeypatch.setattr(
        security,
        "get_supabase_admin_client",
        lambda: SimpleNamespace(auth=SimpleNamespace(get_user=lambda _token: None)),
    )

    async def invalid_token(*_args):
        raise AuthApiError("expired", 401, None)

    monkeypatch.setattr(security, "run_in_threadpool", invalid_token)
    with pytest.raises(HTTPException) as error:
        run(security.get_verified_auth_identity("Bearer expired"))
    assert error.value.status_code == 401

    async def auth_outage(*_args):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr(security, "run_in_threadpool", auth_outage)
    with pytest.raises(HTTPException) as error:
        run(security.get_verified_auth_identity("Bearer valid"))
    assert error.value.status_code == 503


def test_verified_identity_requires_confirmed_email(monkeypatch):
    user_id = uuid4()
    monkeypatch.setattr(
        security,
        "get_supabase_admin_client",
        lambda: SimpleNamespace(auth=SimpleNamespace(get_user=lambda _token: None)),
    )

    async def get_user(*_args):
        return SimpleNamespace(
            user=SimpleNamespace(
                id=str(user_id),
                email=" Doctor@Example.com ",
                email_confirmed_at="2026-10-10T00:00:00Z",
                user_metadata={"full_name": "Doctor"},
            )
        )

    monkeypatch.setattr(security, "run_in_threadpool", get_user)
    identity = run(security.get_verified_auth_identity("bearer valid"))
    assert identity["id"] == user_id
    assert identity["email"] == "doctor@example.com"


def test_org_id_alone_does_not_restore_revoked_membership():
    org_id = uuid4()
    user = SimpleNamespace(id=uuid4(), org_id=org_id)

    class Database:
        async def scalar(self, _query):
            return None

    with pytest.raises(HTTPException) as error:
        run(
            security.get_current_tenant_org(
                x_org_id=str(org_id),
                tenant_org_query=None,
                current_user=user,
                db=Database(),
            )
        )
    assert error.value.status_code == 403


def _patient(first_name: str, last_name: str, org_id):
    return Patient(
        id=uuid4(),
        org_id=org_id,
        phone_number="+919876543210",
        first_name=first_name,
        last_name=last_name,
        medical_history={"notes": ["private diagnosis"]},
        created_at=datetime.now(timezone.utc),
    )


def test_operational_patient_response_hides_clinical_history():
    patient = _patient("Rohan", "Sharma", uuid4())
    assert _visible_patient(patient, SimpleNamespace(role="receptionist")).medical_history == {}
    assert _visible_patient(patient, SimpleNamespace(role="doctor")).medical_history == patient.medical_history


@pytest.mark.anyio
async def test_shared_phone_selects_patient_by_full_name():
    org_id = uuid4()
    mother = _patient("Sunita", "Sharma", org_id)
    son = _patient("Rohan", "Sharma", org_id)
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [mother, son]
    db.execute.return_value = result
    request = SimpleNamespace(patient_id=None, patient_name="Rohan Sharma", dob=None)

    resolved = await _resolve_patient(db, org_id, request, "+919876543210")
    assert resolved.id == son.id


def _get_test_session_maker():
    db_url = get_test_database_url()
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    test_engine = create_async_engine(
        db_url,
        poolclass=NullPool,
        connect_args={"statement_cache_size": 0},
    )
    maker = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return maker, test_engine


def test_call_log_model_schema_invariants():
    assert CallLog.__tablename__ == "call_logs"
    assert VoiceCallSession is CallLog
    assert CallLog.recording_status.default.arg == "disabled"

    columns = CallLog.__table__.columns
    assert "recording_status" in columns
    assert "recording_storage_path" in columns
    assert "full_transcript" in columns
    assert "total_turns" in columns
    assert "audio_recording_url" in columns


def test_call_turn_model_schema_invariants():
    assert VoiceCallTurn.__tablename__ == "voice_call_turns"
    assert CallTurn is VoiceCallTurn

    foreign_keys = list(VoiceCallTurn.__table__.foreign_keys)
    target_tables = [fk.column.table.name for fk in foreign_keys]
    assert "call_logs" in target_tables


@pytest.mark.live
def test_live_db_call_logs_crud_and_view_compatibility():
    async def _runner():
        test_call_id = uuid.uuid4()
        test_room = f"test_room_{uuid.uuid4().hex[:8]}"
        maker, test_engine = _get_test_session_maker()

        try:
            async with maker() as db:
                try:
                    await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=30.0)
                except Exception:
                    pytest.skip("PostgreSQL database is unavailable or timed out")

                result = await db.execute(text("SELECT id FROM organizations LIMIT 1"))
                row = result.fetchone()
                if not row:
                    pytest.skip("No organizations available in database for live integration test")
                org_id = row[0]

                new_call = CallLog(
                    id=test_call_id,
                    org_id=org_id,
                    room_name=test_room,
                    caller_phone="+1234567890",
                    caller_name="Live Test Caller",
                    session_type="browser_mic",
                    triage_status="completed",
                    call_outcome="information_provided",
                    recording_status="ready",
                    recording_storage_path="recordings/test/audio.mp4",
                    duration_seconds=45,
                    total_turns=1,
                    full_transcript="Caller: Hello. Assistant: Hi there.",
                    start_time=datetime.now(timezone.utc),
                    end_time=datetime.now(timezone.utc),
                )
                db.add(new_call)
                await db.commit()

                direct_query = await db.execute(
                    text("SELECT id, recording_status, recording_storage_path FROM call_logs WHERE id = :id"),
                    {"id": test_call_id},
                )
                direct_row = direct_query.fetchone()
                assert direct_row is not None
                assert direct_row[0] == test_call_id
                assert direct_row[1] == "ready"
                assert direct_row[2] == "recordings/test/audio.mp4"

                view_query = await db.execute(
                    text("SELECT id, recording_status, caller_name FROM voice_call_sessions WHERE id = :id"),
                    {"id": test_call_id},
                )
                view_row = view_query.fetchone()
                assert view_row is not None
                assert view_row[0] == test_call_id
                assert view_row[1] == "ready"
                assert view_row[2] == "Live Test Caller"

                turn_1 = VoiceCallTurn(
                    id=uuid.uuid4(),
                    session_id=test_call_id,
                    org_id=org_id,
                    turn_number=1,
                    user_transcript="Hello",
                    ai_response_text="Hi there.",
                )
                db.add(turn_1)
                await db.commit()

                turns_query = await db.execute(
                    text("SELECT COUNT(*) FROM voice_call_turns WHERE session_id = :id"),
                    {"id": test_call_id},
                )
                assert turns_query.scalar() == 1

                await db.execute(
                    text("DELETE FROM call_logs WHERE id = :id"),
                    {"id": test_call_id},
                )
                await db.commit()

                cascade_check = await db.execute(
                    text("SELECT COUNT(*) FROM voice_call_turns WHERE session_id = :id"),
                    {"id": test_call_id},
                )
                assert cascade_check.scalar() == 0
        finally:
            await test_engine.dispose()

    asyncio.run(_runner())


@pytest.mark.live
def test_live_db_check_constraints_enforcement():
    async def _runner():
        maker, test_engine = _get_test_session_maker()
        try:
            async with maker() as db:
                try:
                    await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=10.0)
                except Exception:
                    pytest.skip("PostgreSQL database is unavailable or timed out")

                result = await db.execute(text("SELECT id FROM organizations LIMIT 1"))
                row = result.fetchone()
                if not row:
                    pytest.skip("No organizations available in database for live integration test")
                org_id = row[0]

                with pytest.raises(IntegrityError):
                    await db.execute(
                        text("""
                            INSERT INTO call_logs (
                                id, org_id, caller_phone, room_name, recording_status
                            ) VALUES (
                                :id, :org_id, '+1234567890', :room_name, 'unsupported_status'
                            )
                        """),
                        {
                            "id": uuid.uuid4(),
                            "org_id": org_id,
                            "room_name": f"test_invalid_{uuid.uuid4().hex[:8]}",
                        },
                    )
                    await db.commit()
                await db.rollback()

                with pytest.raises(IntegrityError):
                    await db.execute(
                        text("""
                            INSERT INTO call_logs (
                                id, org_id, caller_phone, room_name, duration_seconds
                            ) VALUES (
                                :id, :org_id, '+1234567890', :room_name, -10
                            )
                        """),
                        {
                            "id": uuid.uuid4(),
                            "org_id": org_id,
                            "room_name": f"test_neg_dur_{uuid.uuid4().hex[:8]}",
                        },
                    )
                    await db.commit()
                await db.rollback()
        finally:
            await test_engine.dispose()

    asyncio.run(_runner())


@pytest.mark.live
def test_live_db_compatibility_view_security_invoker_active():
    async def _runner():
        maker, test_engine = _get_test_session_maker()
        try:
            async with maker() as db:
                try:
                    await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=10.0)
                except Exception:
                    pytest.skip("PostgreSQL database is unavailable or timed out")

                res = await db.execute(text("SELECT reloptions FROM pg_class WHERE relname = 'voice_call_sessions'"))
                options = res.scalar()
                assert options is not None
                assert "security_invoker=true" in options
        finally:
            await test_engine.dispose()

    asyncio.run(_runner())


@pytest.mark.live
def test_live_db_cross_tenant_isolation_invariants():
    async def _runner():
        maker, test_engine = _get_test_session_maker()
        try:
            async with maker() as db:
                try:
                    await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=10.0)
                except Exception:
                    pytest.skip("PostgreSQL database is unavailable or timed out")

                user_res = await db.execute(text("SELECT id, org_id FROM public.users WHERE is_active = true LIMIT 1"))
                user_row = user_res.fetchone()
                if not user_row:
                    pytest.skip("No users available to test RLS impersonation")

                user_a_id = user_row[0]
                org_a_id = user_row[1]
                created_temp_org = True

                org_b_id = uuid.uuid4()
                await db.execute(
                    text("""
                        INSERT INTO organizations (
                            id, name, slug, timezone, country, country_code, currency_code, currency_symbol
                        ) VALUES (
                            :id, 'Temp Org B', :slug, 'Asia/Kolkata', 'India', '+91', 'INR', 'Rs.'
                        )
                    """),
                    {"id": org_b_id, "slug": f"temp-org-b-{org_b_id.hex[:6]}"},
                )
                await db.commit()

                call_a_id = uuid.uuid4()
                call_b_id = uuid.uuid4()

                room_a = f"test_org_a_{uuid.uuid4().hex[:8]}"
                room_b = f"test_org_b_{uuid.uuid4().hex[:8]}"

                call_a = CallLog(
                    id=call_a_id,
                    org_id=org_a_id,
                    room_name=room_a,
                    caller_phone="+1111111111",
                    caller_name="Org A Patient",
                )
                call_b = CallLog(
                    id=call_b_id,
                    org_id=org_b_id,
                    room_name=room_b,
                    caller_phone="+2222222222",
                    caller_name="Org B Patient",
                )
                db.add_all([call_a, call_b])
                await db.commit()

                has_auth_role_res = await db.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'authenticated'"))
                if has_auth_role_res.scalar() is not None:
                    claims = json.dumps({"sub": str(user_a_id), "role": "authenticated"})
                    await db.execute(text("SET LOCAL ROLE authenticated"))
                    await db.execute(
                        text("SELECT set_config('request.jwt.claims', :claims, true)"),
                        {"claims": claims},
                    )

                    query_a_direct = await db.execute(text("SELECT id FROM call_logs"))
                    found_a_ids = [r[0] for r in query_a_direct.fetchall()]
                    assert call_a_id in found_a_ids
                    assert call_b_id not in found_a_ids

                    await db.execute(text("RESET ROLE"))

                await db.execute(
                    text("DELETE FROM call_logs WHERE id IN (:id_a, :id_b)"),
                    {"id_a": call_a_id, "id_b": call_b_id},
                )
                if created_temp_org:
                    await db.execute(text("DELETE FROM organizations WHERE id = :id"), {"id": org_b_id})
                await db.commit()
        finally:
            await test_engine.dispose()

    asyncio.run(_runner())


def test_token_identity_caching(monkeypatch):
    user_id = uuid4()
    call_count = 0

    monkeypatch.setattr(
        security,
        "get_supabase_admin_client",
        lambda: SimpleNamespace(auth=SimpleNamespace(get_user=lambda _token: None)),
    )

    async def get_user(*_args):
        nonlocal call_count
        call_count += 1
        return SimpleNamespace(
            user=SimpleNamespace(
                id=str(user_id),
                email="cached@example.com",
                email_confirmed_at="2026-10-10T00:00:00Z",
                user_metadata={"full_name": "Cached Doctor"},
            )
        )

    monkeypatch.setattr(security, "run_in_threadpool", get_user)

    token_str = f"test-cache-token-{uuid4().hex}"
    identity1 = run(security.get_verified_auth_identity(f"Bearer {token_str}"))
    identity2 = run(security.get_verified_auth_identity(f"Bearer {token_str}"))

    assert identity1["id"] == user_id
    assert identity2["id"] == user_id
    assert call_count == 1

