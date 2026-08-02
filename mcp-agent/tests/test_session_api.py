"""
Tests for the HTTP transport (docs/phase6/decisions.md H14, H45-H49) --
FastAPI TestClient against agent.api.app, with the session store and LLM
client mocked out (session_store's own DB behavior is covered for real in
agent-platform/tests/test_session_store.py; this file is about the HTTP
layer's own logic: routing, status codes, and that it actually calls
run_query with the loaded session state).

Run:
  python3 -m pytest mcp-agent/tests/test_session_api.py -v
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from agent.api import app

client = TestClient(app)


def _loaded_session(messages, token_count, provider="ollama", model="llama3.2:1b"):
    return SimpleNamespace(messages=messages, token_count=token_count, provider=provider, model=model)


def test_health_returns_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_create_session_with_no_body_uses_the_process_default():
    with patch("agent.api._get_model_and_system", return_value=("llama3.2:1b", "ollama")), \
         patch("agent.api.create_session", return_value="11111111-1111-1111-1111-111111111111") as mock_create:
        resp = client.post("/sessions")

    assert resp.status_code == 200
    assert resp.json() == {
        "session_id": "11111111-1111-1111-1111-111111111111",
        "provider": "ollama",
        "model": "llama3.2:1b",
    }
    mock_create.assert_called_once_with("ollama", "llama3.2:1b")


def test_create_session_with_an_explicit_choice_pins_it(monkeypatch):
    with patch("agent.api.build_client_for", return_value=object()) as mock_build, \
         patch("agent.api.create_session", return_value="new-id") as mock_create:
        resp = client.post("/sessions", json={"provider": "anthropic", "model": "claude-sonnet-4-5"})

    assert resp.status_code == 200
    assert resp.json()["provider"] == "anthropic"
    mock_build.assert_called_once_with("anthropic", "claude-sonnet-4-5")
    mock_create.assert_called_once_with("anthropic", "claude-sonnet-4-5")


def test_create_session_with_only_one_of_provider_or_model_400s():
    resp = client.post("/sessions", json={"provider": "anthropic"})
    assert resp.status_code == 400


def test_create_session_400s_on_a_bad_explicit_pin():
    with patch("agent.api.build_client_for", side_effect=RuntimeError("LLM_BASE_URL is not set.")):
        resp = client.post("/sessions", json={"provider": "openai_compatible", "model": "x"})
    assert resp.status_code == 400


def test_create_session_503s_when_the_store_is_unavailable():
    with patch("agent.api._get_model_and_system", return_value=("llama3.2:1b", "ollama")), \
         patch("agent.api.create_session", side_effect=RuntimeError("DATABASE_URL is not set.")):
        resp = client.post("/sessions")

    assert resp.status_code == 503


def test_query_session_404s_for_an_unknown_session():
    with patch("agent.api.load_session", side_effect=KeyError("nope")):
        resp = client.post("/sessions/does-not-exist/query", json={"query": "hi"})

    assert resp.status_code == 404


def test_query_session_503s_when_the_pinned_provider_cannot_be_rebuilt():
    """E.g. a session pinned to "anthropic" but ANTHROPIC_API_KEY isn't set on this process."""
    with patch("agent.api.load_session", return_value=_loaded_session([], 0, "anthropic", "claude-sonnet-4-5")), \
         patch("agent.api.build_client_for", side_effect=RuntimeError("ANTHROPIC_API_KEY is not set.")):
        resp = client.post("/sessions/some-id/query", json={"query": "hi"})

    assert resp.status_code == 503


def test_query_session_runs_the_agent_loop_and_persists_the_result():
    with patch("agent.api.load_session", return_value=_loaded_session([], 0)) as mock_load, \
         patch("agent.api.build_client_for", return_value=object()), \
         patch("agent.api.save_session") as mock_save, \
         patch(
             "agent.api.run_query",
             return_value=("AGENT DECISION\n\nDISPENSE", [{"role": "user", "content": "hi"}]),
         ) as mock_run_query:
        resp = client.post("/sessions/abc/query", json={"query": "check refill risk"})

    assert resp.status_code == 200
    assert resp.json()["response"] == "AGENT DECISION\n\nDISPENSE"
    mock_load.assert_called_once_with("abc")
    mock_run_query.assert_called_once()
    # The loop's own history (loaded from the session) and the caller's
    # question are what get run, not something reconstructed independently.
    call_kwargs = mock_run_query.call_args
    assert call_kwargs.args[1] == "check refill risk"
    # The session's own pinned provider/model are threaded through, not
    # this process's own default (docs/phase6/decisions.md H49).
    assert call_kwargs.kwargs["model"] == "llama3.2:1b"
    assert call_kwargs.kwargs["gen_ai_system"] == "ollama"
    mock_save.assert_called_once()
    assert mock_save.call_args.args[0] == "abc"


def test_query_session_uses_the_sessions_own_pinned_provider_not_a_different_ones_default():
    """Two sessions on the same process, pinned to different providers, must each use their own."""
    with patch("agent.api.load_session", return_value=_loaded_session([], 0, "anthropic", "claude-opus-4")), \
         patch("agent.api.build_client_for", return_value=object()) as mock_build, \
         patch("agent.api.save_session"), \
         patch("agent.api.run_query", return_value=("...", [])):
        client.post("/sessions/abc/query", json={"query": "hi"})

    mock_build.assert_called_once_with("anthropic", "claude-opus-4")


# ── GET /models (docs/phase6/decisions.md H48) ──────────────────────────

def test_list_models_ollama():
    with patch("agent.api.list_ollama_models", return_value=["llama3.2:1b", "deepseek-r1:1.5b"]):
        resp = client.get("/models", params={"provider": "ollama"})

    assert resp.status_code == 200
    assert resp.json() == {"provider": "ollama", "models": ["llama3.2:1b", "deepseek-r1:1.5b"]}


def test_list_models_anthropic_400s_without_a_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    resp = client.get("/models", params={"provider": "anthropic"})
    assert resp.status_code == 400


def test_list_models_openai_compatible_400s_without_a_base_url(monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    resp = client.get("/models", params={"provider": "openai_compatible"})
    assert resp.status_code == 400


def test_list_models_unrecognized_provider_400s():
    resp = client.get("/models", params={"provider": "not_a_real_provider"})
    assert resp.status_code == 400


def test_list_models_502s_when_discovery_fails():
    import httpx

    with patch("agent.api.list_ollama_models", side_effect=httpx.ConnectError("refused")):
        resp = client.get("/models", params={"provider": "ollama"})

    assert resp.status_code == 502
