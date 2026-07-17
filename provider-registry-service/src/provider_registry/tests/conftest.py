"""
DB-backed tests self-skip when Postgres is unreachable — same pattern as the
project's e2e suite (not run against mocks; run against the real thing or skipped).

  TEST_DATABASE_URL   Postgres connection string for the test database
                       (default: postgresql://provider_registry:provider_registry@localhost:5432/provider_registry_test)
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

from provider_registry import db

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://provider_registry:provider_registry@localhost:5432/provider_registry_test",
)

_SCHEMA_SQL_PATH = Path(__file__).resolve().parents[3] / "schema.sql"
_FIXTURES_SQL_PATH = Path(__file__).resolve().parent / "fixtures.sql"

_TABLES_IN_FK_ORDER = (
    "anomaly_flags", "provider_taxonomies", "provider_addresses",
    "providers", "ingestion_runs", "taxonomy_reference", "zip_centroids",
)


def _db_available() -> bool:
    try:
        with psycopg.connect(TEST_DATABASE_URL, connect_timeout=2):
            return True
    except psycopg.OperationalError:
        return False


@pytest.fixture(scope="session")
def db_pool():
    if not _db_available():
        pytest.skip(f"Postgres not reachable at {TEST_DATABASE_URL} — skipping DB-backed tests")

    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    db.reset_pool()
    pool = db.get_pool()

    with pool.connection() as conn:
        conn.execute(_SCHEMA_SQL_PATH.read_text())
        conn.execute(f"TRUNCATE {', '.join(_TABLES_IN_FK_ORDER)} CASCADE")
        conn.execute(_FIXTURES_SQL_PATH.read_text())
        conn.commit()

    yield pool
    db.reset_pool()
