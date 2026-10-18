"""OpenTelemetry for the scoring service — triage-service's pattern (docs/phase6, H16/H22).

Deliberately a small copy, not shared via agent_platform: like triage-service, this is a
deterministic-tier service, not an LLM agent. FastAPI instrumentation continues an incoming
trace; urllib instrumentation carries it into every `client/clinical` call to the FHIR server.
If nothing listens at OTEL_EXPORTER_OTLP_ENDPOINT the exporter drops spans in the background —
it never blocks or fails a request.
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


def tag_current_span(component: str, **attributes) -> None:
    span = trace.get_current_span()
    span.set_attribute("fhir_agent.layer", "deterministic")
    span.set_attribute("fhir_agent.component", component)
    for key, value in attributes.items():
        span.set_attribute(f"fhir_agent.{key}", value)


def current_trace_id() -> str | None:
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else None


def setup_tracing(app: FastAPI, service_name: str = "outcome-prediction-service") -> None:
    global _configured
    if _configured:
        return
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    URLLibInstrumentor().instrument()
    _configured = True
