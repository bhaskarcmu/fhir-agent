"""
Deterministic, non-authoritative explanation of an adjudication decision.

This renders the *already-made* decision (from claims-service) into plain language in the
style of PRD §9.4. It never changes the outcome — it only narrates it. It is used directly
when no LLM key is available, and as the grounding the LLM elaborates when one is.
"""
from __future__ import annotations

_LEAD = {
    "APPROVED": "Claim approved.",
    "DENIED": "Claim denied.",
    "PENDED": "Claim pended.",
    "ROUTED_FOR_REVIEW": "Claim routed for manual review.",
}


def render_explanation(decision: dict) -> str:
    """Return a plain-language explanation of a decision dict (§9.4 style)."""
    outcome = decision.get("outcome", "UNKNOWN")
    reasons = decision.get("reasons") or []
    all_findings = decision.get("allFindings") or []
    pricing = decision.get("pricing")

    parts: list[str] = [_LEAD.get(outcome, f"Claim {outcome}.")]

    if reasons:
        msgs = [r.get("message", r.get("code", "")) for r in reasons]
        parts.append("Reason(s): " + _join(msgs))

    # Secondary findings that didn't determine the outcome but add context (multi-reason).
    reason_codes = {r.get("code") for r in reasons}
    extra = [f.get("message", "") for f in all_findings if f.get("code") not in reason_codes]
    if extra:
        parts.append("Also noted: " + _join(extra))

    if outcome == "PENDED":
        parts.append("The claim is held pending prior authorization or additional information.")
    elif outcome == "ROUTED_FOR_REVIEW":
        parts.append("A manual review task has been created.")

    if pricing and pricing.get("paid"):
        parts.append(
            "Pricing: total ${:.2f}, patient pays ${:.2f}, plan pays ${:.2f} (auth {}).".format(
                float(pricing.get("totalAmount", 0)),
                float(pricing.get("patientPay", 0)),
                float(pricing.get("planPay", 0)),
                pricing.get("authNumber", "n/a"),
            )
        )

    parts.append(f"Decision id: {decision.get('decisionId', 'n/a')}.")
    return " ".join(parts)


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    if not items:
        return "(none)"
    if len(items) == 1:
        return items[0]
    return "; ".join(items[:-1]) + "; and " + items[-1]
