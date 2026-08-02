"""
agent-platform — shared hardening layer for this repo's LLM agents.

Built once, piloted on mcp-agent, carried to claims-agent later
(docs/phase6/decisions.md H2). No clinical logic lives here — this
package enforces output *contracts* and *fail-closed data handling*;
it never decides anything clinical or financial itself.
"""

from __future__ import annotations

from .context_budget import TOKEN_BUDGET, compact
from .fail_closed import RISK_UNKNOWN, is_unknown, safe_risk_level
from .observability import (
    current_trace_id,
    get_tracer,
    is_detailed,
    layer_attrs,
    safe_set_attributes,
    setup_tracing,
    start_span,
    verbosity,
)
from .output_gate import AgentDecision, validate_decision
from .session_store import create_session, load_session, save_session

__all__ = [
    "RISK_UNKNOWN",
    "is_unknown",
    "safe_risk_level",
    "AgentDecision",
    "validate_decision",
    "setup_tracing",
    "get_tracer",
    "safe_set_attributes",
    "start_span",
    "verbosity",
    "is_detailed",
    "layer_attrs",
    "current_trace_id",
    "TOKEN_BUDGET",
    "compact",
    "create_session",
    "load_session",
    "save_session",
]
