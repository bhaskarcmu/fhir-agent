"""
Unit tests for agent_platform.policy (docs/phase6/decisions.md H6): the
file-loading mechanism only -- the actual policy content lives in
mcp-agent/policy.md and is deployment-specific, not tested here.

Run:
  python3 -m pytest agent-platform/tests/test_policy.py -v
"""

from __future__ import annotations

import pytest

from agent_platform.policy import load_policy


def test_load_policy_returns_file_contents(tmp_path):
    policy_file = tmp_path / "policy.md"
    policy_file.write_text("Rule one.\nRule two.\n")

    assert load_policy(policy_file) == "Rule one.\nRule two."


def test_load_policy_accepts_a_string_path(tmp_path):
    policy_file = tmp_path / "policy.md"
    policy_file.write_text("Some policy text.")

    assert load_policy(str(policy_file)) == "Some policy text."


def test_load_policy_raises_clearly_when_missing(tmp_path):
    missing = tmp_path / "does-not-exist.md"
    with pytest.raises(FileNotFoundError, match="Policy file not found"):
        load_policy(missing)
