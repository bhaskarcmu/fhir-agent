"""
Tests for the M1 output contract: submit_decision + the fail-closed enum
gate wired into agent.run_query (docs/phase6/design.md Section 4.1,
docs/phase6/decisions.md H5, H10, H18, H21).

Three layers:
  1. Loop-level tests against a fake Anthropic client (canned tool-use
     responses) -- exercise the enforcement logic in agent.py itself.
  2. Adversarial parametrized cases simulating the malformed/off-contract
     shapes a genuinely weak model produces.
  3. A live local-LLM test against Ollama, self-skipping when unreachable
     -- same convention as provider-registry-service's DB-backed tests --
     satisfying the standing local-LLM testing rule (decisions.md H11)
     without requiring the formal provider adapter (M5) to exist yet.

Run:
  python3 -m pytest mcp-agent/tests/test_output_contract.py -v
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent.agent import run_query
from agent_platform import AgentDecision, validate_decision


# ─────────────────────────────────────────────────────────────────────────────
# Fake Anthropic client -- replays canned responses, no network
# ─────────────────────────────────────────────────────────────────────────────

def _tool_use(name: str, input_: dict, id_: str = "t1") -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", name=name, input=input_, id=id_)


def _text(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def _resp(stop_reason: str, content: list) -> SimpleNamespace:
    return SimpleNamespace(stop_reason=stop_reason, content=content)


class _FakeMessages:
    def __init__(self, responses: list):
        self._responses = list(responses)

    def create(self, **kwargs):
        return self._responses.pop(0)


class _FakeClient:
    """A minimal stand-in for anthropic.Anthropic that replays canned responses."""

    def __init__(self, responses: list):
        self.messages = _FakeMessages(responses)


def _fake_execute_tool(risk_level: str = "LOW", assessment_id: str = "risk-1"):
    def _execute(name: str, inputs: dict) -> str:
        if name == "assess_refill_risk":
            return json.dumps({"risk_level": risk_level, "assessment_id": assessment_id})
        if name == "get_patient_summary":
            return json.dumps({"found": True, "patient": {"id": "patient-1", "name": "Test Patient"}})
        return json.dumps({"error": f"unexpected tool {name}"})

    return _execute


# ─────────────────────────────────────────────────────────────────────────────
# 1. Loop-level behavior
# ─────────────────────────────────────────────────────────────────────────────

class TestSubmitDecisionHappyPath:
    def test_low_risk_dispense_is_accepted_unchanged(self):
        responses = [
            _resp("tool_use", [_tool_use("assess_refill_risk", {"patient_id": "patient-1"})]),
            _resp("tool_use", [_tool_use(
                "submit_decision",
                {"decision": "DISPENSE", "patient_id": "patient-1",
                 "risk_assessment_id": "risk-1", "rationale": "No conflicts found."},
            )]),
        ]
        client = _FakeClient(responses)
        with patch("agent.agent.execute_tool", _fake_execute_tool(risk_level="LOW")):
            final_text, messages = run_query(client, "check refill risk", verbose=False)

        assert "DISPENSE" in final_text
        assert "DO NOT DISPENSE" not in final_text
        assert "Fail-closed override" not in final_text
        assert messages[-1]["role"] == "user"  # the tool_result ack was appended


class TestFailClosedEnforcement:
    def test_unknown_risk_overrides_dispense_to_review(self):
        """The core M1 invariant: code overrides the model, the model doesn't self-correct."""
        responses = [
            _resp("tool_use", [_tool_use("assess_refill_risk", {"patient_id": "patient-1"})]),
            _resp("tool_use", [_tool_use(
                "submit_decision",
                {"decision": "DISPENSE", "patient_id": "patient-1", "rationale": "Looks fine."},
            )]),
        ]
        client = _FakeClient(responses)
        with patch("agent.agent.execute_tool", _fake_execute_tool(risk_level="UNKNOWN")):
            final_text, _ = run_query(client, "check refill risk", verbose=False)

        assert "REVIEW" in final_text
        assert "Fail-closed override" in final_text
        assert "UNKNOWN" in final_text

    def test_override_holds_regardless_of_tool_call_order_in_the_same_batch(self):
        """
        Adversarial ordering: a weak/uncooperative model could emit both tool calls in
        one batch with submit_decision listed first. The override must not depend on it.
        """
        responses = [
            _resp("tool_use", [
                _tool_use("submit_decision", {
                    "decision": "DISPENSE", "patient_id": "patient-1", "rationale": "ok",
                }, id_="t_decision"),
                _tool_use("assess_refill_risk", {"patient_id": "patient-1"}, id_="t_risk"),
            ]),
        ]
        client = _FakeClient(responses)
        with patch("agent.agent.execute_tool", _fake_execute_tool(risk_level="UNKNOWN")):
            final_text, _ = run_query(client, "check refill risk", verbose=False)

        assert "REVIEW" in final_text
        assert "Fail-closed override" in final_text

    def test_no_decision_tool_call_fails_closed_to_review(self):
        """A model that answers in free text instead of calling submit_decision."""
        responses = [
            _resp("end_turn", [_text("The patient looks fine, dispense away!")]),
        ]
        client = _FakeClient(responses)
        final_text, _ = run_query(client, "check refill risk", verbose=False)

        assert "REVIEW" in final_text
        assert "no decision was submitted" in final_text
        assert "dispense away" in final_text.lower()  # narrative preserved as context, not discarded

    def test_review_from_the_model_needs_no_override(self):
        responses = [
            _resp("tool_use", [_tool_use("assess_refill_risk", {"patient_id": "patient-1"})]),
            _resp("tool_use", [_tool_use(
                "submit_decision",
                {"decision": "REVIEW", "patient_id": "patient-1", "rationale": "Ambiguous."},
            )]),
        ]
        client = _FakeClient(responses)
        with patch("agent.agent.execute_tool", _fake_execute_tool(risk_level="UNKNOWN")):
            final_text, _ = run_query(client, "check refill risk", verbose=False)

        assert "REVIEW" in final_text
        assert "Fail-closed override" not in final_text


