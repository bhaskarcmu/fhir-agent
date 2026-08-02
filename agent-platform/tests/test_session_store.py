"""
Tests for agent_platform.session_store -- cross-session persistence (docs/
phase6/decisions.md H12). Self-skips when Postgres isn't reachable (see
conftest.py), same convention as provider-registry-service's DB-backed
tests -- run against the real thing, not a mock, or skipped.

Run (with a local Postgres reachable at TEST_DATABASE_URL):
  python3 -m pytest agent-platform/tests/test_session_store.py -v
"""

from __future__ import annotations

import pytest


def test_create_session_returns_a_new_empty_session(db_session_store):
    session_id = db_session_store.create_session()
    messages, token_count = db_session_store.load_session(session_id)
    assert messages == []
    assert token_count == 0


def test_save_and_reload_round_trips_plain_dict_messages(db_session_store):
    session_id = db_session_store.create_session()
    messages = [
        {"role": "user", "content": "check refill risk"},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "{}"}]},
    ]
    db_session_store.save_session(session_id, messages, token_count=1234)

    reloaded_messages, reloaded_token_count = db_session_store.load_session(session_id)
    assert reloaded_messages == messages
    assert reloaded_token_count == 1234


def test_save_and_reload_round_trips_anthropic_sdk_content_blocks(db_session_store):
    """
    The real hazard this module exists to handle: an assistant-turn message
    built from response.content holds Pydantic model instances
    (TextBlock/ToolUseBlock), not plain dicts -- these must serialize and
    come back as equivalent plain-dict JSON, not crash or silently drop data.
    """
    from anthropic.types import TextBlock, ToolUseBlock

    session_id = db_session_store.create_session()
    messages = [
        {"role": "user", "content": "check refill risk"},
        {
            "role": "assistant",
            "content": [
                TextBlock(type="text", text="Let me check.", citations=None),
                ToolUseBlock(type="tool_use", id="t1", name="get_patient_summary", input={"name": "X"}),
            ],
        },
    ]
    db_session_store.save_session(session_id, messages, token_count=500)

    reloaded_messages, _ = db_session_store.load_session(session_id)
    assert reloaded_messages[0] == {"role": "user", "content": "check refill risk"}
    assistant_content = reloaded_messages[1]["content"]
    assert assistant_content[0] == {"type": "text", "text": "Let me check.", "citations": None}
    assert assistant_content[1]["name"] == "get_patient_summary"
    assert assistant_content[1]["input"] == {"name": "X"}


def test_load_unknown_session_raises_key_error(db_session_store):
    with pytest.raises(KeyError):
        db_session_store.load_session("00000000-0000-0000-0000-000000000000")


def test_save_unknown_session_raises_key_error(db_session_store):
    with pytest.raises(KeyError):
        db_session_store.save_session("00000000-0000-0000-0000-000000000000", [], 0)


def test_sessions_are_independent(db_session_store):
    session_a = db_session_store.create_session()
    session_b = db_session_store.create_session()

    db_session_store.save_session(session_a, [{"role": "user", "content": "a"}], 10)
    db_session_store.save_session(session_b, [{"role": "user", "content": "b"}], 20)

    messages_a, tokens_a = db_session_store.load_session(session_a)
    messages_b, tokens_b = db_session_store.load_session(session_b)
    assert messages_a == [{"role": "user", "content": "a"}]
    assert messages_b == [{"role": "user", "content": "b"}]
    assert (tokens_a, tokens_b) == (10, 20)
