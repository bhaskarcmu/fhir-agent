"""
Database connection pool.

Environment variables:
  DATABASE_URL   Postgres connection string (required)
                 e.g. postgresql://provider_registry:provider_registry@postgres:5432/provider_registry
"""

from __future__ import annotations

import os

from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        database_url = os.environ.get("DATABASE_URL", "")
        if not database_url:
            raise RuntimeError(
                "DATABASE_URL is not set. "
                "Set it to a Postgres connection string, "
                "e.g. postgresql://provider_registry:provider_registry@localhost:5432/provider_registry"
            )
        _pool = ConnectionPool(database_url, open=True)
    return _pool


def reset_pool() -> None:
    """Close and clear the pool — used by tests to point at a different DATABASE_URL."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
