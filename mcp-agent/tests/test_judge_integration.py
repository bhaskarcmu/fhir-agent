"""
Live integration test: judge_response against a real local Ollama model
-- not simulated. Satisfies the standing local-LLM testing rule
(docs/phase6/decisions.md H11: "the judge... [is] evaluated against
outputs a local/weak model actually produced via M5's adapters -- not
only against Claude's own clean output") for the judge itself, not just
the main decision loop (see test_provider_integration.py for that).

Hard-fails (not self-skips) when Ollama isn't reachable, via the shared
conftest.py fixture -- same convention M5 established (H50).

Run:
  python3 -m pytest mcp-agent/tests/test_judge_integration.py -v
"""

from __future__ import annotations

import os

from agent_platform.providers import OpenAICompatibleProvider

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:1b")


def test_live_judge_produces_a_valid_result_or_fails_closed_to_inconclusive(ensure_ollama_model_available):
    """
    Whatever llama3.2:1b actually does with the judge's tool-call
    instructions -- cooperates cleanly, answers in free text, produces a
    malformed call -- judge_response must resolve to a well-formed
    JudgeResult, never raise. This is exactly the thing a mocked test
    can't prove: a real weak model's actual (sometimes uncooperative)
    tool-calling behavior.
    """
    from agent_platform.judge import JudgeResult, judge_response

    client = OpenAICompatibleProvider(base_url=f"{OLLAMA_HOST}/v1")
    result = judge_response(
        client,
        OLLAMA_MODEL,
        query="Check refill risk for a patient",
        rationale="Patient has a documented penicillin allergy and is prescribed amoxicillin. "
                   "Do not dispense without physician review.",
    )

    assert isinstance(result, JudgeResult)
    if result.available:
        assert isinstance(result.groundedness_ok, bool)
        assert isinstance(result.tone_ok, bool)
        assert isinstance(result.phi_leak_detected, bool)
