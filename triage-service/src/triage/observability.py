"""
OTel setup for triage-service (docs/phase6/design.md Section 4.2,
decisions.md H16/H22).

Deliberately NOT shared via agent_platform -- triage-service is
deterministic-tier code, not an LLM agent, and depending on a package
named "agent platform" from a service that has no clinical-agent
concerns would blur exactly the boundary this repo's conventions are
built around ("AI explains and orchestrates; deterministic services
decide"). A small, independent setup here is the right amount of
duplication for ~15 lines used in one place.

FastAPI + urllib auto-instrumentation together give this service the
whole propagation story for free: FastAPIInstrumentor extracts an
incoming traceparent header and starts a server span continuing that
trace; URLLibInstrumentor injects the same trace context into every
outbound urllib.request call fhir-clinical-client makes -- so a trace
started in mcp-agent or claims-service continues all the way into
fhir-service through triage-service, with zero changes to
fhir_clinical_client itself.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.urllib import URLLibInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_configured = False


def setup_tracing(app: FastAPI, service_name: str = "triage-service") -> None:
    """
    Configure tracing once per process. OTEL_EXPORTER_OTLP_ENDPOINT
    defaults to http://localhost:4317 (the local Jaeger OTLP receiver);
    if nothing is listening there the exporter fails closed on its own
    side -- it logs and drops spans in the background, it never blocks
    or fails a real clinical request.
    """
    global _configured
    if _configured:
        return

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    URLLibInstrumentor().instrument()

    _configured = True
