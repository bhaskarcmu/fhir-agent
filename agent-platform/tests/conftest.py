"""
DB-backed tests self-skip when Postgres is unreachable -- same pattern as
provider-registry-service/src/provider_registry/tests/conftest.py.

  TEST_DATABASE_URL   Postgres connection string for the test database
                       (default: postgresql://agent_platform:agent_platform@localhost:5433/agent_platform_test)
"""

from __future__ import annotations

import os

import psycopg
import pytest

from agent_platform import session_store

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://agent_platform:agent_platform@localhost:5433/agent_platform_test",
)


def _db_available() -> bool:
    try:
        with psycopg.connect(TEST_DATABASE_URL, connect_timeout=2):
            return True
    except psycopg.OperationalError:
        return False


@pytest.fixture
def db_session_store():
    if not _db_available():
        pytest.skip(f"Postgres not reachable at {TEST_DATABASE_URL} -- skipping DB-backed tests")

    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    session_store.reset_pool()
    pool = session_store.get_pool()

    with pool.connection() as conn:
        conn.execute("DROP TABLE IF EXISTS agent_sessions")
        conn.commit()

    from pathlib import Path
    schema_path = Path(__file__).resolve().parents[1] / "schema.sql"
    with pool.connection() as conn:
        conn.execute(schema_path.read_text())
        conn.commit()

    yield session_store

    session_store.reset_pool()
