"""
Unit tests for agent_platform.judge (docs/phase6/decisions.md H11,
superseding H7): the LLM-as-judge that runs on every response and can
never override a decision. Fake clients here; see
mcp-agent/tests/test_judge_integration.py for the live test against a
real weak model (H11's standing testing rule).

Run:
  python3 -m pytest agent-platform/tests/test_judge.py -v
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent_platform.judge import JudgeResult, judge_response


def _tool_use(name: str, input_: dict, id_: str = "j1") -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", name=name, input=input_, id=id_)


def _resp(content: list) -> SimpleNamespace:
    return SimpleNamespace(content=content)


class _FakeMessages:
    def __init__(self, response):
        self._response = response

    def create(self, **kwargs):
        return self._response


class _FakeClient:
    def __init__(self, response):
        self.messages = _FakeMessages(response)


class _RaisingClient:
    class _Messages:
        def create(self, **kwargs):
            raise RuntimeError("judge model unreachable")

    messages = _Messages()


def test_judge_returns_a_complete_result_on_a_clean_submit_judgment_call():
    response = _resp([_tool_use("submit_judgment", {
        "groundedness_ok": True, "tone_ok": True, "phi_leak_detected": False, "notes": "",
    })])
    client = _FakeClient(response)

    result = judge_response(client, "test-model", query="check refill risk", rationale="Low risk, dispense.")

    assert result == JudgeResult(available=True, groundedness_ok=True, tone_ok=True, phi_leak_detected=False, notes="")


def test_judge_reports_flagged_concerns():
    response = _resp([_tool_use("submit_judgment", {
        "groundedness_ok": False, "tone_ok": True, "phi_leak_detected": True,
        "notes": "Rationale mentions patient's home address, which wasn't needed.",
    })])
    client = _FakeClient(response)

    result = judge_response(client, "test-model", query="q", rationale="r")

    assert result.available is True
    assert result.groundedness_ok is False
    assert result.phi_leak_detected is True
    assert "address" in result.notes


def test_judge_is_inconclusive_when_the_model_answers_in_free_text():
    """A weak model that doesn't call the tool -- inconclusive, not a crash."""
    response = _resp([SimpleNamespace(type="text", text="Looks fine to me!")])
    client = _FakeClient(response)

    result = judge_response(client, "test-model", query="q", rationale="r")

    assert result == JudgeResult(available=False)


def test_judge_is_inconclusive_on_malformed_tool_input():
    response = _resp([_tool_use("submit_judgment", {"groundedness_ok": True})])  # missing required keys
    client = _FakeClient(response)

    result = judge_response(client, "test-model", query="q", rationale="r")

    assert result == JudgeResult(available=False)


def test_judge_is_inconclusive_and_does_not_raise_when_the_model_call_fails():
    """The core invariant: a broken judge must never take down the response it's evaluating."""
    result = judge_response(_RaisingClient(), "test-model", query="q", rationale="r")
    assert result == JudgeResult(available=False)


@pytest.mark.parametrize("field", ["groundedness_ok", "tone_ok", "phi_leak_detected"])
def test_judge_result_fields_default_to_none_when_unavailable(field):
    result = JudgeResult(available=False)
    assert getattr(result, field) is None
