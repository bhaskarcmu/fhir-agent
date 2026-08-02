"""
Integration tests for run_query's context-budget compaction (docs/phase6/
decisions.md H13) -- the real M3 policy that replaced M1's MAX_REPL_TURNS
turn-count stopgap.

Run:
  python3 -m pytest mcp-agent/tests/test_context_budget_integration.py -v
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from agent.agent import run_query
from agent_platform import TOKEN_BUDGET


def _tool_use(name: str, input_: dict, id_: str = "t1") -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", name=name, input=input_, id=id_)


def _resp(stop_reason: str, content: list, usage=None) -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=content,
        usage=usage or SimpleNamespace(input_tokens=100, output_tokens=20),
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


def _fake_execute_tool():
    def _execute(name, inputs):
        import json
        if name == "assess_refill_risk":
            return json.dumps({"risk_level": "LOW", "assessment_id": "risk-1"})
        return json.dumps({"error": f"unexpected tool {name}"})

    return _execute


def _old_turn_plus_new_batch():
    """A pre-existing turn (from a prior call) followed by the model's response to a new one."""
    return [
        _resp("tool_use", [_tool_use("assess_refill_risk", {"patient_id": "patient-1"})]),
        _resp("tool_use", [_tool_use(
            "submit_decision",
            {"decision": "DISPENSE", "patient_id": "patient-1", "rationale": "ok"},
        )]),
    ]


def test_under_budget_leaves_prior_history_untouched():
    prior_messages = [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": [{"type": "text", "text": "an earlier answer"}]},
    ]
    client = _FakeClient(_old_turn_plus_new_batch())
    with patch("agent.agent.execute_tool", _fake_execute_tool()):
        _final_text, messages = run_query(
            client, "second question", list(prior_messages), verbose=False, token_count=100,
        )

    # The old turn is still there -- nothing was dropped.
    assert messages[0] == prior_messages[0]
    assert messages[1] == prior_messages[1]


def test_over_budget_drops_the_oldest_turn_before_the_new_query_runs():
    # Two complete prior turns -- compact() must have more than one turn to
    # work with before it will drop anything (never discard the only
    # conversation the caller is actively having, per context_budget.py).
    prior_messages = [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": [{"type": "text", "text": "an earlier answer"}]},
        {"role": "user", "content": "second question"},
        {"role": "assistant", "content": [{"type": "text", "text": "another earlier answer"}]},
    ]
    client = _FakeClient(_old_turn_plus_new_batch())
    with patch("agent.agent.execute_tool", _fake_execute_tool()):
        _final_text, messages = run_query(
            client,
            "third question",
            list(prior_messages),
            verbose=False,
            token_count=TOKEN_BUDGET + 1,
        )

    # The oldest turn is gone; the second prior turn and the new question remain.
    assert prior_messages[0] not in messages
    assert prior_messages[1] not in messages
    assert messages[0] == {"role": "user", "content": "second question"}
    assert {"role": "user", "content": "third question"} in messages


def test_stats_dict_receives_the_new_token_count():
    client = _FakeClient(_old_turn_plus_new_batch())
    stats: dict = {}
    with patch("agent.agent.execute_tool", _fake_execute_tool()):
        run_query(client, "check refill risk", verbose=False, stats=stats)

    # Both fake responses set input_tokens=100 by default -- the stats dict
    # should reflect the *last* real response's usage, the current
    # conversation size, not an accumulated sum.
    assert stats["token_count"] == 100


def test_return_arity_is_unchanged_stats_is_purely_additive():
    """Every pre-M3 call site (2-tuple unpacking) must keep working unmodified."""
    client = _FakeClient(_old_turn_plus_new_batch())
    with patch("agent.agent.execute_tool", _fake_execute_tool()):
        result = run_query(client, "check refill risk", verbose=False)

    assert len(result) == 2
    final_text, messages = result
    assert isinstance(final_text, str)
    assert isinstance(messages, list)