# ─────────────────────────────────────────────────────────────────────────────
# 2. Adversarial cases -- malformed/off-contract shapes a weak model produces
# ─────────────────────────────────────────────────────────────────────────────

class TestWeakModelAdversarialInputs:
    """
    Simulating shapes a genuinely weak/local model actually produces -- the
    standing local-LLM testing rule (docs/phase6/decisions.md H11) applies
    from M1 onward, not only once the formal provider seam (M5) exists.
    """

    @pytest.mark.parametrize(
        "bad_decision",
        [
            "maybe dispense idk",
            '{"decision": "DISPENSE"}',
            "Dispense the medication to the patient",
            "",
            None,
        ],
    )
    def test_off_contract_decision_value_fails_closed(self, bad_decision):
        responses = [
            _resp("tool_use", [_tool_use("assess_refill_risk", {"patient_id": "patient-1"})]),
            _resp("tool_use", [_tool_use(
                "submit_decision",
                {"decision": bad_decision, "patient_id": "patient-1", "rationale": "..."},
            )]),
        ]
        client = _FakeClient(responses)
        with patch("agent.agent.execute_tool", _fake_execute_tool(risk_level="LOW")):
            final_text, _ = run_query(client, "check refill risk", verbose=False)

        assert "REVIEW" in final_text


# ─────────────────────────────────────────────────────────────────────────────
# 3. Live local model -- self-skips when Ollama isn't reachable
# ─────────────────────────────────────────────────────────────────────────────

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
# Default matches the lightest tag the setup instructions actually pull
# (`ollama pull llama3.2:1b`) -- the bare "llama3.2" tag resolves to a
# different (unpulled) model and 404s if this default drifts from it.
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:1b")


def _ollama_reachable() -> bool:
    try:
        import httpx
        httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=2.0)
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not _ollama_reachable(),
    reason=f"Ollama not reachable at {OLLAMA_HOST} -- skipping live local-LLM adversarial "
           f"test (docs/phase6/decisions.md H11). Set OLLAMA_HOST to point at a running "
           f"instance to exercise this.",
)
class TestLiveLocalModelAdversarial:
    """
    A genuinely weak/local model, not simulated -- the harshest realistic
    adversary for the enum gate (docs/phase6/design.md Section 5). Talks to
    Ollama directly (not through the Anthropic-shaped agent loop -- that
    translation layer is M5's job); this pins that the *gate itself*
    degrades safely no matter what a real weak model actually says.
    """

    def test_live_local_model_output_is_handled_safely(self):
        import httpx

        resp = httpx.post(
            f"{OLLAMA_HOST}/v1/chat/completions",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": "Respond with exactly one word: DISPENSE, "
                                   "DO_NOT_DISPENSE, or REVIEW.",
                    },
                    {
                        "role": "user",
                        "content": "A patient's drug-allergy risk check could not be "
                                   "completed. What should happen?",
                    },
                ],
                "max_tokens": 20,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]

        # Whatever the weak model actually said, the gate must resolve to exactly
        # one of the three enum values -- never crash, never pass through raw text.
        decision, _reason = validate_decision(raw, saw_unknown_risk=False)
        assert decision in AgentDecision
