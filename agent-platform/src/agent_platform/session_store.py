"""
Postgres-backed cross-session persistence (docs/phase6/design.md Section
4.3, decisions.md H12). One of memory's three separate axes -- the other
two (per-conversation token budget, concurrent-session-count scaling) are
context_budget.py and Phase 6 M4 respectively, not this module.

Follows provider-registry-service's db.py connection-pool convention
exactly (same DATABASE_URL env var, same lazy global-pool pattern, same
reset_pool() test hook) for consistency with the one other Postgres-backed
service in this repo.

Messages are stored as JSON text, not native jsonb, deliberately: the
Anthropic SDK's assistant-turn content blocks (TextBlock, ToolUseBlock) are
Pydantic models, not plain dicts, so they need model_dump(mode="json")
before they're JSON-safe at all -- see serialize_messages(). Storing as
text with manual (de)serialization avoids needing a psycopg JSONB adapter
tuned to that conversion.
"""

from __future__ import annotations

import json
import os
import uuid

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
                "e.g. postgresql://agent_platform:agent_platform@localhost:5433/agent_platform"
            )
        _pool = ConnectionPool(database_url, open=True)
    return _pool


def reset_pool() -> None:
    """Close and clear the pool -- used by tests to point at a different DATABASE_URL."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def _to_jsonable(obj):
    """Recursively convert Anthropic SDK objects (Pydantic models) to plain JSON-safe values."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, list):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj


def serialize_messages(messages: list[dict]) -> str:
    """JSON-encode a messages list, converting any Anthropic SDK content blocks first."""
    return json.dumps(_to_jsonable(messages))


def deserialize_messages(raw: str) -> list[dict]:
    """
    The inverse of serialize_messages(). Returns plain dicts -- which the
    Anthropic API accepts directly as message content (this codebase's own
    tool_result blocks are already plain dicts, not SDK objects, so this is
    not a new shape as far as client.messages.create() is concerned).
    """
    return json.loads(raw)


def create_session() -> str:
    """Create a new, empty session. Returns the new session_id."""
    session_id = str(uuid.uuid4())
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO agent_sessions (session_id, messages, token_count) "
            "VALUES (%s, %s, %s)",
            (session_id, serialize_messages([]), 0),
        )
        conn.commit()
    return session_id


def load_session(session_id: str) -> tuple[list[dict], int]:
    """Returns (messages, token_count). Raises KeyError if session_id is unknown."""
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT messages, token_count FROM agent_sessions WHERE session_id = %s",
            (session_id,),
        ).fetchone()
    if row is None:
        raise KeyError(f"Unknown session_id: {session_id}")
    raw_messages, token_count = row
    return deserialize_messages(raw_messages), token_count


def save_session(session_id: str, messages: list[dict], token_count: int) -> None:
    """Overwrite a session's messages and token_count. Raises KeyError if session_id is unknown."""
    pool = get_pool()
    with pool.connection() as conn:
        cur = conn.execute(
            "UPDATE agent_sessions SET messages = %s, token_count = %s, updated_at = now() "
            "WHERE session_id = %s",
            (serialize_messages(messages), token_count, session_id),
        )
        if cur.rowcount == 0:
            raise KeyError(f"Unknown session_id: {session_id}")
        conn.commit()
