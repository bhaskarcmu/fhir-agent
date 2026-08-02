"""
Tests for session persistence wiring in non_interactive_mode and
interactive_mode (docs/phase6/decisions.md H12, H14, H49) -- resume,
create, the graceful in-memory fallback when the session store is
unavailable (mirroring claims-agent's own no-API-key deterministic
fallback), and M5's per-session provider/model pinning.

Run:
  python3 -m pytest mcp-agent/tests/test_session_persistence.py -v
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from agent.agent import interactive_mode, non_interactive_mode
from agent_platform import ResolvedProvider


class _FakeClient:
    """non_interactive_mode/interactive_mode never touch client.messages
    directly -- run_query is patched out in every test here, so this only
    needs to exist as a distinguishable object, not behave like anthropic.Anthropic."""


def _resolved(*, is_default: bool = True) -> ResolvedProvider:
    return ResolvedProvider(_FakeClient(), "llama3.2:1b", "ollama", is_default=is_default)


def _loaded_session(messages, token_count, provider="anthropic", model="claude-sonnet-4-5"):
    """Stands in for agent_platform.session_store.LoadedSession."""
    return SimpleNamespace(messages=messages, token_count=token_count, provider=provider, model=model)


def test_non_interactive_mode_without_session_id_is_stateless_as_before():
    with patch("agent.agent.run_query", return_value=("AGENT DECISION\n\nDISPENSE", [])) as mock_rq, \
         patch("agent.agent.load_session") as mock_load, \
         patch("agent.agent.save_session") as mock_save:
        exit_code = non_interactive_mode(_resolved(), "check refill risk")

    assert exit_code == 0
    mock_load.assert_not_called()
    mock_save.assert_not_called()
    mock_rq.assert_called_once()


def test_non_interactive_mode_with_session_id_resumes_and_persists():
    prior_messages = [{"role": "user", "content": "earlier question"}]
    with patch("agent.agent.load_session", return_value=_loaded_session(prior_messages, 500)) as mock_load, \
         patch("agent.agent.build_client_for", return_value=_FakeClient()) as mock_build, \
         patch(
             "agent.agent.run_query",
             return_value=("AGENT DECISION\n\nDISPENSE", prior_messages + [{"role": "user", "content": "new"}]),
         ) as mock_rq, \
         patch("agent.agent.save_session") as mock_save:
        exit_code = non_interactive_mode(_resolved(), "check refill risk", session_id="abc-123")

    assert exit_code == 0
    mock_load.assert_called_once_with("abc-123")
    # The session's own pinned provider/model rebuild the client (H49) --
    # not whatever `resolved` (today's default) would otherwise use.
    mock_build.assert_called_once_with("anthropic", "claude-sonnet-4-5")
    # run_query is called with the resumed history, not an empty list.
    assert mock_rq.call_args.args[2] == prior_messages
    assert mock_rq.call_args.kwargs["model"] == "claude-sonnet-4-5"
    assert mock_rq.call_args.kwargs["gen_ai_system"] == "anthropic"
    mock_save.assert_called_once()
    assert mock_save.call_args.args[0] == "abc-123"


def test_non_interactive_mode_with_unknown_session_id_fails_closed_not_silently():
    with patch("agent.agent.load_session", side_effect=KeyError("nope")), \
         patch("agent.agent.run_query") as mock_rq:
        exit_code = non_interactive_mode(_resolved(), "check refill risk", session_id="ghost")

    assert exit_code == 1
    mock_rq.assert_not_called()  # never runs a query against a session that doesn't exist


def test_interactive_mode_creates_a_new_session_with_the_resolved_provider_and_model(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/for-this-test")
    inputs = iter(["quit"])

    with patch("builtins.input", side_effect=lambda _: next(inputs)), \
         patch("agent.agent.create_session", return_value="new-session-id") as mock_create:
        interactive_mode(_resolved())

    mock_create.assert_called_once_with("ollama", "llama3.2:1b")


def test_interactive_mode_falls_back_to_in_memory_when_the_store_is_unavailable(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    inputs = iter(["quit"])

    with patch("builtins.input", side_effect=lambda _: next(inputs)), \
         patch("agent.agent.create_session") as mock_create:
        interactive_mode(_resolved())

    # No DATABASE_URL -- create_session() is never even attempted, matching
    # claims-agent's own graceful-degrade-don't-crash precedent.
    mock_create.assert_not_called()
    assert "Goodbye" in capsys.readouterr().out


def test_interactive_mode_resumes_a_given_session_id_and_rebuilds_its_own_client(monkeypatch):
    prior_messages = [{"role": "user", "content": "earlier question"}]
    inputs = iter(["quit"])

    with patch("builtins.input", side_effect=lambda _: next(inputs)), \
         patch("agent.agent.load_session", return_value=_loaded_session(prior_messages, 500, "openai_compatible", "deepseek-chat")) as mock_load, \
         patch("agent.agent.build_client_for", return_value=_FakeClient()) as mock_build:
        interactive_mode(_resolved(), session_id="resume-me")

    mock_load.assert_called_once_with("resume-me")
    mock_build.assert_called_once_with("openai_compatible", "deepseek-chat")


# ── Disclosure (docs/phase6/decisions.md H46) ────────────────────────────

def test_disclosure_is_shown_at_a_tty_when_the_default_was_used(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    inputs = iter(["quit"])

    with patch("builtins.input", side_effect=lambda _: next(inputs)), \
         patch("sys.stdin.isatty", return_value=True):
        interactive_mode(_resolved(is_default=True))

    assert "self-hosted Llama" in capsys.readouterr().out


def test_disclosure_is_not_shown_when_the_provider_was_explicitly_chosen(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    inputs = iter(["quit"])

    with patch("builtins.input", side_effect=lambda _: next(inputs)), \
         patch("sys.stdin.isatty", return_value=True):
        interactive_mode(_resolved(is_default=False))

    assert "self-hosted Llama" not in capsys.readouterr().out


def test_disclosure_is_not_shown_when_stdin_is_not_a_tty(monkeypatch, capsys):
    """The signal only ever gates whether to show the message -- automated callers see nothing extra."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    inputs = iter(["quit"])

    with patch("builtins.input", side_effect=lambda _: next(inputs)), \
         patch("sys.stdin.isatty", return_value=False):
        interactive_mode(_resolved(is_default=True))

    assert "self-hosted Llama" not in capsys.readouterr().out
