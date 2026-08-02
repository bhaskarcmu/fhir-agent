"""
Tests for session persistence wiring in non_interactive_mode and
interactive_mode (docs/phase6/decisions.md H12, H14) -- resume, create,
and the graceful in-memory fallback when the session store is unavailable
(mirroring claims-agent's own no-API-key deterministic fallback).

Run:
  python3 -m pytest mcp-agent/tests/test_session_persistence.py -v
"""

from __future__ import annotations

from unittest.mock import patch

from agent.agent import interactive_mode, non_interactive_mode


class _FakeClient:
    """non_interactive_mode/interactive_mode never touch client.messages
    directly -- run_query is patched out in every test here, so this only
    needs to exist as a distinguishable object, not behave like anthropic.Anthropic."""


def test_non_interactive_mode_without_session_id_is_stateless_as_before():
    with patch("agent.agent.run_query", return_value=("AGENT DECISION\n\nDISPENSE", [])) as mock_rq, \
         patch("agent.agent.load_session") as mock_load, \
         patch("agent.agent.save_session") as mock_save:
        exit_code = non_interactive_mode(_FakeClient(), "check refill risk")

    assert exit_code == 0
    mock_load.assert_not_called()
    mock_save.assert_not_called()
    mock_rq.assert_called_once()


def test_non_interactive_mode_with_session_id_resumes_and_persists():
    prior_messages = [{"role": "user", "content": "earlier question"}]
    with patch("agent.agent.load_session", return_value=(prior_messages, 500)) as mock_load, \
         patch(
             "agent.agent.run_query",
             return_value=("AGENT DECISION\n\nDISPENSE", prior_messages + [{"role": "user", "content": "new"}]),
         ) as mock_rq, \
         patch("agent.agent.save_session") as mock_save:
        exit_code = non_interactive_mode(_FakeClient(), "check refill risk", session_id="abc-123")

    assert exit_code == 0
    mock_load.assert_called_once_with("abc-123")
    # run_query is called with the resumed history, not an empty list.
    assert mock_rq.call_args.args[2] == prior_messages
    mock_save.assert_called_once()
    assert mock_save.call_args.args[0] == "abc-123"


def test_non_interactive_mode_with_unknown_session_id_fails_closed_not_silently():
    with patch("agent.agent.load_session", side_effect=KeyError("nope")), \
         patch("agent.agent.run_query") as mock_rq:
        exit_code = non_interactive_mode(_FakeClient(), "check refill risk", session_id="ghost")

    assert exit_code == 1
    mock_rq.assert_not_called()  # never runs a query against a session that doesn't exist


def test_interactive_mode_creates_a_new_session_when_database_url_is_set(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/for-this-test")
    inputs = iter(["quit"])

    with patch("builtins.input", side_effect=lambda _: next(inputs)), \
         patch("agent.agent.create_session", return_value="new-session-id") as mock_create:
        interactive_mode(_FakeClient())

    mock_create.assert_called_once()


def test_interactive_mode_falls_back_to_in_memory_when_the_store_is_unavailable(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    inputs = iter(["quit"])

    with patch("builtins.input", side_effect=lambda _: next(inputs)), \
         patch("agent.agent.create_session") as mock_create:
        interactive_mode(_FakeClient())

    # No DATABASE_URL -- create_session() is never even attempted, matching
    # claims-agent's own graceful-degrade-don't-crash precedent.
    mock_create.assert_not_called()
    assert "Goodbye" in capsys.readouterr().out


def test_interactive_mode_resumes_a_given_session_id(monkeypatch):
    prior_messages = [{"role": "user", "content": "earlier question"}]
    inputs = iter(["quit"])

    with patch("builtins.input", side_effect=lambda _: next(inputs)), \
         patch("agent.agent.load_session", return_value=(prior_messages, 500)) as mock_load:
        interactive_mode(_FakeClient(), session_id="resume-me")

    mock_load.assert_called_once_with("resume-me")
