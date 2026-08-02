"""
Deployment resilience for the one paid, external, metered call every agent
turn makes: the LLM API (docs/phase6/design.md Section 4.4, decisions.md
H19, H20). Two independent protections wrap that single call site:

- CircuitBreaker: availability. Trips after repeated consecutive failures
  so a real outage fails fast instead of retrying into it turn after turn.
- RateCostLimiter: spend. Hybrid posture (H19) -- alert-only for
  legitimate clinical traffic, a hard backstop reserved specifically for
  runaway/bug-driven spend that pure alert-only has no protection against.

Both fail closed via a dedicated exception, never a raw crash and never a
silent retry loop -- agent.py maps either one directly onto M1's REVIEW
sink (an LLM call that cannot be attempted is exactly as safety-relevant
as a risk check that came back UNKNOWN).

This is a deliberate, documented divergence from HttpTriageClient.java's
"no breaker" precedent for internal service-to-service calls: the LLM
API's external, metered, cost-bearing risk profile is materially
different from what that precedent was written for (H20).

State is process-local by design, same scope as session_store.py's
connection pool -- one mcp-agent CLI invocation or one mcp-agent-api
process. A tripped breaker shedding load in exactly the process that's
failing is the point; there is no cross-process coordination need here.
"""

from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Callable, TypeVar

from prometheus_client import Counter, Histogram

T = TypeVar("T")


class CircuitOpenError(RuntimeError):
    """The LLM API circuit breaker is open -- the call was not attempted."""


class CostLimitExceededError(RuntimeError):
    """The hard cost/rate backstop was exceeded -- the call was not attempted."""


# ── Metrics (docs/phase6/decisions.md H27, telemetry-schema.md Section 7) ──
# A real Prometheus counter/histogram, not just the per-span gen_ai.usage.*
# attributes M2 already has -- a span attribute can't answer "how many
# tokens today" or feed an alert threshold. Scraped from mcp-agent-api's
# /metrics the same way the Java services' /actuator/prometheus already is.

LLM_TOKENS_TOTAL = Counter(
    "fhir_agent_llm_tokens_total",
    "Total LLM tokens consumed by the refill-triage agent, by direction.",
    ["direction"],
)

LLM_CALLS_TOTAL = Counter(
    "fhir_agent_llm_calls_total",
    "Total LLM API call attempts, by outcome.",
    ["outcome"],  # success | failure | circuit_open | cost_blocked
)

LLM_CALL_DURATION_SECONDS = Histogram(
    "fhir_agent_llm_call_duration_seconds",
    "Duration of successful LLM API calls.",
)

RATE_LIMIT_ALERTS_TOTAL = Counter(
    "fhir_agent_rate_limit_alerts_total",
    "Times the alert-only rate/cost threshold was crossed (traffic still allowed through).",
)

# Exceptions the breaker treats as an LLM-API-availability failure. All of
# the SDK's actual API-side errors (timeout, connection, rate-limit, 5xx,
# 4xx) share this one base class -- deliberately broad: the breaker's job
# is "this dependency isn't answering usably right now", and a sustained
# run of 4xx (e.g. an auth/config break) is just as much an outage from the
# caller's perspective as a 5xx is. A bug in *our own* code (a plain
# TypeError, say) is not caught here and propagates as before -- the
# breaker protects against the external dependency, not against ourselves.
try:
    import anthropic

    BREAKER_TRIPPING_EXCEPTIONS: tuple[type[BaseException], ...] = (anthropic.APIError,)
except ImportError:  # pragma: no cover -- anthropic is a hard dependency of every caller
    BREAKER_TRIPPING_EXCEPTIONS = (Exception,)

# Grounded in the real per-query measurement this repo already has
# (docs/phase6/decisions.md H29: 5,404 / 5,381 input tokens for two live
# reference-workflow queries) -- used as the pre-call cost estimate when no
# better estimate (the caller's own last-known conversation size) is
# available yet.
ESTIMATED_TOKENS_PER_CALL = 5_400

# A single clinician issuing queries by hand cannot plausibly sustain more
# than a few queries a minute. ALERT_TOKENS_PER_MINUTE is set generously
# above realistic manual use (~10 queries/minute) so it only fires on
# genuinely unusual volume; HARD_BACKSTOP_TOKENS_PER_MINUTE is 10x that
# (~100 queries/minute) -- sized to catch a runaway loop or retry storm
# specifically, not to ever trip during real clinical use.
DEFAULT_ALERT_TOKENS_PER_MINUTE = 10 * ESTIMATED_TOKENS_PER_CALL
DEFAULT_HARD_BACKSTOP_TOKENS_PER_MINUTE = 100 * ESTIMATED_TOKENS_PER_CALL

# 5 consecutive failures (not 1) tolerates an isolated transient blip,
# consistent with this repo's existing connect/overall timeout convention
# (HttpTriageClient.java) rather than failing fast on the first hiccup.
# 30s reset gives a real outage a real chance to clear before the next
# probe, short enough not to leave the agent unusable for long.
DEFAULT_FAILURE_THRESHOLD = 5
DEFAULT_RESET_TIMEOUT_SECONDS = 30.0


