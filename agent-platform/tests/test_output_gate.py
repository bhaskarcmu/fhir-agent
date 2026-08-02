"""
Tests for agent_platform.output_gate — the enum-output fail-closed gate.

Includes adversarial cases shaped like what a weak/local model actually
produces (stringified structures, wrong casing, extra prose, wrong type),
per the standing local-LLM testing rule (docs/phase6/decisions.md H11).
"""

from __future__ import annotations

import pytest

from agent_platform.output_gate import AgentDecision, validate_decision


@pytest.mark.parametrize(
    "raw",
    ["DISPENSE", "DO_NOT_DISPENSE", "REVIEW"],
)
def test_valid_decisions_pass_through_when_risk_is_known(raw):
    decision, reason = validate_decision(raw, saw_unknown_risk=False)
    assert decision is AgentDecision(raw)
    assert reason is None


def test_lowercase_decision_is_normalized():
    decision, reason = validate_decision("dispense", saw_unknown_risk=False)
    assert decision is AgentDecision.DISPENSE
    assert reason is None


def test_no_decision_submitted_fails_closed_to_review():
    decision, reason = validate_decision(None, saw_unknown_risk=False)
    assert decision is AgentDecision.REVIEW
    assert "no decision was submitted" in reason


@pytest.mark.parametrize(
    "raw",
    [
        "MAYBE_DISPENSE",           # not a contract value
        "dispense the medication",  # a weak model padding the value with prose
        '{"decision": "DISPENSE"}', # a weak model stringifying structured output
        "",
        "   ",
        123,                        # wrong type entirely
        ["DISPENSE"],               # wrong type entirely
    ],
)
def test_off_contract_values_fail_closed_to_review(raw):
    """
    Adversarial shapes a genuinely weak model can produce -- this is exactly
    the class of input Claude reliably avoids but a local/small model does
    not, which is why this suite doesn't only test the happy path.
    """
    decision, reason = validate_decision(raw, saw_unknown_risk=False)
    assert decision is AgentDecision.REVIEW
    assert reason is not None


@pytest.mark.parametrize("raw", ["DISPENSE", "DO_NOT_DISPENSE"])
def test_unknown_risk_forces_review_even_if_model_disagrees(raw):
    """
    The core hard invariant: a risk check that could not be completed is
    never narrated as safe, regardless of what the model itself concluded.
    """
    decision, reason = validate_decision(raw, saw_unknown_risk=True)
    assert decision is AgentDecision.REVIEW
    assert "UNKNOWN" in reason
    assert raw in reason


def test_review_is_accepted_unchanged_even_with_unknown_risk():
    """The model choosing REVIEW itself when risk is UNKNOWN needs no override."""
    decision, reason = validate_decision("REVIEW", saw_unknown_risk=True)
    assert decision is AgentDecision.REVIEW
    assert reason is None
