"""
M4 additions to the HTTP transport (docs/phase6/milestone-plan.md M4):
the concurrency limiter in front of query_session, and the /metrics
endpoint. See test_session_api.py for the M3/M5 session-routing tests this
builds on, and test_resilience_integration.py for the breaker/cost-limit
chaos tests exercised through run_query directly.

Run:
  python3 -m pytest mcp-agent/tests/test_api_resilience.py -v
"""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import patch

import anthropic
import httpx
from fastapi.testclient import TestClient

from agent.api import app

client = TestClient(app)


def _loaded_session(messages=None, token_count=0, provider="ollama", model="llama3.2:1b"):
    return SimpleNamespace(messages=messages or [], token_count=token_count, provider=provider, model=model)


def test_query_session_503s_when_the_concurrency_limit_is_exhausted():
    with patch("agent.api._query_slots", threading.Semaphore(0)), \
         patch("agent.api._QUERY_QUEUE_DEADLINE_SECONDS", 0.05), \
         patch("agent.api.load_session", return_value=_loaded_session()), \
         patch("agent.api.build_client_for", return_value=object()):
        resp = client.post("/sessions/abc/query", json={"query": "hi"})

    assert resp.status_code == 503
    assert "concurrent" in resp.json()["detail"].lower()


def test_query_session_releases_the_slot_after_a_normal_request():
    with patch("agent.api.load_session", return_value=_loaded_session()), \
         patch("agent.api.build_client_for", return_value=object()), \
         patch("agent.api.save_session"), \
         patch("agent.api.run_query", return_value=("AGENT DECISION\n\nREVIEW", [])):
        first = client.post("/sessions/abc/query", json={"query": "hi"})
        second = client.post("/sessions/abc/query", json={"query": "hi again"})

    assert first.status_code == 200
    assert second.status_code == 200


def test_query_session_502s_on_an_individual_llm_api_failure():
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    exc = anthropic.AuthenticationError(
        "invalid x-api-key", response=httpx.Response(401, request=request), body=None
    )
    with patch("agent.api.load_session", return_value=_loaded_session()), \
         patch("agent.api.build_client_for", return_value=object()), \
         patch("agent.api.run_query", side_effect=exc):
        resp = client.post("/sessions/abc/query", json={"query": "hi"})

    assert resp.status_code == 502
    assert "invalid x-api-key" in resp.json()["detail"]


def test_metrics_endpoint_exposes_prometheus_text():
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "fhir_agent_llm_calls_total" in resp.text
