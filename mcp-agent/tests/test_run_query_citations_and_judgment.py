"""
Integration tests: run_query actually wires M6's citations and judge
result through to the final decision_block (docs/phase6/decisions.md
H11, H15) -- not just that the underlying functions work in isolation
(see test_format.py, agent-platform/tests/test_judge.py,
agent-platform/tests/test_knowledge.py for those).

Run:
  python3 -m pytest mcp-agent/tests/test_run_query_citations_and_judgment.py -v
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

from agent.agent import run_query
from agent_platform import JudgeResult


def _tool_use(name: str, input_: dict, id_: str = "t1") -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", name=name, input=input_, id=id_)


def _resp(stop_reason: str, content: list) -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason=stop_reason, content=content,
        usage=SimpleNamespace(input_tokens=100, output_tokens=20),
    )


class _FakeClient:
    def __init__(self, responses: list):
        self._responses = list(responses)

    class _Messages:
        def __init__(self, outer):
            self._outer = outer

        def create(self, **kwargs):
            return self._outer._responses.pop(0)

    @property
    def messages(self):
        return self._Messages(self)


def _fake_execute_tool(flagged_medications=None):
    def _execute(name, inputs):
        if name == "assess_refill_risk":
            result = {"risk_level": "HIGH", "assessment_id": "risk-1"}
            if flagged_medications:
                result["flagged_medications"] = flagged_medications
            return json.dumps(result)
        return json.dumps({"error": f"unexpected tool {name}"})

    return _execute


def _decision_responses():
    return [
        _resp("tool_use", [_tool_use("assess_refill_risk", {"patient_id": "p1"})]),
        _resp("tool_use", [_tool_use(
            "submit_decision",
            {"decision": "DO_NOT_DISPENSE", "patient_id": "p1", "rationale": "Penicillin conflict."},
        )]),
    ]


def test_citations_appear_when_a_flagged_medication_is_present():
    client = _FakeClient(_decision_responses())
    flagged = [{"rxnorm_code": "723", "display": "Amoxicillin 500 MG Oral Capsule"}]
    fake_citation = {"source": "openFDA Drug Label API", "boxed_warning": None, "contraindications": "Do not use."}

    with patch("agent.agent.execute_tool", _fake_execute_tool(flagged)), \
         patch("agent.agent.fetch_drug_label_citation", return_value=fake_citation), \
         patch("agent.agent.fetch_drug_class", return_value=[{"class_name": "PENICILLINS", "class_type": "VA"}]), \
         patch("agent.agent.judge_response", return_value=JudgeResult(available=False)):
        final_text, _messages = run_query(client, "check refill risk", verbose=False)

    assert "Citations:" in final_text
    assert "Amoxicillin" in final_text
    assert "Do not use." in final_text
    assert "PENICILLINS" in final_text


def test_no_citations_section_when_nothing_was_flagged():
    client = _FakeClient(_decision_responses())

    with patch("agent.agent.execute_tool", _fake_execute_tool(flagged_medications=None)), \
         patch("agent.agent.judge_response", return_value=JudgeResult(available=False)):
        final_text, _messages = run_query(client, "check refill risk", verbose=False)

    assert "Citations:" not in final_text


def test_judge_result_is_threaded_through_to_the_final_text():
    client = _FakeClient(_decision_responses())
    flagged_judgment = JudgeResult(
        available=True, groundedness_ok=False, tone_ok=True, phi_leak_detected=False,
        notes="Rationale is too generic.",
    )

    with patch("agent.agent.execute_tool", _fake_execute_tool()), \
         patch("agent.agent.judge_response", return_value=flagged_judgment) as mock_judge:
        final_text, _messages = run_query(client, "check refill risk", verbose=False)

    mock_judge.assert_called_once()
    call_kwargs = mock_judge.call_args.kwargs
    assert call_kwargs["query"] == "check refill risk"
    assert "Penicillin conflict" in call_kwargs["rationale"]
    assert "Quality review flagged" in final_text
    assert "too generic" in final_text


def test_a_real_judge_failure_does_not_affect_the_decision_or_crash_run_query():
    """
    The core invariant (docs/phase6/decisions.md H11), exercised through
    the real judge_response (not mocked) this time: _decision_responses()
    supplies exactly 2 canned responses for the main loop, so when
    judge_response makes its own (3rd) call to the same fake client, the
    queue is empty -- a real failure, absorbed by judge_response's own
    broad exception handling, not simulated by mocking it away.
    """
    client = _FakeClient(_decision_responses())

    with patch("agent.agent.execute_tool", _fake_execute_tool()):
        final_text, _messages = run_query(client, "check refill risk", verbose=False)

    assert "DO NOT DISPENSE" in final_text  # the real decision, untouched
    assert "Quality review" not in final_text  # judge was inconclusive, not flagged


def test_citation_lookup_functions_are_called_with_the_flagged_medications_data():
    client = _FakeClient(_decision_responses())
    flagged = [{"rxnorm_code": "723", "display": "Amoxicillin 500 MG Oral Capsule"}]

    with patch("agent.agent.execute_tool", _fake_execute_tool(flagged)), \
         patch("agent.agent.fetch_drug_label_citation", return_value=None) as mock_label, \
         patch("agent.agent.fetch_drug_class", return_value=[]) as mock_class, \
         patch("agent.agent.judge_response", return_value=JudgeResult(available=False)):
        run_query(client, "check refill risk", verbose=False)

    mock_label.assert_called_once_with("Amoxicillin")
    mock_class.assert_called_once_with("723")
