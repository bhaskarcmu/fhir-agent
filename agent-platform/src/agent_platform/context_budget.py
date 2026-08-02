"""
Token-budget policy for the agent's message history (docs/phase6/design.md
Section 4.3, decisions.md H13). Replaces M1's MAX_REPL_TURNS stopgap (a
turn-count cap, not a token-based one) with a real number.

TOKEN_BUDGET is grounded in real, live-measured usage, not guessed: two
complete refill-risk queries (get_patient_summary -> assess_refill_risk ->
submit_decision -- the platform's actual reference workflow, run against
the live stack) cost 5,404 and 5,381 tokens end to end respectively,
measured from real gen_ai.usage.* span attributes via Jaeger
(docs/phase6/telemetry-schema.md). TOKEN_BUDGET below is set to roughly
7-8x that single-query cost -- enough room for a genuine multi-turn
clinical conversation before compaction, while staying a small,
deliberately cost-conscious fraction of the model's real context window
(not a technical necessity; ties to Phase 6 M4's cost-control mandate,
same as the LLM-usage-metrics deferral in telemetry-schema.md Section 7).
"""

from __future__ import annotations

TOKEN_BUDGET = 40_000


def _turn_boundaries(messages: list[dict]) -> list[int]:
    """
    Indices where a new user-initiated turn starts. Only the literal human
    query has plain string content ({"role": "user", "content": "..."});
    tool-result round-trips within the same turn are also "user" role but
    carry list content, so they don't count as a new turn boundary.
    """
    return [
        i for i, m in enumerate(messages)
        if m.get("role") == "user" and isinstance(m.get("content"), str)
    ]


def compact(messages: list[dict], token_count: int, budget: int = TOKEN_BUDGET) -> tuple[list[dict], bool]:
    """
    Drop the single oldest complete turn if token_count exceeds budget.
    Returns (possibly-truncated messages, whether anything was dropped).

    Deliberately drops one turn per call, not a loop down to some target:
    there is no live per-turn token count, only the running session total
    from the most recent real API response (see agent.py's run_query) --
    so this is a self-correcting policy, not a one-shot precise one. The
    caller re-checks the real, newly-measured token_count on the next
    response and compacts again if still over budget.
    """
    if token_count <= budget:
        return messages, False

    boundaries = _turn_boundaries(messages)
    if len(boundaries) <= 1:
        # Only the current (or no) turn remains -- nothing safe to drop
        # without discarding the conversation the caller is actively having.
        return messages, False

    return messages[boundaries[1]:], True