@dataclass
class CircuitBreaker:
    """A consecutive-failure circuit breaker: closed -> open -> half-open -> closed."""

    failure_threshold: int = DEFAULT_FAILURE_THRESHOLD
    reset_timeout_seconds: float = DEFAULT_RESET_TIMEOUT_SECONDS

    _state: str = field(default="closed", init=False)
    _consecutive_failures: int = field(default=0, init=False)
    _opened_at: float = field(default=0.0, init=False)
    _lock: Lock = field(default_factory=Lock, init=False)

    def before_call(self) -> None:
        """Raise CircuitOpenError if the circuit is open and not ready for a trial call."""
        with self._lock:
            if self._state != "open":
                return
            if time.monotonic() - self._opened_at < self.reset_timeout_seconds:
                raise CircuitOpenError(
                    f"circuit open after {self._consecutive_failures} consecutive "
                    f"LLM API failures; will allow a trial call again "
                    f"{self.reset_timeout_seconds:.0f}s after the last trip"
                )
            # Reset window elapsed: allow exactly one trial call through
            # (half-open) without resetting the failure count yet -- a
            # success clears it in on_success(), a failure re-opens.
            self._state = "half_open"

    def on_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0
            self._state = "closed"

    def on_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.failure_threshold:
                self._state = "open"
                self._opened_at = time.monotonic()

    @property
    def state(self) -> str:
        return self._state


@dataclass
class RateCostLimiter:
    """
    Hybrid rate/cost posture (decisions.md H19): alert-only for legitimate
    clinical traffic, a hard backstop reserved for runaway/bug-driven
    spend. Tracks token usage in a sliding time window.
    """

    alert_tokens_per_minute: int = DEFAULT_ALERT_TOKENS_PER_MINUTE
    hard_backstop_tokens_per_minute: int = DEFAULT_HARD_BACKSTOP_TOKENS_PER_MINUTE
    window_seconds: float = 60.0

    _events: deque = field(default_factory=deque, init=False)  # (monotonic_ts, tokens)
    _lock: Lock = field(default_factory=Lock, init=False)

    def _windowed_total_locked(self, now: float) -> int:
        while self._events and now - self._events[0][0] > self.window_seconds:
            self._events.popleft()
        return sum(tokens for _, tokens in self._events)

    def before_call(self, estimated_tokens: int) -> bool:
        """
        Check the running total against both thresholds before a call is
        attempted. Returns True if this call crosses the alert threshold
        (still allowed through -- alert-only is informational, not a
        block). Raises CostLimitExceededError if the hard backstop is
        already exceeded -- the call is not attempted.
        """
        with self._lock:
            now = time.monotonic()
            total = self._windowed_total_locked(now)
            if total + estimated_tokens > self.hard_backstop_tokens_per_minute:
                raise CostLimitExceededError(
                    f"hard cost backstop exceeded: {total} tokens already used in the "
                    f"last {self.window_seconds:.0f}s (limit "
                    f"{self.hard_backstop_tokens_per_minute}) -- request blocked to "
                    "protect against runaway spend"
                )
            return total + estimated_tokens > self.alert_tokens_per_minute

    def record(self, actual_tokens: int) -> None:
        with self._lock:
            self._events.append((time.monotonic(), actual_tokens))


_breaker: CircuitBreaker | None = None
_limiter: RateCostLimiter | None = None


def get_circuit_breaker() -> CircuitBreaker:
    global _breaker
    if _breaker is None:
        _breaker = CircuitBreaker(
            failure_threshold=int(
                os.environ.get("LLM_CIRCUIT_FAILURE_THRESHOLD", DEFAULT_FAILURE_THRESHOLD)
            ),
            reset_timeout_seconds=float(
                os.environ.get("LLM_CIRCUIT_RESET_SECONDS", DEFAULT_RESET_TIMEOUT_SECONDS)
            ),
        )
    return _breaker


def get_rate_limiter() -> RateCostLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateCostLimiter(
            alert_tokens_per_minute=int(
                os.environ.get("LLM_ALERT_TOKENS_PER_MINUTE", DEFAULT_ALERT_TOKENS_PER_MINUTE)
            ),
            hard_backstop_tokens_per_minute=int(
                os.environ.get(
                    "LLM_HARD_BACKSTOP_TOKENS_PER_MINUTE",
                    DEFAULT_HARD_BACKSTOP_TOKENS_PER_MINUTE,
                )
            ),
        )
    return _limiter


def reset_resilience_state() -> None:
    """Reset the breaker and limiter singletons -- used by tests, mirrors reset_pool()."""
    global _breaker, _limiter
    _breaker = None
    _limiter = None


def call_with_resilience(fn: Callable[[], T], *, estimated_tokens: int) -> T:
    """
    Run fn() (the actual client.messages.create(...) call) behind the
    circuit breaker and rate/cost limiter. Raises CircuitOpenError or
    CostLimitExceededError -- without attempting fn() at all -- if either
    protection is tripped; the caller (agent.py) maps both onto the
    REVIEW fail-closed sink. Any exception fn() itself raises is recorded
    against the breaker and re-raised unchanged, so the caller's existing
    per-call error handling is untouched.
    """
    breaker = get_circuit_breaker()
    limiter = get_rate_limiter()

    if limiter.before_call(estimated_tokens):
        RATE_LIMIT_ALERTS_TOTAL.inc()
    breaker.before_call()

    start = time.monotonic()
    try:
        result = fn()
    except BREAKER_TRIPPING_EXCEPTIONS:
        breaker.on_failure()
        LLM_CALLS_TOTAL.labels(outcome="failure").inc()
        raise
    breaker.on_success()
    LLM_CALL_DURATION_SECONDS.observe(time.monotonic() - start)
    LLM_CALLS_TOTAL.labels(outcome="success").inc()
    return result


def record_usage(input_tokens: int, output_tokens: int) -> None:
    """
    Record a completed call's real token usage: into the rate limiter's
    sliding window (for the *next* call's threshold check) and into the
    Prometheus counter (for Grafana/alerting). Call once per successful
    LLM API response, after usage is known.
    """
    get_rate_limiter().record(input_tokens + output_tokens)
    LLM_TOKENS_TOTAL.labels(direction="input").inc(input_tokens)
    LLM_TOKENS_TOTAL.labels(direction="output").inc(output_tokens)
