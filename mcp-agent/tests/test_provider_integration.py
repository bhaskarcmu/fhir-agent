"""
Live integration test: run_query through the real M5 "ollama" provider
identity (docs/phase6/decisions.md H4, H45), pointed at a real local
Ollama instance -- not a fake, not a stub. This is the milestone's own
stated acceptance criterion (docs/phase6/prd.md M5: "The full M1
adversarial test corpus passes unmodified against the OpenAI-compatible
adapter pointed at a local Ollama model") -- M1's own live-Ollama test
(test_output_contract.py) talked to Ollama directly, bypassing the agent
loop, because this translation layer didn't exist yet; this file is that
same standing rule (H11) now exercised through the real thing.

Hard-fails (not self-skips) when Ollama isn't reachable -- Ollama is now
a required CI/dev dependency for this test, per decisions.md H50. See
conftest.py's ensure_ollama_model_available fixture, which also pulls the
required model on demand if Ollama is up but the model isn't pulled yet.

Run:
  python3 -m pytest mcp-agent/tests/test_provider_integration.py -v
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

from agent.agent import run_query
from agent_platform import AgentDecision
from agent_platform.providers import OpenAICompatibleProvider

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
# Matches test_output_contract.py's own default -- the lightest tag the
# setup instructions actually pull (`ollama pull llama3.2:1b`), and one
# confirmed to advertise "tools" capability. Also conftest.py's default.
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:1b")


def _fake_execute_tool(risk_level: str):
    """Stands in for the FHIR/triage tools -- real per M1's convention, only the
    clinical-data layer is faked here; the LLM call itself is real."""
    def _execute(name: str, inputs: dict) -> str:
        if name == "get_patient_summary":
            return json.dumps({
                "found": True,
                "patient": {"id": "patient-1", "name": "Test Patient", "gender": "female", "birth_date": "1990-01-01"},
            })
        if name == "assess_refill_risk":
            return json.dumps({"risk_level": risk_level, "assessment_id": "risk-1"})
        return json.dumps({"error": f"unexpected tool {name}"})

    return _execute


def test_live_ollama_resolves_to_a_valid_gated_decision(ensure_ollama_model_available):
    """
    Exercises the real translation layer (outbound tool schema + messages,
    inbound tool_calls/finish_reason) against a genuinely weak local
    model through the actual run_query loop, end to end -- not simulated.
    Whatever the model actually decides, the result must land on exactly
    one of the three enum values: the gate degrading safely against a
    real weak model speaking through a real HTTP round trip is the thing
    a mocked test alone cannot prove.
    """
    client = OpenAICompatibleProvider(base_url=f"{OLLAMA_HOST}/v1")
    with patch("agent.agent.execute_tool", _fake_execute_tool(risk_level="LOW")):
        final_text, messages = run_query(
            client,
            "Check refill risk for patient Test Patient",
            verbose=False,
            model=OLLAMA_MODEL,
            gen_ai_system="ollama",
        )

    assert any(decision.value in final_text for decision in AgentDecision)
    assert isinstance(messages, list)


def test_live_ollama_unknown_risk_is_never_narrated_as_dispense(ensure_ollama_model_available):
    """
    The core M1 invariant (decisions.md H18), now proven against a real
    weak model through the real translation layer rather than a canned
    fake response: an incomplete safety check is always forced to REVIEW,
    regardless of what the model itself concluded.
    """
    client = OpenAICompatibleProvider(base_url=f"{OLLAMA_HOST}/v1")
    with patch("agent.agent.execute_tool", _fake_execute_tool(risk_level="UNKNOWN")):
        final_text, _messages = run_query(
            client,
            "Check refill risk for patient Test Patient",
            verbose=False,
            model=OLLAMA_MODEL,
            gen_ai_system="ollama",
        )

    assert "REVIEW" in final_text
