"""
Shared fixture for this test suite's live-Ollama tests (docs/phase6/
decisions.md H50, superseding the earlier self-skip convention): Ollama
is now a required CI/dev dependency for the tests that specifically
exercise real weak-model behavior, not an optional adversarial-testing
nice-to-have. Those tests hard-fail (pytest.fail, not pytest.skip) when
Ollama is genuinely unreachable.

Deliberately NOT autouse -- the large body of fake-client agent-loop
tests in this suite (test_output_contract.py's canned-response cases,
test_tracing.py, test_resilience_integration.py, etc.) test logic that's
orthogonal to which real model backs it, and must keep running with zero
dependency on Ollama being available. Only the specific tests that need
a real model request this fixture explicitly.

Session-scoped: checked/pulled once per test run, not once per test --
pulling a model on a cold cache can take real time.
"""

from __future__ import annotations

import os

import httpx
import pytest

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:1b")

# Bounded, matching this repo's existing timeout-not-retry-forever
# convention (HttpTriageClient.java, M4's breaker/deadline logic) -- a
# stuck download must not hang the test run indefinitely.
_PULL_TIMEOUT_SECONDS = 300.0


def _pulled_model_names() -> set[str]:
    response = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=5.0)
    response.raise_for_status()
    return {m["name"] for m in response.json().get("models", [])}


def _pull_model(model: str) -> None:
    with httpx.stream(
        "POST", f"{OLLAMA_HOST}/api/pull", json={"name": model}, timeout=_PULL_TIMEOUT_SECONDS,
    ) as response:
        response.raise_for_status()
        for _ in response.iter_lines():
            pass  # drain -- Ollama streams pull progress as newline-delimited JSON; we just wait for completion


@pytest.fixture(scope="session")
def ensure_ollama_model_available() -> None:
    """
    Requested explicitly by tests that need a real local model. Fails the
    test descriptively (not a raw connection-error traceback) if Ollama
    is unreachable, or if the required model can't be pulled -- one
    attempt, no retry loop, matching decisions.md H50's "don't
    over-engineer this" scope.
    """
    try:
        if OLLAMA_MODEL not in _pulled_model_names():
            _pull_model(OLLAMA_MODEL)
    except Exception as exc:
        pytest.fail(
            f"Ollama at {OLLAMA_HOST} is required for this test but the model "
            f"{OLLAMA_MODEL!r} could not be made available: {exc}",
            pytrace=False,
        )
