"""
End-to-end tests for the demo flow.

Exercises the full tool chain — get_patient_summary → assess_refill_risk —
without live services. FHIRClient is mocked at the class level; the triage
HTTP call is mocked via httpx.

These tests validate the exact scenarios created by data/scripts/seed_demo.py:
  - Kristle Mraz: penicillin allergy + amoxicillin Rx → HIGH risk
  - John Doe:     no allergies + lisinopril Rx        → LOW risk

Run:
  python3 -m pytest mcp-agent/tests/test_e2e_demo_flow.py -v
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import httpx
import pytest

from fhir_clinical_client import Allergy, Medication, Patient
from agent.tools import execute_tool, get_patient_summary, assess_refill_risk


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures — demo patient data matching seed_demo.py
# ─────────────────────────────────────────────────────────────────────────────

KRISTLE_PATIENT = Patient(
    id="patient-kristle",
    family_name="Mraz",
    given_name="Kristle",
    gender="female",
    birth_date=None,
)

KRISTLE_AMOXICILLIN = Medication(
    id="med-amox-kristle",
    code="723",
    display="Amoxicillin 500 MG Oral Capsule",
    status="active",
)

KRISTLE_PENICILLIN_ALLERGY = Allergy(
    id="alg-pen-kristle",
    code="764146007",          # SNOMED CT: Penicillin (matches seed_demo.py)
    display="Penicillin",
    criticality="high",
    category=["medication"],
)

JOHN_PATIENT = Patient(
    id="patient-john",
    family_name="Doe",
    given_name="John",
    gender="male",
    birth_date=None,
)

JOHN_LISINOPRIL = Medication(
    id="med-lisinopril-john",
    code="29046",
    display="Lisinopril 10 MG Oral Tablet",
    status="active",
)


def _mock_fhir_client(patients=None, medications=None, allergies=None):
    mock = MagicMock()
    mock.search_patients.return_value = patients or []
    mock.get_medications.return_value = medications or []
    mock.get_allergies.return_value = allergies or []
    return mock


def _triage_response(risk_level: str, patient_id: str, note: str) -> dict:
    """Minimal valid FHIR RiskAssessment matching the triage service output shape."""
    return {
        "resourceType": "RiskAssessment",
        "id": f"risk-demo-{risk_level.lower()}",
        "status": "final",
        "subject": {"reference": f"Patient/{patient_id}"},
        "prediction": [{
            "outcome": {
                "coding": [{"code": risk_level, "display": f"{risk_level} RISK"}]
            }
        }],
        "note": [{"text": note}],
        "basis": [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Demo scenario 1: Kristle Mraz — HIGH risk
# ─────────────────────────────────────────────────────────────────────────────

class TestKristleMrazHighRisk:
    """
    Validates the primary demo scenario end-to-end.

    get_patient_summary("Kristle Mraz") → single match
    assess_refill_risk(patient_id)      → HIGH risk (penicillin conflict)
    """

    def test_get_patient_summary_finds_kristle(self):
        with patch("agent.tools._fhir_client",
                   return_value=_mock_fhir_client(patients=[KRISTLE_PATIENT])):
            result = json.loads(execute_tool("get_patient_summary", {"name": "Kristle Mraz"}))

        assert result["found"] is True
        assert "multiple_matches" not in result
        assert result["patient"]["id"] == "patient-kristle"
        assert result["patient"]["name"] == "Kristle Mraz"

    def test_assess_refill_risk_returns_high(self):
        triage_resp = _triage_response(
            risk_level="HIGH",
            patient_id="patient-kristle",
            note="CONFLICT DETECTED: Amoxicillin belongs to the penicillin family. "
                 "Patient has a recorded allergy to: Penicillin.",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = triage_resp
        mock_response.raise_for_status = MagicMock()

        with patch("agent.tools.httpx.post", return_value=mock_response):
            result = json.loads(execute_tool(
                "assess_refill_risk",
                {"patient_id": "patient-kristle"},
            ))

        assert result["risk_level"] == "HIGH"
        assert result["assessment_id"] == "risk-demo-high"
        assert "CONFLICT" in result["note"]

    def test_full_demo_flow_kristle(self):
        """
        Simulates the exact sequence the agent executes for the demo query:
        'Check refill risk for Kristle Mraz'
        """
        # Step 1: agent calls get_patient_summary
        with patch("agent.tools._fhir_client",
                   return_value=_mock_fhir_client(patients=[KRISTLE_PATIENT])):
            summary = json.loads(execute_tool(
                "get_patient_summary", {"name": "Kristle Mraz"}
            ))

        assert summary["found"] is True
        patient_id = summary["patient"]["id"]

        # Step 2: agent calls assess_refill_risk with the resolved patient_id
        triage_resp = _triage_response(
            risk_level="HIGH",
            patient_id=patient_id,
            note="CONFLICT DETECTED: Amoxicillin — penicillin allergy on record.",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = triage_resp
        mock_response.raise_for_status = MagicMock()

        with patch("agent.tools.httpx.post", return_value=mock_response):
            assessment = json.loads(execute_tool(
                "assess_refill_risk", {"patient_id": patient_id}
            ))

        assert assessment["risk_level"] == "HIGH"
        assert assessment["assessment_id"].startswith("risk-")


# ─────────────────────────────────────────────────────────────────────────────
# Demo scenario 2: John Doe — LOW risk
# ─────────────────────────────────────────────────────────────────────────────

class TestJohnDoeLowRisk:
    """
    Validates the contrast demo scenario.

    get_patient_summary("John Doe") → single match
    assess_refill_risk(patient_id)  → LOW risk (no conflicts)
    """

    def test_get_patient_summary_finds_john(self):
        with patch("agent.tools._fhir_client",
                   return_value=_mock_fhir_client(patients=[JOHN_PATIENT])):
            result = json.loads(execute_tool("get_patient_summary", {"name": "John Doe"}))

        assert result["found"] is True
        assert result["patient"]["id"] == "patient-john"

    def test_assess_refill_risk_returns_low(self):
        triage_resp = _triage_response(
            risk_level="LOW",
            patient_id="patient-john",
            note="No drug-allergy conflicts detected. Safe to dispense.",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = triage_resp
        mock_response.raise_for_status = MagicMock()

        with patch("agent.tools.httpx.post", return_value=mock_response):
            result = json.loads(execute_tool(
                "assess_refill_risk",
                {"patient_id": "patient-john"},
            ))

        assert result["risk_level"] == "LOW"

    def test_full_demo_flow_john(self):
        """Simulates 'Check refill risk for John Doe'."""
        with patch("agent.tools._fhir_client",
                   return_value=_mock_fhir_client(patients=[JOHN_PATIENT])):
            summary = json.loads(execute_tool(
                "get_patient_summary", {"name": "John Doe"}
            ))

        patient_id = summary["patient"]["id"]

        triage_resp = _triage_response(
            risk_level="LOW",
            patient_id=patient_id,
            note="No drug-allergy conflicts detected. Safe to dispense.",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = triage_resp
        mock_response.raise_for_status = MagicMock()

        with patch("agent.tools.httpx.post", return_value=mock_response):
            assessment = json.loads(execute_tool(
                "assess_refill_risk", {"patient_id": patient_id}
            ))

        assert assessment["risk_level"] == "LOW"


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_patient_not_found_returns_structured_error(self):
        with patch("agent.tools._fhir_client",
                   return_value=_mock_fhir_client(patients=[])):
            result = json.loads(execute_tool(
                "get_patient_summary", {"name": "Nobody Real"}
            ))

        assert result["found"] is False
        assert "message" in result

    def test_multiple_patients_returns_multiple_matches(self):
        john1 = Patient(id="p1", family_name="Doe", given_name="John", gender="male")
        john2 = Patient(id="p2", family_name="Doe", given_name="John", gender="male")
        with patch("agent.tools._fhir_client",
                   return_value=_mock_fhir_client(patients=[john1, john2])):
            result = json.loads(execute_tool(
                "get_patient_summary", {"name": "John Doe"}
            ))

        assert result["found"] is True
        assert result["multiple_matches"] is True
        assert result["count"] == 2
        assert len(result["patients"]) == 2

    def test_assess_refill_risk_with_medication_id(self):
        """medication_id is forwarded to the triage service payload."""
        triage_resp = _triage_response("LOW", "patient-john", "Safe to dispense.")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = triage_resp
        mock_response.raise_for_status = MagicMock()

        with patch("agent.tools.httpx.post", return_value=mock_response) as mock_post:
            execute_tool("assess_refill_risk", {
                "patient_id": "patient-john",
                "medication_id": "med-lisinopril-john",
            })

        payload = mock_post.call_args.kwargs["json"]
        assert payload["patient_id"] == "patient-john"
        assert payload["medication_id"] == "med-lisinopril-john"

    def test_triage_service_unreachable_returns_error(self):
        with patch("agent.tools.httpx.post",
                   side_effect=httpx.ConnectError("connection refused")):
            result = json.loads(execute_tool(
                "assess_refill_risk", {"patient_id": "patient-kristle"}
            ))

        assert "error" in result
        assert "triage service" in result["error"].lower()

    def test_unknown_tool_returns_error(self):
        result = json.loads(execute_tool("nonexistent_tool", {}))
        assert "error" in result
        assert "Unknown tool" in result["error"]
