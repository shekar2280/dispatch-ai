"""Regression tests for operator tools."""

import sys
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from scripts import seed_clinic_demo
from tests.database_support import get_test_database_url


@pytest.mark.parametrize("value", ["", "postgresql://localhost/clinic", "sqlite:///clinic_test.db"])
def test_database_rejects_missing_or_unsafe_target(monkeypatch, value):
    monkeypatch.setenv("TEST_DATABASE_URL", value)
    with pytest.raises(RuntimeError):
        get_test_database_url()


def test_database_uses_explicit_test_target_and_preserves_credentials(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://production/clinic")
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://tester:p%40ss@localhost/clinic_test")
    assert get_test_database_url() == "postgresql+asyncpg://tester:p%40ss@localhost/clinic_test"


@pytest.mark.parametrize("environment", ["production", "prod", "unknown"])
def test_demo_seed_refuses_unapproved_environment(monkeypatch, environment):
    org_id = str(uuid4())
    seed = AsyncMock()
    monkeypatch.setattr(seed_clinic_demo, "run_seed", seed)
    monkeypatch.setattr(seed_clinic_demo.settings, "ENVIRONMENT", environment)
    monkeypatch.setattr(sys, "argv", ["seed_clinic_demo.py", "--org-id", org_id, "--confirm-org-id", org_id])
    with pytest.raises(SystemExit) as error:
        seed_clinic_demo.main()
    assert error.value.code == 2
    seed.assert_not_called()


@pytest.mark.asyncio
async def test_seed_requires_a_doctor_in_the_selected_clinic(monkeypatch):
    org_id = uuid4()
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(timezone="Europe/London")
    db.scalar.return_value = None
    sessions = MagicMock()
    sessions.return_value.__aenter__.return_value = db
    monkeypatch.setattr(seed_clinic_demo, "AsyncSessionLocal", sessions)
    with pytest.raises(RuntimeError, match="active doctor membership"):
        await seed_clinic_demo.run_seed(org_id, date(2026, 1, 1))
    query = db.scalar.call_args.args[0].compile()
    assert org_id in query.params.values()
    assert "users.role" in str(query)
    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_seed_does_not_commit_deletions_when_replacement_fails(monkeypatch):
    db = AsyncMock()
    db.add = MagicMock()
    db.get.return_value = SimpleNamespace(timezone="Europe/London")
    db.scalar.return_value = SimpleNamespace(id=uuid4())
    db.flush.side_effect = RuntimeError("Synthetic insertion failure")
    sessions = MagicMock()
    sessions.return_value.__aenter__.return_value = db
    monkeypatch.setattr(seed_clinic_demo, "AsyncSessionLocal", sessions)
    with pytest.raises(RuntimeError, match="insertion failure"):
        await seed_clinic_demo.run_seed(uuid4(), date(2026, 1, 1))
    assert db.execute.await_count > 0
    db.commit.assert_not_awaited()


def test_demo_seed_requires_matching_confirmation(monkeypatch):
    seed = AsyncMock()
    monkeypatch.setattr(seed_clinic_demo, "run_seed", seed)
    monkeypatch.setattr(seed_clinic_demo.settings, "ENVIRONMENT", "staging")
    monkeypatch.setattr(
        sys, "argv", ["seed_clinic_demo.py", "--org-id", str(uuid4()), "--confirm-org-id", str(uuid4())]
    )
    with pytest.raises(SystemExit) as error:
        seed_clinic_demo.main()
    assert error.value.code == 2
    seed.assert_not_called()
