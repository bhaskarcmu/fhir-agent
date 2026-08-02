"""
Tests for agent_platform.observability -- the PHI-safe span attribute
allowlist and span helpers (docs/phase6/decisions.md H22, design.md
Section 4.2 PHI-redaction discussion).

Uses OTel's own InMemorySpanExporter (a standard SDK testing utility),
not a live collector -- these tests never need Jaeger running.
"""

from __future__ import annotations

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agent_platform.observability import ALLOWED_SPAN_ATTRIBUTE_KEYS, safe_set_attributes, start_span


def _tracer_with_memory_exporter():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter


def test_allowlisted_attributes_pass_through():
    tracer, exporter = _tracer_with_memory_exporter()
    with tracer.start_as_current_span("test.span") as span:
        safe_set_attributes(span, {"patient_id": "p1", "risk_level": "HIGH"})

    attrs = dict(exporter.get_finished_spans()[0].attributes)
    assert attrs == {"patient_id": "p1", "risk_level": "HIGH"}


def test_phi_shaped_keys_are_dropped_not_raised():
    """
    The core hazard this module exists to close: a caller passing a
    demographic field must not leak it onto a span, and must not crash
    the agent turn either -- fail closed by silently dropping.
    """
    tracer, exporter = _tracer_with_memory_exporter()
    with tracer.start_as_current_span("test.span") as span:
        safe_set_attributes(span, {
            "patient_id": "p1",
            "given_name": "Kristle",
            "family_name": "Mraz",
            "birth_date": "1980-01-01",
            "address": "123 Main St",
        })

    attrs = dict(exporter.get_finished_spans()[0].attributes)
    assert attrs == {"patient_id": "p1"}


def test_none_values_are_dropped():
    tracer, exporter = _tracer_with_memory_exporter()
    with tracer.start_as_current_span("test.span") as span:
        safe_set_attributes(span, {"patient_id": "p1", "risk_assessment_id": None})

    attrs = dict(exporter.get_finished_spans()[0].attributes)
    assert attrs == {"patient_id": "p1"}


def test_start_span_context_manager_applies_the_same_filter():
    tracer, exporter = _tracer_with_memory_exporter()
    with start_span("test.span", tracer, {"patient_id": "p1", "given_name": "Kristle"}):
        pass

    attrs = dict(exporter.get_finished_spans()[0].attributes)
    assert attrs == {"patient_id": "p1"}


def test_gen_ai_semantic_convention_keys_are_allowlisted():
    """Model-call spans need these; confirm they aren't accidentally dropped."""
    tracer, exporter = _tracer_with_memory_exporter()
    with tracer.start_as_current_span("test.span") as span:
        safe_set_attributes(span, {
            "gen_ai.system": "anthropic",
            "gen_ai.request.model": "claude-sonnet-4-5",
            "gen_ai.usage.input_tokens": 42,
            "gen_ai.usage.output_tokens": 7,
        })

    attrs = dict(exporter.get_finished_spans()[0].attributes)
    assert attrs["gen_ai.system"] == "anthropic"
    assert attrs["gen_ai.usage.input_tokens"] == 42


def test_allowlist_has_no_demographic_looking_keys():
    """
    A structural guard on the guard: fail the test suite itself if someone
    adds a demographic-shaped key to the allowlist by mistake. Deliberately
    specific phrases, not a bare "name" substring -- that would also flag
    legitimate non-PHI keys like gen_ai.tool.name (a tool's name, not a
    patient's).
    """
    blocked_phrases = (
        "given_name", "family_name", "patient_name", "birth", "address",
        "dob", "gender",
    )
    for key in ALLOWED_SPAN_ATTRIBUTE_KEYS:
        lowered = key.lower()
        assert not any(bad in lowered for bad in blocked_phrases), (
            f"{key!r} looks demographic and should not be in the allowlist"
        )
