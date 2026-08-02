"""
Regression test for a real bug found live during M5 testing (docs/phase6/
decisions.md H11): a genuinely weak local model (llama3.2:1b via Ollama,
through the new OpenAI-compatible provider seam) omitted a required tool
argument, and execute_tool's raw dict indexing (inputs["patient_id"])
raised an uncaught KeyError that aborted the whole query instead of
failing closed. Confirmed via a real end-to-end CLI run against real
FHIR/triage services and a real Ollama model, not simulated -- see
docs/phase6/milestone-plan.md M5 for the live transcript.

Run:
  python3 -m pytest mcp-agent/tests/test_tools.py -v
"""

from __future__ import annotations

import json

from agent.tools import execute_tool
from agent_platform import RISK_UNKNOWN


def test_missing_required_argument_fails_closed_instead_of_raising():
    result_str = execute_tool("assess_refill_risk", {})  # patient_id omitted entirely
    result = json.loads(result_str)

    assert "error" in result
    assert "patient_id" in result["error"]
    assert result["risk_level"] == RISK_UNKNOWN


def test_missing_argument_on_get_patient_summary_also_fails_closed():
    result_str = execute_tool("get_patient_summary", {})  # name omitted
    result = json.loads(result_str)

    assert "error" in result
    assert "name" in result["error"]


def test_unknown_tool_name_is_unaffected():
    result_str = execute_tool("not_a_real_tool", {"whatever": "value"})
    result = json.loads(result_str)

    assert result == {"error": "Unknown tool: not_a_real_tool"}
