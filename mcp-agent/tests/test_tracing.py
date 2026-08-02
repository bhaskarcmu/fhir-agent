"""
End-to-end tracing tests for run_query (docs/phase6/design.md Section 4.2,
decisions.md H22): one trace per agent run, spans per model/tool call,
gen_ai.* attributes, and -- the part that actually matters -- no PHI
anywhere in the exported spans even when the clinician's own query text
contains a patient name.

Uses OTel's InMemorySpanExporter (a standard SDK testing utility) bound
directly to agent.agent's module-level tracer via patching, rather than
touching the process-wide global TracerProvider (which OTel only allows
setting once per process -- see the docstring on the fixture below).

Run:
  python3 -m pytest mcp-agent/tests/test_tracing.py -v
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agent.agent import run_query


def _tool_use(name: str, input_: dict, id_: str = "t1") -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", name=name, input=input_, id=id_)


def _resp(stop_reason: str, content: list, usage=None) -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=content,
        usage=usage or SimpleNamespace(input_tokens=100, output_tokens=20),
    )


class _FakeMessages:
    def __init__(self, responses: list):
        self._responses = list(responses)

    def create(self, **kwargs):
        return self._responses.pop(0)


class _FakeClient:
    def __init__(self, responses: list):
        self.messages = _FakeMessages(responses)


def _fake_execute_tool(risk_level: str = "LOW"):
    def _execute(name: str, inputs: dict) -> str:
        if name == "assess_refill_risk":
            return json.dumps({"risk_level": risk_level, "assessment_id": "risk-1"})
        return json.dumps({"error": f"unexpected tool {name}"})

    return _execute


@pytest.fixture
def memory_tracer():
    """
    A tracer backed by InMemorySpanExporter, patched onto agent.agent's
    module-level _tracer for the duration of one test. Deliberately does
    NOT call trace.set_tracer_provider() -- OTel only honors the first
    call per process, so a test-local TracerProvider plus patching the
    consumer's tracer reference is the safe way to isolate span capture
    without fighting global state or ordering across the test session.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    with patch("agent.agent._tracer", tracer):
        yield exporter


def test_one_root_span_per_run_query_call(memory_tracer):
    responses = [
        _resp("tool_use", [_tool_use("assess_refill_risk", {"patient_id": "patient-1"})]),
        _resp("tool_use", [_tool_use(
            "submit_decision",
            {"decision": "DISPENSE", "patient_id": "patient-1", "rationale": "ok"},
        )]),
    ]
    client = _FakeClient(responses)
    with patch("agent.agent.execute_tool", _fake_execute_tool()):
        run_query(client, "check refill risk for a patient", verbose=False)

    spans = memory_tracer.get_finished_spans()
    root_spans = [s for s in spans if s.name == "agent.run_query"]
    assert len(root_spans) == 1


def test_chat_and_tool_and_decision_spans_are_all_present(memory_tracer):
    responses = [
        _resp("tool_use", [_tool_use("assess_refill_risk", {"patient_id": "patient-1"})]),
        _resp("tool_use", [_tool_use(
            "submit_decision",
            {"decision": "DISPENSE", "patient_id": "patient-1", "rationale": "ok"},
        )]),
    ]
    client = _FakeClient(responses)
    with patch("agent.agent.execute_tool", _fake_execute_tool()):
        run_query(client, "check refill risk", verbose=False)

    names = [s.name for s in memory_tracer.get_finished_spans()]
    assert "agent.run_query" in names
    assert any(n.startswith("chat ") for n in names)
    assert "execute_tool assess_refill_risk" in names
    assert "agent.submit_decision" in names


def test_gen_ai_attributes_on_chat_span(memory_tracer):
    responses = [
        _resp("tool_use", [_tool_use("assess_refill_risk", {"patient_id": "patient-1"})]),
        _resp("tool_use", [_tool_use(
            "submit_decision",
            {"decision": "DISPENSE", "patient_id": "patient-1", "rationale": "ok"},
        )]),
    ]
    client = _FakeClient(responses)
    with patch("agent.agent.execute_tool", _fake_execute_tool()):
        run_query(client, "check refill risk", verbose=False)

    chat_spans = [s for s in memory_tracer.get_finished_spans() if s.name.startswith("chat ")]
    assert len(chat_spans) == 2  # one per client.messages.create() call
    attrs = dict(chat_spans[0].attributes)
    assert attrs["gen_ai.system"] == "anthropic"
    assert attrs["gen_ai.usage.input_tokens"] == 100
    assert attrs["gen_ai.usage.output_tokens"] == 20


