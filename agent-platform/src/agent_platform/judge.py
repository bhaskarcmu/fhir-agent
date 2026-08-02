"""
LLM-as-judge for soft-quality checks on the agent's own final response
(docs/phase6/design.md Section 4.6, decisions.md H11, superseding H7).

Runs on every response, not a filtered "important" subset -- the cost
and latency of that are explicitly accepted (H11). Checks soft
qualities only (groundedness, tone, unnecessary PHI in the rationale
text) and structurally CANNOT override the decision M1's gate already
enforced: judge_response() is called strictly after a decision is
already final, its result is never fed back into validate_decision(),
and there is no code path from a judge verdict to a changed decision.

Deliberately does NOT go through agent_platform.resilience's shared
circuit breaker / rate limiter: those exist to protect the safety-
critical clinical call, and a string of judge failures must never trip
the same breaker and start blocking real clinical queries. The judge's
own reliability is fully decoupled -- it has its own narrow try/except
and fails closed to "inconclusive" on literally anything going wrong
(unreachable model, malformed response, timeout, a weak model answering
in free text instead of calling the tool). A broken judge must never
take the actual clinical response down with it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .observability import get_tracer, layer_attrs, safe_set_attributes, start_span

_tracer = get_tracer("agent_platform.judge")

JUDGE_TOOL_DEFINITION = {
    "name": "submit_judgment",
    "description": (
        "Submit your evaluation of the clinical assistant's response. Call this "
        "exactly once with your assessment -- do not answer in free text."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "groundedness_ok": {
                "type": "boolean",
                "description": "True if the rationale is specific and consistent with what a "
                                "real risk assessment would produce -- not generic, invented, "
                                "or self-contradictory.",
            },
            "tone_ok": {
                "type": "boolean",
                "description": "True if the tone is professional and appropriately direct -- "
                                "not alarmist, casual, or hedging on a real risk.",
            },
            "phi_leak_detected": {
                "type": "boolean",
                "description": "True if the rationale includes patient demographic detail "
                                "(name, DOB, address) beyond what answering the question requires.",
            },
            "notes": {
                "type": "string",
                "description": "One brief sentence explaining any 'false' value above. Empty if all true.",
            },
        },
        "required": ["groundedness_ok", "tone_ok", "phi_leak_detected", "notes"],
    },
}

JUDGE_SYSTEM_PROMPT = (
    "You are a quality reviewer for a clinical decision-support assistant's response. "
    "You have no authority to change any clinical decision -- you are only checking soft "
    "qualities of how the response was communicated. Call submit_judgment exactly once."
)


@dataclass
class JudgeResult:
    """available=False means the judge itself was inconclusive -- not that anything failed
    the checks. Never treat available=False as a quality problem with the judged response."""

    available: bool
    groundedness_ok: bool | None = None
    tone_ok: bool | None = None
    phi_leak_detected: bool | None = None
    notes: str = ""


def _block_get(block, key, default=None):
    if isinstance(block, dict):
        return block.get(key, default)
    return getattr(block, key, default)


def judge_response(client, model: str, *, query: str, rationale: str) -> JudgeResult:
    """
    Evaluate one final rationale for soft-quality issues. Best-effort and
    non-blocking by design -- see module docstring for why this
    deliberately bypasses the shared resilience layer.
    """
    with start_span("agent.judge", _tracer, layer_attrs("agent.judge", "judge_response")) as span:
        try:
            response = client.messages.create(
                model=model,
                max_tokens=256,
                system=JUDGE_SYSTEM_PROMPT,
                tools=[JUDGE_TOOL_DEFINITION],
                messages=[{
                    "role": "user",
                    "content": f"Clinician's query: {query}\n\nAssistant's rationale: {rationale}",
                }],
            )
        except Exception:
            safe_set_attributes(span, {"judge.available": False})
            return JudgeResult(available=False)

        for block in getattr(response, "content", None) or []:
            if _block_get(block, "type") != "tool_use":
                continue
            inputs = _block_get(block, "input") or {}
            try:
                result = JudgeResult(
                    available=True,
                    groundedness_ok=bool(inputs["groundedness_ok"]),
                    tone_ok=bool(inputs["tone_ok"]),
                    phi_leak_detected=bool(inputs["phi_leak_detected"]),
                    notes=str(inputs.get("notes", "")),
                )
            except (KeyError, TypeError):
                safe_set_attributes(span, {"judge.available": False})
                return JudgeResult(available=False)
            safe_set_attributes(span, {
                "judge.available": True,
                "judge.groundedness_ok": result.groundedness_ok,
                "judge.tone_ok": result.tone_ok,
                "judge.phi_leak_detected": result.phi_leak_detected,
            })
            return result

        # A weak model answered in free text instead of calling the tool --
        # inconclusive, not a failure of the response being judged.
        safe_set_attributes(span, {"judge.available": False})
        return JudgeResult(available=False)
