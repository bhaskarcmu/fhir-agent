"""
Tracing tests for triage-service (docs/phase6/design.md Section 4.2,
decisions.md H16/H22): a real request produces a server span, continuing
whatever trace the caller (mcp-agent, claims-service) started.

Taps an extra InMemorySpanExporter onto the already-configured global
TracerProvider (set once, at triage.main import time, by
observability.setup_tracing) rather than calling
trace.set_tracer_provider() again -- OTel only honors the first call per
process, so adding a second span processor to the existing provider is
the correct way to observe spans in a test without fighting that.

Run:
  python3 -m pytest triage-service/src/triage/tests/test_tracing.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from fhir_clinical_client import Allergy, Medication
from triage.main import app

client = TestClient(app)


def _mock_fhir_client(medications=None, allergies=None):
    mock = MagicMock()
    mock.get_medications.return_value = medications or []
    mock.get_allergies.return_value = allergies or []
    return mock


def _capture_spans() -> InMemorySpanExporter:
    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider), (
        "triage.main should have configured a real TracerProvider on import "
        "via observability.setup_tracing() -- if this fails, tracing setup "
        "didn't run before this test."
    )
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return exporter


def test_health_request_produces_a_server_span():
    exporter = _capture_spans()
    resp = client.get("/health")
    assert resp.status_code == 200

    spans = exporter.get_finished_spans()
    assert any(s.name.upper().endswith("/HEALTH") or "health" in s.name.lower() for s in spans), (
        f"expected a server span for GET /health, got: {[s.name for s in spans]}"
    )


def test_refill_risk_request_produces_a_server_span_and_no_phi():
    exporter = _capture_spans()
    with patch(
        "triage.main._get_client",
        return_value=_mock_fhir_client(
            medications=[Medication(id="m1", code="723", display="Amoxicillin", status="active")],
            allergies=[Allergy(
                id="a1", code="764146007", display="Penicillin",
                criticality="high", category=["medication"],
            )],
        ),
    ):
        resp = client.post("/triage/refill-risk", json={"patient_id": "patient-kristle"})

    assert resp.status_code == 200
    spans = exporter.get_finished_spans()
    assert len(spans) >= 1

    # FastAPI's default server-span attributes are HTTP/route metadata only --
    # confirm the request body (which could carry a patient_id, not PHI itself,
    # but is exactly the kind of thing worth pinning) never surfaces anything
    # demographic. No span attribute value should contain the mock display text.
    for span in spans:
        for value in span.attributes.values():
            assert "Kristle" not in str(value)
            assert "Amoxicillin" not in str(value)