def test_decision_span_carries_the_fail_closed_override(memory_tracer):
    responses = [
        _resp("tool_use", [_tool_use("assess_refill_risk", {"patient_id": "patient-1"})]),
        _resp("tool_use", [_tool_use(
            "submit_decision",
            {"decision": "DISPENSE", "patient_id": "patient-1", "rationale": "ok"},
        )]),
    ]
    client = _FakeClient(responses)
    with patch("agent.agent.execute_tool", _fake_execute_tool(risk_level="UNKNOWN")):
        run_query(client, "check refill risk", verbose=False)

    decision_span = next(
        s for s in memory_tracer.get_finished_spans() if s.name == "agent.submit_decision"
    )
    attrs = dict(decision_span.attributes)
    assert attrs["decision"] == "REVIEW"
    assert "UNKNOWN" in attrs["override_reason"]


def test_no_span_ever_carries_the_patients_name(memory_tracer):
    """
    The whole point of the PHI-safe attribute allowlist (agent_platform.
    observability): a clinician's query text naming a real patient must
    never end up on any exported span, anywhere, even though it flows
    through the function as user_input.
    """
    responses = [
        _resp("tool_use", [_tool_use("assess_refill_risk", {"patient_id": "patient-1"})]),
        _resp("tool_use", [_tool_use(
            "submit_decision",
            {"decision": "DISPENSE", "patient_id": "patient-1", "rationale": "ok"},
        )]),
    ]
    client = _FakeClient(responses)
    with patch("agent.agent.execute_tool", _fake_execute_tool()):
        run_query(client, "Check refill risk for Kristle Mraz", verbose=False)

    for span in memory_tracer.get_finished_spans():
        for value in span.attributes.values():
            assert "Kristle" not in str(value)
            assert "Mraz" not in str(value)


def test_spans_carry_layer_and_component_attributes(memory_tracer):
    """docs/phase6/telemetry-schema.md Section 3.1 -- the agent-tier layer taxonomy."""
    responses = [
        _resp("tool_use", [_tool_use("assess_refill_risk", {"patient_id": "patient-1"})]),
        _resp("tool_use", [_tool_use(
            "submit_decision",
            {"decision": "DISPENSE", "patient_id": "patient-1", "rationale": "ok"},
        )]),
    ]
    client = _FakeClient(responses)
    with patch("agent.agent.execute_tool", _fake_execute_tool()):
        run_query(client, "check refill risk", verbose=False)

    by_name = {s.name: s for s in memory_tracer.get_finished_spans()}

    assert by_name["agent.run_query"].attributes["fhir_agent.layer"] == "agent.orchestration"
    assert by_name["agent.run_query"].attributes["fhir_agent.component"] == "run_query"
    assert by_name["agent.run_query"].attributes["fhir_agent.verbosity"] == "standard"

    assert by_name["execute_tool assess_refill_risk"].attributes["fhir_agent.layer"] == "agent.tools"
    assert (
        by_name["execute_tool assess_refill_risk"].attributes["fhir_agent.component"]
        == "assess_refill_risk"
    )

    assert by_name["agent.submit_decision"].attributes["fhir_agent.layer"] == "agent.orchestration"
    assert by_name["agent.submit_decision"].attributes["fhir_agent.component"] == "submit_decision"


def test_decision_block_output_includes_the_trace_id(memory_tracer):
    """docs/phase6/telemetry-schema.md Section 5 -- surfaced to the CLI user, not just Jaeger."""
    responses = [
        _resp("tool_use", [_tool_use("assess_refill_risk", {"patient_id": "patient-1"})]),
        _resp("tool_use", [_tool_use(
            "submit_decision",
            {"decision": "DISPENSE", "patient_id": "patient-1", "rationale": "ok"},
        )]),
    ]
    client = _FakeClient(responses)
    with patch("agent.agent.execute_tool", _fake_execute_tool()):
        final_text, _ = run_query(client, "check refill risk", verbose=False)

    assert "Trace ID:" in final_text
    assert "Trace ID: (none)" not in final_text

    root_span = next(
        s for s in memory_tracer.get_finished_spans() if s.name == "agent.run_query"
    )
    expected_trace_id = format(root_span.context.trace_id, "032x")
    assert expected_trace_id in final_text
