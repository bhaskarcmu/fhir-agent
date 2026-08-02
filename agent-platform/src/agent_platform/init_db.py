"""
Apply schema.sql -- run once before starting the app (Dockerfile CMD, or manually
for local dev). Same convention as provider-registry-service/src/provider_registry/init_db.py.

    python -m agent_platform.init_db
"""

from __future__ import annotations

from pathlib import Path

from .session_store import get_pool

SCHEMA_SQL_PATH = Path(__file__).resolve().parents[2] / "schema.sql"


def main() -> None:
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(SCHEMA_SQL_PATH.read_text())
        conn.commit()
    print(f"schema applied from {SCHEMA_SQL_PATH}")


if __name__ == "__main__":
    main()
