"""
Unit tests for agent_platform.resilience (docs/phase6/decisions.md H19,
H20, milestone-plan.md M4): the circuit breaker and rate/cost limiter in
isolation, without touching the real Anthropic SDK or a running agent.
See mcp-agent/tests/test_resilience_integration.py for the chaos-style
tests that exercise these through run_query.

Run:
  python3 -m pytest agent-platform/tests/test_resilience.py -v
"""

from __future__ import annotations

import time

import anthropic
import httpx
import pytest

from agent_platform.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    CostLimitExceededError,
    RateCostLimiter,
    call_with_resilience,
    get_circuit_breaker,
    get_rate_limiter,
    reset_resilience_state,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_resilience_state()
    yield
    reset_resilience_state()


# ── CircuitBreaker ──────────────────────────────────────────────────────

def test_circuit_stays_closed_below_the_failure_threshold():
    breaker = CircuitBreaker(failure_threshold=3, reset_timeout_seconds=30)
    breaker.on_failure()
    breaker.on_failure()
    assert breaker.state == "closed"
    breaker.before_call()  # does not raise


def test_circuit_opens_at_the_failure_threshold():
    breaker = CircuitBreaker(failure_threshold=3, reset_timeout_seconds=30)
    breaker.on_failure()
    breaker.on_failure()
    breaker.on_failure()
    assert breaker.state == "open"
    with pytest.raises(CircuitOpenError):
        breaker.before_call()


def test_a_success_resets_the_consecutive_failure_count():
    breaker = CircuitBreaker(failure_threshold=3, reset_timeout_seconds=30)
    breaker.on_failure()
    breaker.on_failure()
    breaker.on_success()
    breaker.on_failure()
    breaker.on_failure()
    # Two failures again after the reset -- still below threshold of 3.
    assert breaker.state == "closed"
    breaker.before_call()


def test_circuit_allows_a_trial_call_after_the_reset_timeout_elapses():
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout_seconds=0.05)
    breaker.on_failure()
    assert breaker.state == "open"
    with pytest.raises(CircuitOpenError):
        breaker.before_call()

    time.sleep(0.06)
    breaker.before_call()  # does not raise -- half-open trial allowed
    assert breaker.state == "half_open"


def test_call_with_resilience_trips_the_breaker_after_repeated_failures():
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")

    def _fail():
        raise anthropic.APIConnectionError(request=request)

    breaker = get_circuit_breaker()
    breaker.failure_threshold = 3

    for _ in range(3):
        with pytest.raises(anthropic.APIConnectionError):
            call_with_resilience(_fail, estimated_tokens=100)

    assert breaker.state == "open"
    # The breaker is open now -- the next call is short-circuited before
    # fn() is ever invoked, not another APIConnectionError.
    with pytest.raises(CircuitOpenError):
        call_with_resilience(_fail, estimated_tokens=100)


def test_call_with_resilience_does_not_trip_the_breaker_on_a_non_api_exception():
    """
    The breaker protects against the external LLM dependency, not against
    bugs in our own code -- a plain exception from fn() (not an
    anthropic.APIError) propagates unchanged and is not counted as a
    breaker failure.
    """
    def _fail():
        raise ValueError("a bug, not an API failure")

    breaker = get_circuit_breaker()
    breaker.failure_threshold = 1

    with pytest.raises(ValueError):
        call_with_resilience(_fail, estimated_tokens=100)

    assert breaker.state == "closed"


def test_call_with_resilience_returns_the_result_on_success():
    result = call_with_resilience(lambda: "ok", estimated_tokens=100)
    assert result == "ok"
    assert get_circuit_breaker().state == "closed"


# ── RateCostLimiter ──────────────────────────────────────────────────────

def test_limiter_allows_calls_under_the_alert_threshold():
    limiter = RateCostLimiter(alert_tokens_per_minute=1_000, hard_backstop_tokens_per_minute=10_000)
    assert limiter.before_call(500) is False


def test_limiter_flags_alert_without_blocking():
    limiter = RateCostLimiter(alert_tokens_per_minute=1_000, hard_backstop_tokens_per_minute=10_000)
    limiter.record(900)
    assert limiter.before_call(200) is True  # alert-only: still allowed through


def test_limiter_blocks_once_the_hard_backstop_is_exceeded():
    limiter = RateCostLimiter(alert_tokens_per_minute=1_000, hard_backstop_tokens_per_minute=2_000)
    limiter.record(1_900)
    with pytest.raises(CostLimitExceededError):
        limiter.before_call(200)


def test_limiter_window_prunes_old_events():
    limiter = RateCostLimiter(
        alert_tokens_per_minute=1_000, hard_backstop_tokens_per_minute=2_000, window_seconds=0.05
    )
    limiter.record(1_900)
    time.sleep(0.06)
    # The old event has aged out of the window -- a call that would have
    # been blocked a moment ago is fine now.
    assert limiter.before_call(200) is False


def test_get_rate_limiter_singleton_is_stable_across_calls():
    a = get_rate_limiter()
    b = get_rate_limiter()
    assert a is b
