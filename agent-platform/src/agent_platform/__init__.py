"""
agent-platform — shared hardening layer for this repo's LLM agents.

Built once, piloted on mcp-agent, carried to claims-agent later
(docs/phase6/decisions.md H2). No clinical logic lives here — this
package enforces output *contracts* and *fail-closed data handling*;
it never decides anything clinical or financial itself.
"""

from __future__ import annotations

from .fail_closed import RISK_UNKNOWN, is_unknown, safe_risk_level
from .output_gate import AgentDecision, validate_decision

__all__ = [
    "RISK_UNKNOWN",
    "is_unknown",
    "safe_risk_level",
    "AgentDecision",
    "validate_decision",
]
