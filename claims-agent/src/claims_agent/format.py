"""Terminal formatting for the claims explanation agent."""
from __future__ import annotations

OUTCOME_ICONS = {
    "APPROVED": "✅",
    "DENIED": "🛑",
    "PENDED": "⏸️",
    "ROUTED_FOR_REVIEW": "🔎",
}
OUTCOME_LABELS = {
    "APPROVED": "APPROVED",
    "DENIED": "DENIED",
    "PENDED": "PENDED — prior authorization / info needed",
    "ROUTED_FOR_REVIEW": "ROUTED FOR MANUAL REVIEW",
}
DIVIDER = "─" * 68


def header(outcome: str, decision_id: str) -> str:
    icon = OUTCOME_ICONS.get(outcome, "•")
    label = OUTCOME_LABELS.get(outcome, outcome)
    return f"{icon} {label}\n   Decision: {decision_id}"


def error_block(message: str) -> str:
    return f"⚠️  {message}"
