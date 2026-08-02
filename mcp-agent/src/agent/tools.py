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

from agent_platform import RISK_UNKNOWN, safe_risk_level
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
    {
        "name": "submit_decision",
        "description": (
            "Submit your final recommendation for this refill-risk query. This MUST be your "
            "last action once you have the information you need — do not write a free-text "
            "final answer instead; call this tool. "
            "Map assess_refill_risk's risk level to a decision: LOW risk → DISPENSE, "
            "HIGH risk → DO_NOT_DISPENSE, MODERATE risk or anything you are not confident "
            "about → REVIEW. If assess_refill_risk returned risk_level UNKNOWN or an error "
            "(the safety check could not be completed), you must submit REVIEW — never "
            "DISPENSE or DO_NOT_DISPENSE on an incomplete check, even if other context makes "
            "you want to guess."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "decision": {
                    "type": "string",
                    "enum": ["DISPENSE", "DO_NOT_DISPENSE", "REVIEW"],
                    "description": "Your final recommendation.",
                },
                "patient_id": {
                    "type": "string",
                    "description": "The FHIR Patient ID this decision is about.",
                },
                "risk_assessment_id": {
                    "type": "string",
                    "description": (
                        "The FHIR RiskAssessment ID returned by assess_refill_risk, for audit "
                        "purposes. Omit only if a risk assessment could not be obtained."
                    ),
                },
                "rationale": {
                    "type": "string",
                    "description": (
                        "A brief, factual clinical rationale for this decision, grounded in "
                        "what assess_refill_risk actually returned. Do not fabricate."
                    ),
                },
            },
            "required": ["decision", "patient_id", "rationale"],
        },
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Client factories
# ─────────────────────────────────────────────────────────────────────────────

def _fhir_client() -> FHIRClient:
    gateway_url = os.environ.get("FHIR_GATEWAY_URL", "")
    api_key = os.environ.get("FHIR_API_KEY", "")
    if not gateway_url:
        raise RuntimeError(
            "FHIR_GATEWAY_URL is not set. "
            "Example: export FHIR_GATEWAY_URL=http://localhost:8000/fhir"
        )
    if not api_key:
        return FHIRClient(gateway_url=gateway_url)
    return FHIRClient(gateway_url=gateway_url, api_key=api_key)


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

    Fail-closed data-layer guard (docs/phase6/decisions.md H18, mirroring
    claims-service's HttpTriageClient.java): every path that does not
    produce a risk level this function understands -- triage down,
    erroring, or an unrecognized response -- returns risk_level
    RISK_UNKNOWN, never a value that could be read as safe. "risk_level"
    is always present in the returned dict, including on error paths, so
    a caller can detect an incomplete check by that key alone without
    also checking for "error".
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
        return {
            "error": f"Triage service error ({exc.response.status_code}): {detail}",
            "risk_level": RISK_UNKNOWN,
        }
    except httpx.RequestError as exc:
        return {
            "error": f"Cannot reach triage service at {triage_url}: {exc}. "
                     "Is the triage service running?",
            "risk_level": RISK_UNKNOWN,
        }

    # Extract the key fields for the agent to reason about. A missing or
    # unrecognized code fails closed to RISK_UNKNOWN -- it is never passed
    # through raw and never assumed to mean "safe".
    raw_code = (
        assessment.get("prediction", [{}])[0]
        .get("outcome", {})
        .get("coding", [{}])[0]
        .get("code")
    )
    risk_code = safe_risk_level(raw_code)
    note = assessment.get("note", [{}])[0].get("text", "")
    basis = assessment.get("basis", [])
    assessment_id = assessment.get("id", "")

    result = {
        "risk_level": risk_code,
        "assessment_id": assessment_id,
        "note": note,
        "basis_count": len(basis),
        "basis_references": [b["reference"] for b in basis],
        "full_assessment": assessment,
    }
    if risk_code == RISK_UNKNOWN and raw_code:
        # The response parsed fine but the code itself wasn't recognized --
        # distinct from a missing code, worth surfacing to the agent as text.
        result["error"] = f"Triage returned an unrecognized risk code: {raw_code!r}"
    return result


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
