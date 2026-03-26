"""
Tool implementations for the MCP agent.

Each function here corresponds to one Anthropic tool definition. Tools
call either FHIRClient (for patient data) or the triage service (for
risk assessment). No clinical logic lives here — the agent orchestrates,
the triage service evaluates.

Environment variables consumed:
  FHIR_GATEWAY_URL    Base URL of the FHIR server
  FHIR_API_KEY        Kong API key (omit for local dev)
  TRIAGE_SERVICE_URL  Base URL of the triage service
"""

from __future__ import annotations

import json
import os

import httpx

from fhir_clinical_client import FHIRClient, FHIRClientError, NotFoundError


# ─────────────────────────────────────────────────────────────────────────────
# Anthropic tool definitions
# ─────────────────────────────────────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "get_patient_summary",
        "description": (
            "Find a patient by name and return their demographics and FHIR ID. "
            "Use this first to resolve a patient name to an ID before calling "
            "other tools. Supports partial name matching — 'Kristle' or 'Mraz' "
            "will both find 'Kristle Mraz'. Returns all matches if multiple "
            "patients share a name."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Patient name or partial name to search for.",
                }
            },
            "required": ["name"],
        },
    },
    {
        "name": "assess_refill_risk",
        "description": (
            "Evaluate drug-allergy conflict risk for a patient. "
            "Fetches the patient's active medications and recorded allergies, "
            "runs the triage rule engine, and returns a structured risk assessment "
            "with risk level (HIGH/MODERATE/LOW), clinical rationale, and a "
            "FHIR RiskAssessment ID for audit purposes. "
            "Requires a patient_id — call get_patient_summary first if you only "
            "have a name. "
            "Optionally pass medication_id to evaluate a specific prescription; "
            "omit it to evaluate all active medications."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "FHIR Patient ID returned by get_patient_summary.",
                },
                "medication_id": {
                    "type": "string",
                    "description": (
                        "FHIR MedicationRequest ID to evaluate a specific prescription. "
                        "If omitted, all active medications are evaluated."
                    ),
                },
            },
            "required": ["patient_id"],
        },
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Client factories
# ─────────────────────────────────────────────────────────────────────────────

def _fhir_client() -> FHIRClient:
    gateway_url = os.environ.get("FHIR_GATEWAY_URL", "")
    api_key = os.environ.get("FHIR_API_KEY", "local")
    if not gateway_url:
        raise RuntimeError(
            "FHIR_GATEWAY_URL is not set. "
            "Example: export FHIR_GATEWAY_URL=http://localhost:8080/fhir"
        )
    # FHIRClient appends /fhir internally. Strip it from the env var if present
    # so FHIR_GATEWAY_URL=http://host:8080/fhir and http://host:8080 both work.
    base = gateway_url.rstrip("/")
    if base.endswith("/fhir"):
        base = base[: -len("/fhir")]
    return FHIRClient(gateway_url=base, api_key=api_key)


def _triage_url() -> str:
    url = os.environ.get("TRIAGE_SERVICE_URL", "http://localhost:8001")
    return url.rstrip("/")


# ─────────────────────────────────────────────────────────────────────────────
# Tool: get_patient_summary
# ─────────────────────────────────────────────────────────────────────────────

def get_patient_summary(name: str) -> dict:
    """
    Search for patients by name. Returns a structured result the agent
    can reason about — either a single match, multiple matches, or not found.
    """
    try:
        client = _fhir_client()
        patients = client.search_patients(name)
    except FHIRClientError as exc:
        return {"error": f"FHIR server error: {exc}"}
    except RuntimeError as exc:
        return {"error": str(exc)}

    if not patients:
        return {
            "found": False,
            "message": f"No patients found matching '{name}'. "
                       "Try a different spelling or partial name.",
        }

    results = [
        {
            "id": p.id,
            "name": f"{p.given_name} {p.family_name}",
            "gender": p.gender,
            "birth_date": p.birth_date.isoformat() if p.birth_date else None,
        }
        for p in patients
    ]

    if len(results) == 1:
        return {
            "found": True,
            "patient": results[0],
        }

    return {
        "found": True,
        "multiple_matches": True,
        "count": len(results),
        "patients": results,
        "message": (
            f"Found {len(results)} patients matching '{name}'. "
            "Please clarify which patient you mean, or use the patient ID directly."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tool: assess_refill_risk
# ─────────────────────────────────────────────────────────────────────────────

def assess_refill_risk(
    patient_id: str,
    medication_id: str | None = None,
) -> dict:
    """
    Call the triage service to evaluate refill risk for a patient.
    Returns the full RiskAssessment response plus a simplified summary
    the agent can use to compose its narrative.
    """
    triage_url = _triage_url()
    payload: dict = {"patient_id": patient_id}
    if medication_id:
        payload["medication_id"] = medication_id

    try:
        response = httpx.post(
            f"{triage_url}/triage/refill-risk",
            json=payload,
            timeout=30.0,
        )
        response.raise_for_status()
        assessment = response.json()
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", str(exc))
        except Exception:
            detail = str(exc)
        return {"error": f"Triage service error ({exc.response.status_code}): {detail}"}
    except httpx.RequestError as exc:
        return {
            "error": f"Cannot reach triage service at {triage_url}: {exc}. "
                     "Is the triage service running?"
        }

    # Extract the key fields for the agent to reason about
    risk_code = (
        assessment.get("prediction", [{}])[0]
        .get("outcome", {})
        .get("coding", [{}])[0]
        .get("code", "UNKNOWN")
    )
    note = assessment.get("note", [{}])[0].get("text", "")
    basis = assessment.get("basis", [])
    assessment_id = assessment.get("id", "")

    return {
        "risk_level": risk_code,
        "assessment_id": assessment_id,
        "note": note,
        "basis_count": len(basis),
        "basis_references": [b["reference"] for b in basis],
        "full_assessment": assessment,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────────────────────

def execute_tool(name: str, inputs: dict) -> str:
    """
    Dispatch a tool call by name and return the result as a JSON string.
    The agent passes this string back to Claude as the tool result.
    """
    if name == "get_patient_summary":
        result = get_patient_summary(inputs["name"])
    elif name == "assess_refill_risk":
        result = assess_refill_risk(
            patient_id=inputs["patient_id"],
            medication_id=inputs.get("medication_id"),
        )
    else:
        result = {"error": f"Unknown tool: {name}"}

    return json.dumps(result, indent=2)
