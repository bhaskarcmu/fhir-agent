"""
Shared OTel setup for this repo's LLM agents (docs/phase6/design.md
Section 4.2, decisions.md H22).

One trace per agent run; a span per model call and per tool call, using
`gen_ai.*` semantic-convention attributes. Exports via OTLP to whatever
`OTEL_EXPORTER_OTLP_ENDPOINT` points at -- a local Jaeger instance in dev
(docker compose --profile observability), Cloud Trace later, same code
either way (H22).

PHI safety is structural, not scrub-after-the-fact (mirroring
provider-registry-service's sanitize_location() precedent): span
attributes go through an explicit allowlist, not a denylist. A key that
isn't recognized as safe is dropped, not silently included.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span

# Attributes that are safe to attach to a span: FHIR resource IDs (needed
# for audit/debug correlation, same as this repo's existing Provenance
# resources referencing Patient/id), gen_ai.* semantic-convention fields,
# tool/decision metadata, real OTel code.* semantic-convention fields (source
# location), and this repo's own fhir_agent.* namespace (architectural
# meaning -- see docs/phase6/telemetry-schema.md). Never a name, birth date,
# address, or any other demographic text -- those never get a code path into
# this function to begin with.
ALLOWED_SPAN_ATTRIBUTE_KEYS = frozenset({
    "patient_id",
    "medication_id",
    "risk_level",
    "risk_assessment_id",
    "decision",
    "override_reason",
    "gen_ai.system",
    "gen_ai.request.model",
    "gen_ai.response.finish_reasons",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "gen_ai.tool.name",
    "code.function.name",
    "fhir_agent.layer",
    "fhir_agent.component",
    "fhir_agent.verbosity",
})

# TELEMETRY_VERBOSITY (docs/phase6/telemetry-schema.md Section 4). Deliberately
# not OTEL_-prefixed -- that prefix is reserved for the real OpenTelemetry
# SDK's own environment variables, not repo-specific settings.
VALID_VERBOSITY_LEVELS = ("standard", "detailed")

_configured = False


def setup_tracing(service_name: str) -> None:
    """
    Configure the global TracerProvider once per process. Safe to call
    more than once -- subsequent calls are no-ops.

    OTEL_EXPORTER_OTLP_ENDPOINT defaults to http://localhost:4317 (the
    local Jaeger OTLP gRPC receiver). If nothing is listening there, the
    OTLP exporter fails closed on its own side -- it logs and drops
    spans in the background; it does not raise into application code or
    block a real clinical query.
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

    # Auto-instrument outbound HTTP: the triage-service call in tools.py,
    # and the Anthropic SDK's own internal httpx client -- both get a
    # traceparent header injected automatically, joining this trace with
    # whatever the receiving service does with it (R5).
    HTTPXClientInstrumentor().instrument()

    _configured = True


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)


def verbosity() -> str:
    """
    Current TELEMETRY_VERBOSITY level: "standard" (default, enrich existing
    spans only) or "detailed" (opt-in, adds sub-spans at the one boundary
    documented in docs/phase6/telemetry-schema.md Section 4.2). An
    unrecognized value fails closed to "standard" -- the lower-volume,
    lower-overhead option -- rather than silently going maximally verbose.
    """
    value = os.environ.get("TELEMETRY_VERBOSITY", "standard").strip().lower()
    return value if value in VALID_VERBOSITY_LEVELS else "standard"


def is_detailed() -> bool:
    return verbosity() == "detailed"


def layer_attrs(layer: str, component: str) -> dict:
    """
    The standard fhir_agent.* attribute set for a span at a given
    architectural layer/component (docs/phase6/telemetry-schema.md Section 2).
    Pass the result to safe_set_attributes() or start_span()'s attrs param.
    """
    return {
        "fhir_agent.layer": layer,
        "fhir_agent.component": component,
        "fhir_agent.verbosity": verbosity(),
    }


def current_trace_id() -> str | None:
    """
    The active span's trace ID as a lowercase 32-hex-digit string (the
    standard W3C Trace Context textual form), or None if there is no active
    span. Used to surface the trace ID back to whoever made the request
    (docs/phase6/telemetry-schema.md Section 5) -- a trace ID only visible
    inside span context is useless to a human or test program that isn't
    already looking at the tracing backend.
    """
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if not ctx.is_valid:
        return None
    return format(ctx.trace_id, "032x")


def safe_set_attributes(span: Span, attrs: dict) -> None:
    """
    Set only allowlisted attributes on a span. A key not in
    ALLOWED_SPAN_ATTRIBUTE_KEYS is dropped, not raised on and not
    included -- fail closed on the side of not leaking PHI, not on the
    side of blocking the call.
    """
    for key, value in attrs.items():
        if key not in ALLOWED_SPAN_ATTRIBUTE_KEYS:
            continue
        if value is None:
            continue
        span.set_attribute(key, value)


@contextmanager
def start_span(name: str, tracer: trace.Tracer, attrs: dict | None = None) -> Iterator[Span]:
    """Convenience wrapper: start a span, apply the PHI-safe attribute filter, yield it."""
    with tracer.start_as_current_span(name) as span:
        if attrs:
            safe_set_attributes(span, attrs)
        yield span
