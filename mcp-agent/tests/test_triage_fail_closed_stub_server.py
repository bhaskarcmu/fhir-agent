"""
Contract test for assess_refill_risk's fail-closed data-layer guard, over a
real HTTP round-trip against a stub triage server -- not object-mocked
httpx.post. Mirrors claims-service's HttpTriageClientTest.java: a mocked
client can't catch a transport bug like a silently-empty request body, and
this pins the same fail-closed contract on the Python side
(docs/phase6/decisions.md H18): every path that doesn't yield a risk level
we understand maps to RISK_UNKNOWN, never LOW.

Run:
  python3 -m pytest mcp-agent/tests/test_triage_fail_closed_stub_server.py -v
"""

from __future__ import annotations

import http.server
import json
import threading
from contextlib import contextmanager

import pytest

from agent.tools import assess_refill_risk
from agent_platform import RISK_UNKNOWN


class _StubHandler(http.server.BaseHTTPRequestHandler):
    status = 200
    body = b"{}"
    last_request_body: bytes | None = None

    def do_POST(self):  # noqa: N802 (stdlib method name)
        length = int(self.headers.get("Content-Length", 0))
        type(self).last_request_body = self.rfile.read(length)
        self.send_response(type(self).status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(type(self).body)

    def log_message(self, *args):  # keep test output quiet
        pass


@contextmanager
def _stub_server(status: int, body: dict):
    _StubHandler.status = status
    _StubHandler.body = json.dumps(body).encode()
    _StubHandler.last_request_body = None
    server = http.server.HTTPServer(("127.0.0.1", 0), _StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", _StubHandler
    finally:
        server.shutdown()
        thread.join()


def _risk_response(code: str) -> dict:
    return {
        "resourceType": "RiskAssessment",
        "id": "risk-stub",
        "prediction": [{"outcome": {"coding": [{"code": code}]}}],
        "note": [{"text": "stub"}],
        "basis": [],
    }


@pytest.mark.parametrize("code", ["HIGH", "MODERATE", "LOW"])
def test_recognized_codes_pass_through_over_real_http(monkeypatch, code):
    with _stub_server(200, _risk_response(code)) as (url, handler):
        monkeypatch.setenv("TRIAGE_SERVICE_URL", url)
        result = assess_refill_risk(patient_id="patient-1")

    assert result["risk_level"] == code
    # Pin the actual request body -- exactly the class of bug a mocked
    # httpx.post can't catch (a silently-empty or malformed body).
    sent = json.loads(handler.last_request_body)
    assert sent["patient_id"] == "patient-1"


def test_unrecognized_code_over_real_http_fails_closed(monkeypatch):
    with _stub_server(200, _risk_response("SEVERE")) as (url, _handler):
        monkeypatch.setenv("TRIAGE_SERVICE_URL", url)
        result = assess_refill_risk(patient_id="patient-1")

    assert result["risk_level"] == RISK_UNKNOWN
    assert "error" in result


def test_5xx_over_real_http_fails_closed(monkeypatch):
    with _stub_server(500, {"detail": "internal error"}) as (url, _handler):
        monkeypatch.setenv("TRIAGE_SERVICE_URL", url)
        result = assess_refill_risk(patient_id="patient-1")

    assert result["risk_level"] == RISK_UNKNOWN
    assert "error" in result


def test_malformed_body_over_real_http_fails_closed(monkeypatch):
    """A 200 with a body that doesn't even match the expected shape."""
    with _stub_server(200, {"unexpected": "shape"}) as (url, _handler):
        monkeypatch.setenv("TRIAGE_SERVICE_URL", url)
        result = assess_refill_risk(patient_id="patient-1")

    assert result["risk_level"] == RISK_UNKNOWN


def test_connection_refused_fails_closed(monkeypatch):
    """No server listening at all -- a real transport failure, not simulated."""
    probe = http.server.HTTPServer(("127.0.0.1", 0), _StubHandler)
    port = probe.server_port
    probe.server_close()  # release the port; nothing is listening on it now

    monkeypatch.setenv("TRIAGE_SERVICE_URL", f"http://127.0.0.1:{port}")
    result = assess_refill_risk(patient_id="patient-1")

    assert result["risk_level"] == RISK_UNKNOWN
    assert "error" in result
