"""
Tests for the HTTP transport (docs/phase6/decisions.md H14) -- FastAPI
TestClient against agent.api.app, with the session store and Anthropic
client mocked out (session_store's own DB behavior is covered for real in
agent-platform/tests/test_session_store.py; this file is about the HTTP
layer's own logic: routing, status codes, and that it actually calls
run_query with the loaded session state).

Run:
  python3 -m pytest mcp-agent/tests/test_session_api.py -v
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from agent.api import app

client = TestClient(app)


def test_health_returns_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_create_session_returns_a_session_id():
    with patch("agent.api.create_session", return_value="11111111-1111-1111-1111-111111111111"):
        resp = client.post("/sessions")

    assert resp.status_code == 200
    assert resp.json() == {"session_id": "11111111-1111-1111-1111-111111111111"}


def test_create_session_503s_when_the_store_is_unavailable():
    with patch("agent.api.create_session", side_effect=RuntimeError("DATABASE_URL is not set.")):
        resp = client.post("/sessions")

    assert resp.status_code == 503


def test_query_session_404s_for_an_unknown_session():
    with patch("agent.api._get_client", return_value=object()):
        with patch("agent.api.load_session", side_effect=KeyError("nope")):
            resp = client.post("/sessions/does-not-exist/query", json={"query": "hi"})

    assert resp.status_code == 404


def test_query_session_503s_when_no_anthropic_key_is_configured():
    with patch("agent.api._get_client", side_effect=RuntimeError("ANTHROPIC_API_KEY is not set.")):
        resp = client.post("/sessions/some-id/query", json={"query": "hi"})

    assert resp.status_code == 503


def test_query_session_runs_the_agent_loop_and_persists_the_result():
    with patch("agent.api._get_client", return_value=object()), \
         patch("agent.api.load_session", return_value=([], 0)) as mock_load, \
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
    mock_save.assert_called_once()
    assert mock_save.call_args.args[0] == "abc"
