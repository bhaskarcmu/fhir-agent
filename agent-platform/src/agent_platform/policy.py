"""
Policy loading for this repo's LLM agents (docs/phase6/design.md Section
4.6, decisions.md H6). Rules that always apply go straight into the
system prompt -- retrieval (RAG) is structurally the wrong mechanism for
something that's true on every single turn, no matter what the
conversation is about. RAG is reserved for the genuine knowledge base
(knowledge.py), which answers a different question ("what does the
label say about this specific drug") that a static prompt can't.

No clinical logic lives here -- this module only reads a text file. The
actual policy content is deployment-specific and lives with the agent
that owns it (mcp-agent/policy.md), not in this shared package.
"""

from __future__ import annotations

from pathlib import Path


def load_policy(path: str | Path) -> str:
    """
    Read a policy file's full text. Raises FileNotFoundError with a clear
    message if it's missing -- fail loud, since a silently-empty policy
    would mean the agent quietly runs with no policy constraints at all,
    which is worse than crashing at startup.
    """
    policy_path = Path(path)
    if not policy_path.is_file():
        raise FileNotFoundError(
            f"Policy file not found at {policy_path} -- an agent must not start "
            "with a silently-empty policy."
        )
    return policy_path.read_text().strip()
