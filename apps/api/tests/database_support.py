"""Explicit database selection for tests that write persistent records."""

import os

from sqlalchemy.engine import make_url


def get_test_database_url() -> str:
    value = os.environ.get("TEST_DATABASE_URL", "")
    if not value:
        raise RuntimeError("TEST_DATABASE_URL must identify a disposable test database")
    parsed = make_url(value)
    if parsed.get_backend_name() != "postgresql" or "test" not in (parsed.database or "").lower():
        raise RuntimeError("TEST_DATABASE_URL must use PostgreSQL and a database name containing 'test'")
    return parsed.set(drivername="postgresql+asyncpg").render_as_string(hide_password=False)
