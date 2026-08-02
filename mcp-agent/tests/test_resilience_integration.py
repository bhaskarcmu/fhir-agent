"""
Chaos-style integration tests for M4's circuit breaker and rate/cost
limiter as seen through run_query (docs/phase6/milestone-plan.md M4):
simulated LLM API timeouts/5xx/rate-limit responses, confirming the
breaker trips and the call is short-circuited, and that both failure
modes fail closed to REVIEW (docs/phase6/decisions.md H18-H20) rather
than a raw crash. Unit-level breaker/limiter behavior lives in
agent-platform/tests/test_resilience.py; this file is specifically about
run_query's own integration of them.

Run:
  python3 -m pytest mcp-agent/tests/test_resilience_integration.py -v
"""

from __future__ import annotations

from types import SimpleNamespace

import anthropic
import httpx
import pytest

from agent.agent import run_query
from agent_platform import get_circuit_breaker, get_rate_limiter, reset_resilience_state
from agent_platform.resilience import LLM_CALLS_TOTAL

_REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


@pytest.fixture(autouse=True)
def _reset():
    reset_resilience_state()
    yield
    reset_resilience_state()


class _FailingClient:
    """A client whose messages.create always raises the given exception."""

    def __init__(self, exc: Exception):
        self._exc = exc
        self.call_count = 0

    class _Messages:
        def __init__(self, outer):
            self._outer = outer

        def create(self, **kwargs):
            self._outer.call_count += 1
            raise self._outer._exc

    @property
    def messages(self):
        return self._Messages(self)


def _resp(stop_reason: str, content: list, usage=None) -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=content,
        usage=usage or SimpleNamespace(input_tokens=100, output_tokens=20),
    )


class _SucceedingClient:
    def __init__(self, response):
        self._response = response
        self.call_count = 0

    class _Messages:
        def __init__(self, outer):
            self._outer = outer

        def create(self, **kwargs):
            self._outer.call_count += 1
            return self._outer._response

    @property
    def messages(self):
        return self._Messages(self)


@pytest.mark.parametrize(
    "exc",
    [
        anthropic.APITimeoutError(request=_REQUEST),
        anthropic.APIConnectionError(request=_REQUEST),
        anthropic.RateLimitError(
            "rate limited", response=httpx.Response(429, request=_REQUEST), body=None
        ),
        anthropic.InternalServerError(
            "server error", response=httpx.Response(500, request=_REQUEST), body=None
        ),
    ],
)
def test_individual_api_failures_still_propagate_below_the_breaker_threshold(exc):
    """
    A single transient failure (timeout, connection error, 429, 5xx) is
    not swallowed -- it still propagates out of run_query exactly as it
    did before M4, as long as the breaker hasn't tripped yet. M4 only
    changes what happens once the breaker actually opens (see below).
    """
    client = _FailingClient(exc)
    with pytest.raises(type(exc)):
        run_query(client, "check refill risk", verbose=False)
    assert client.call_count == 1


def test_repeated_failures_trip_the_breaker_and_the_next_call_fails_closed_to_review():
    breaker = get_circuit_breaker()
    breaker.failure_threshold = 3

    client = _FailingClient(anthropic.APITimeoutError(request=_REQUEST))

    for _ in range(3):
        with pytest.raises(anthropic.APITimeoutError):
            run_query(client, "check refill risk", verbose=False)
    assert breaker.state == "open"
    assert client.call_count == 3

    # The breaker is open now -- run_query must not raise or crash. It
    # fails closed to REVIEW instead, and the API is not called again.
    final_text, messages = run_query(client, "check refill risk", verbose=False)

    assert client.call_count == 3  # short-circuited -- no new attempt
    assert "REVIEW" in final_text
    assert isinstance(messages, list)


def test_hard_cost_backstop_fails_closed_to_review_without_calling_the_api():
    limiter = get_rate_limiter()
    limiter.hard_backstop_tokens_per_minute = 1_000
    limiter.record(999)  # one token under the backstop already

    client = _SucceedingClient(_resp("end_turn", [SimpleNamespace(type="text", text="hi")]))

    final_text, _messages = run_query(
        client, "check refill risk", verbose=False, token_count=500
    )

    assert client.call_count == 0  # never attempted -- blocked pre-call
    assert "REVIEW" in final_text


def test_a_successful_call_after_a_trip_closes_the_circuit_again():
    breaker = get_circuit_breaker()
    breaker.failure_threshold = 1
    breaker.reset_timeout_seconds = 0.0  # trial call allowed immediately

    client = _FailingClient(anthropic.APITimeoutError(request=_REQUEST))
    with pytest.raises(anthropic.APITimeoutError):
        run_query(client, "check refill risk", verbose=False)
    assert breaker.state == "open"

    success_response = _resp(
        "tool_use",
        [SimpleNamespace(type="tool_use", name="submit_decision", input={
            "decision": "REVIEW", "patient_id": "p1", "rationale": "ok",
        }, id="t1")],
    )
    ok_client = _SucceedingClient(success_response)
    final_text, _messages = run_query(ok_client, "check refill risk", verbose=False)
    assert breaker.state == "closed"
    assert "REVIEW" in final_text


def test_llm_calls_total_metric_increments_on_success():
    before = LLM_CALLS_TOTAL.labels(outcome="success")._value.get()

    client = _SucceedingClient(_resp(
        "tool_use",
        [SimpleNamespace(type="tool_use", name="submit_decision", input={
            "decision": "REVIEW", "patient_id": "p1", "rationale": "ok",
        }, id="t1")],
    ))
    run_query(client, "check refill risk", verbose=False)

    after = LLM_CALLS_TOTAL.labels(outcome="success")._value.get()
    assert after == before + 1
