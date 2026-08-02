"""
Tests for agent_platform.context_budget -- the token-budget compaction
policy (docs/phase6/decisions.md H13).
"""

from __future__ import annotations

from agent_platform.context_budget import TOKEN_BUDGET, compact, _turn_boundaries


def _user_turn(text: str) -> dict:
    return {"role": "user", "content": text}


def _tool_round_trip() -> dict:
    """A within-turn tool-result message -- also role=user, but list content."""
    return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "{}"}]}


def _assistant_turn() -> dict:
    return {"role": "assistant", "content": [{"type": "text", "text": "..."}]}


def test_under_budget_is_a_noop():
    messages = [_user_turn("hi"), _assistant_turn()]
    result, dropped = compact(messages, token_count=100, budget=TOKEN_BUDGET)
    assert result is messages
    assert dropped is False


def test_over_budget_drops_the_oldest_turn():
    messages = [
        _user_turn("first question"), _assistant_turn(),
        _user_turn("second question"), _tool_round_trip(), _assistant_turn(),
    ]
    result, dropped = compact(messages, token_count=TOKEN_BUDGET + 1, budget=TOKEN_BUDGET)
    assert dropped is True
    assert result == messages[2:]  # the first turn (2 messages) is gone
    assert result[0] == _user_turn("second question")


def test_tool_round_trips_within_a_turn_are_not_mistaken_for_a_turn_boundary():
    messages = [
        _user_turn("only question"), _tool_round_trip(), _tool_round_trip(), _assistant_turn(),
    ]
    boundaries = _turn_boundaries(messages)
    assert boundaries == [0]  # only the real user query counts, not the tool_result messages


def test_refuses_to_drop_the_only_remaining_turn():
    """Never discard the conversation the caller is actively having."""
    messages = [_user_turn("only question"), _tool_round_trip(), _assistant_turn()]
    result, dropped = compact(messages, token_count=TOKEN_BUDGET + 1, budget=TOKEN_BUDGET)
    assert dropped is False
    assert result == messages


def test_exactly_at_budget_is_not_over():
    messages = [_user_turn("hi"), _assistant_turn(), _user_turn("hi2"), _assistant_turn()]
    result, dropped = compact(messages, token_count=TOKEN_BUDGET, budget=TOKEN_BUDGET)
    assert dropped is False
    assert result is messages


def test_token_budget_default_is_a_reasonable_multiple_of_one_real_measured_query():
    """
    Guards the documented rationale: TOKEN_BUDGET was set from two real
    measured queries costing ~5,400 tokens each (see module docstring),
    not an arbitrary round number. This test just pins the constant so a
    future change to it is a deliberate, visible diff, not an accident.
    """
    assert TOKEN_BUDGET == 40_000
