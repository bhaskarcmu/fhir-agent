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

# TELEMETRY_VERBOSITY / fhir_agent.* / trace-ID surfacing (docs/phase6/
# telemetry-schema.md). Small, deliberate duplication of agent-platform's
# equivalent helpers -- see the module docstring for why this isn't shared.
VALID_VERBOSITY_LEVELS = ("standard", "detailed")

_configured = False


def verbosity() -> str:
    value = os.environ.get("TELEMETRY_VERBOSITY", "standard").strip().lower()
    return value if value in VALID_VERBOSITY_LEVELS else "standard"


def is_detailed() -> bool:
    return verbosity() == "detailed"


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)


def tag_current_span(layer: str, component: str) -> None:
    """
    Enrich whatever span is currently active (typically the auto-instrumented
    FastAPI server span) with fhir_agent.layer/.component/.verbosity. Doesn't
    create a new span -- this is the "standard" verbosity path: attribute
    enrichment on spans that already exist, not new span volume.
    """
    span = trace.get_current_span()
    span.set_attribute("fhir_agent.layer", layer)
    span.set_attribute("fhir_agent.component", component)
    span.set_attribute("fhir_agent.verbosity", verbosity())


def current_trace_id() -> str | None:
    """The active span's trace ID as lowercase hex, or None with no active span."""
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return None
    return format(ctx.trace_id, "032x")


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
