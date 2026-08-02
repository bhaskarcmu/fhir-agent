"""
Fail-closed risk-code handling, shared across this repo's LLM agents.

Mirrors the one real fail-closed precedent in this codebase --
claims-service's HttpTriageClient.java: every path that does not
produce a risk level the caller understands (service unavailable,
transport error, unrecognized response) maps to UNKNOWN, never to a
value that could be read as "safe". See docs/phase6/design.md Section
4.1 and docs/phase6/decisions.md H18.
"""

from __future__ import annotations

RISK_UNKNOWN = "UNKNOWN"

_RECOGNIZED_RISK_LEVELS = frozenset({"HIGH", "MODERATE", "LOW"})


def safe_risk_level(raw_code: str | None) -> str:
    """
    Coerce a risk code from a triage response to a recognized value or
    the UNKNOWN sentinel.

    A missing, empty, or unrecognized code is treated exactly like an
    unreachable service: UNKNOWN, never assumed to be "LOW". Narrating
    a recommendation as safe because a safety check returned something
    the caller doesn't understand is the fail-open hazard this
    function exists to close off. Case-insensitive, mirroring the
    Java precedent's own normalization.
    """
    if not raw_code:
        return RISK_UNKNOWN
    normalized = raw_code.strip().upper()
    if normalized in _RECOGNIZED_RISK_LEVELS:
        return normalized
    return RISK_UNKNOWN


def is_unknown(risk_level: str | None) -> bool:
    """True if a risk level is the fail-closed sentinel (or falsy/missing)."""
    return not risk_level or risk_level == RISK_UNKNOWN
