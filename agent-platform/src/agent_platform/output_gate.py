"""
Output-side enum gate for this repo's LLM agents.

Constrains an agent's final decision to a small, explicit set of
values, validated in code -- never trusted from tool-schema adherence
alone (a live model can stringify or mangle a structured value; see
the llm-tool-schema-oneof-unreliable finding) -- and enforces REVIEW
as the fail-closed sink whenever the model's proposed decision
conflicts with a risk check that did not complete. This is this
repo's existing fail-closed thesis applied to agent *output*, not
just deterministic-service *decisions*. See docs/phase6/design.md
Section 4.1 and docs/phase6/decisions.md H5, H10, H21.
"""

from __future__ import annotations

from enum import Enum


class AgentDecision(str, Enum):
    """The only values a refill-triage agent turn may resolve to."""

    DISPENSE = "DISPENSE"
    DO_NOT_DISPENSE = "DO_NOT_DISPENSE"
    REVIEW = "REVIEW"


def validate_decision(
    raw_decision: object,
    *,
    saw_unknown_risk: bool,
) -> tuple[AgentDecision, str | None]:
    """
    Validate a model-proposed decision against the enum contract.

    Returns (decision, override_reason). override_reason is None when
    the model's own value is accepted unchanged; otherwise it names
    why code forced REVIEW instead of trusting the model's output.

    Fails closed to REVIEW when:
      - no decision was submitted at all (raw_decision is None -- e.g.
        the model answered in free text instead of calling the
        decision tool);
      - the value doesn't match one of the enum members (schema
        drift, a weak model stringifying/mangling the value, an
        unexpected type, etc.); or
      - a risk check during this turn returned UNKNOWN and the model
        tried to submit anything other than REVIEW anyway
        (saw_unknown_risk=True) -- a broken or unclear safety check is
        never narrated as "dispense" or "do not dispense", regardless
        of what the model concluded from the rest of the context.
    """
    if raw_decision is None:
        return AgentDecision.REVIEW, "no decision was submitted"

    try:
        decision = AgentDecision(str(raw_decision).strip().upper())
    except (AttributeError, ValueError):
        return (
            AgentDecision.REVIEW,
            f"{raw_decision!r} is not a recognized decision value",
        )

    if saw_unknown_risk and decision is not AgentDecision.REVIEW:
        return (
            AgentDecision.REVIEW,
            "a risk check during this turn could not be completed (UNKNOWN); "
            f"'{decision.value}' was overridden -- an incomplete safety check "
            "is never narrated as safe",
        )

    return decision, None
