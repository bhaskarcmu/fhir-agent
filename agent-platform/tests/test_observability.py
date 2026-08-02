"""
Tests for agent_platform.observability -- the PHI-safe span attribute
allowlist and span helpers (docs/phase6/decisions.md H22, design.md
Section 4.2 PHI-redaction discussion).

Uses OTel's own InMemorySpanExporter (a standard SDK testing utility),
not a live collector -- these tests never need Jaeger running.
"""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agent_platform.observability import (
    ALLOWED_SPAN_ATTRIBUTE_KEYS,
    current_trace_id,
    is_detailed,
    layer_attrs,
    safe_set_attributes,
    start_span,
    verbosity,
)


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


def test_verbosity_defaults_to_standard(monkeypatch):
    monkeypatch.delenv("TELEMETRY_VERBOSITY", raising=False)
    assert verbosity() == "standard"
    assert is_detailed() is False


def test_verbosity_reads_detailed(monkeypatch):
    monkeypatch.setenv("TELEMETRY_VERBOSITY", "detailed")
    assert verbosity() == "detailed"
    assert is_detailed() is True


@pytest.mark.parametrize("raw", ["DETAILED", "  detailed  ", "Detailed"])
def test_verbosity_is_case_and_whitespace_insensitive(monkeypatch, raw):
    monkeypatch.setenv("TELEMETRY_VERBOSITY", raw)
    assert verbosity() == "detailed"


def test_unrecognized_verbosity_fails_closed_to_standard(monkeypatch):
    """An unrecognized value degrades to the lower-volume option, not maximum verbosity."""
    monkeypatch.setenv("TELEMETRY_VERBOSITY", "maximum-overdrive")
    assert verbosity() == "standard"


def test_layer_attrs_shape(monkeypatch):
    monkeypatch.delenv("TELEMETRY_VERBOSITY", raising=False)
    attrs = layer_attrs("triage.rules", "evaluate")
    assert attrs == {
        "fhir_agent.layer": "triage.rules",
        "fhir_agent.component": "evaluate",
        "fhir_agent.verbosity": "standard",
    }


def test_layer_attrs_are_all_allowlisted():
    attrs = layer_attrs("agent.orchestration", "run_query")
    assert set(attrs).issubset(ALLOWED_SPAN_ATTRIBUTE_KEYS)


def test_current_trace_id_none_with_no_active_span():
    assert current_trace_id() is None


def test_current_trace_id_matches_the_active_span():
    tracer, _exporter = _tracer_with_memory_exporter()
    with tracer.start_as_current_span("test.span") as span:
        trace_id = current_trace_id()
        expected = format(span.get_span_context().trace_id, "032x")
        assert trace_id == expected
        assert len(trace_id) == 32


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
