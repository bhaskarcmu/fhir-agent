"""
Tool layer for the claims explanation agent.

The single tool calls the claims-service adjudication façade and returns the **authoritative**
decision. The agent explains that decision; it never computes or alters it (non-authoritative,
R17.8). No clinical or business logic lives here.

Environment:
  CLAIMS_GATEWAY_URL  Base URL of the claims-service (default http://localhost:8090).
                      Point at the Kong proxy for the gated setup.
  CLAIMS_API_KEY      Kong API key (omit for local/direct).
"""
from __future__ import annotations

import json
import os

import httpx

TOOL_DEFINITIONS = [
    {
        "name": "adjudicate_claim",
        "description": (
            "Submit a prescription claim to the claims-adjudication service and return the "
            "authoritative decision (outcome, reasons, and pricing). This is the source of "
            "truth — explain its result; never change or second-guess the outcome."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "claim": {
                    "type": "object",
                    "description": "A canonical claim object (memberId, planId, rxcui, ndc, "
                                   "quantity, dateOfService, coverage dates, etc.).",
                }
            },
            "required": ["claim"],
        },
    }
]


class ClaimsClient:
    """Thin HTTP client to the claims-service adjudication endpoint."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 client: httpx.Client | None = None):
        self.base_url = (base_url or os.environ.get("CLAIMS_GATEWAY_URL",
                                                    "http://localhost:8090")).rstrip("/")
        self.api_key = api_key if api_key is not None else os.environ.get("CLAIMS_API_KEY", "")
        self._client = client or httpx.Client(timeout=30)

    def adjudicate(self, claim: dict) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["apikey"] = self.api_key
        resp = self._client.post(f"{self.base_url}/claims/adjudicate",
                                 json=claim, headers=headers)
        resp.raise_for_status()
        return resp.json()


def execute_tool(name: str, tool_input: dict, client: ClaimsClient) -> str:
    """Dispatch an Anthropic tool call. Returns a JSON string (never raises into the loop)."""
    if name != "adjudicate_claim":
        return json.dumps({"error": f"unknown tool: {name}"})
    try:
        decision = client.adjudicate(tool_input["claim"])
        return json.dumps(decision)
    except httpx.HTTPError as e:
        return json.dumps({"error": f"claims-service call failed: {e}"})
    except Exception as e:  # noqa: BLE001 - tools must not raise into the agent loop
        return json.dumps({"error": str(e)})
