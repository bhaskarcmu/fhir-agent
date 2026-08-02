"""Tests for agent_platform.fail_closed — the risk-code fail-closed sentinel."""

from __future__ import annotations

import pytest

from agent_platform.fail_closed import RISK_UNKNOWN, is_unknown, safe_risk_level


@pytest.mark.parametrize("raw", ["HIGH", "MODERATE", "LOW"])
def test_recognized_codes_pass_through_unchanged(raw):
    assert safe_risk_level(raw) == raw


@pytest.mark.parametrize("raw", ["high", "Moderate", "low"])
def test_recognized_codes_are_case_insensitive(raw):
    assert safe_risk_level(raw) == raw.upper()


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "SEVERE",           # a code the caller doesn't recognize -- must not pass through raw
        "high risk",        # malformed/extra text
        "  ",               # whitespace only
        "unknown",
        "null",
    ],
)
def test_unrecognized_or_missing_codes_fail_closed_to_unknown(raw):
    """
    The core hazard this function exists to close: an unrecognized code must
    never be treated as though it were a valid, safe risk level.
    """
    assert safe_risk_level(raw) == RISK_UNKNOWN


def test_is_unknown_true_for_sentinel_and_falsy():
    assert is_unknown(RISK_UNKNOWN) is True
    assert is_unknown(None) is True
    assert is_unknown("") is True


def test_is_unknown_false_for_recognized_levels():
    assert is_unknown("HIGH") is False
    assert is_unknown("LOW") is False
