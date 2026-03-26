"""
Integration tests for the triage service API.

Uses FastAPI TestClient — no running server required.
FHIRClient is mocked so no FHIR server is needed either.

Run:
  python3 -m pytest triage-service/src/triage/tests/test_api.py -v
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fhir_clinical_client import Allergy, Medication
from triage.main import app

client = TestClient(app)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _mock_fhir_client(medications=None, allergies=None):
    """Return a mock FHIRClient that returns the given lists."""
    mock = MagicMock()
    mock.get_medications.return_value = medications or []
    mock.get_allergies.return_value = allergies or []
    return mock


def _amoxicillin():
    return Medication(
        id="med-amox",
        code="723",
        display="Amoxicillin 250 MG Oral Capsule",
        status="active",
    )


def _penicillin_allergy():
    return Allergy(
        id="alg-pen",
        code="91936005",
        display="Allergy to penicillin",
        criticality="high",
        category=["medication"],
    )


def _fexofenadine():
    return Medication(
        id="med-fex",
        code="997488",
        display="Fexofenadine hydrochloride 30 MG Oral Tablet",
        status="active",
    )


def _loratadine():
    return Medication(
        id="med-lor",
        code="311372",
        display="Loratadine 10 MG Oral Tablet",
        status="active",
    )


# ─────────────────────────────────────────────────────────────────────────────
# /health
# ─────────────────────────────────────────────────────────────────────────────

class TestHealth:

    def test_health_returns_ok(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "version" in body


# ─────────────────────────────────────────────────────────────────────────────
# /triage/refill-risk — response structure
# ─────────────────────────────────────────────────────────────────────────────

class TestRefillRiskStructure:

    def test_returns_risk_assessment_resource_type(self):
        with patch("triage.main._get_client",
                   return_value=_mock_fhir_client()):
            resp = client.post("/triage/refill-risk",
                               json={"patient_id": "test-patient"})
        assert resp.status_code == 200
        assert resp.json()["resourceType"] == "RiskAssessment"

    def test_response_has_required_fields(self):
        with patch("triage.main._get_client",
                   return_value=_mock_fhir_client()):
            resp = client.post("/triage/refill-risk",
                               json={"patient_id": "test-patient"})
        body = resp.json()
        assert "id" in body
        assert "status" in body
        assert "subject" in body
        assert "prediction" in body
        assert "note" in body

    def test_subject_references_patient(self):
        with patch("triage.main._get_client",
                   return_value=_mock_fhir_client()):
            resp = client.post("/triage/refill-risk",
                               json={"patient_id": "patient-abc"})
        assert resp.json()["subject"]["reference"] == "Patient/patient-abc"

    def test_id_has_risk_prefix(self):
        with patch("triage.main._get_client",
                   return_value=_mock_fhir_client()):
            resp = client.post("/triage/refill-risk",
                               json={"patient_id": "test-patient"})
        assert resp.json()["id"].startswith("risk-")

    def test_status_is_final(self):
        with patch("triage.main._get_client",
                   return_value=_mock_fhir_client()):
            resp = client.post("/triage/refill-risk",
                               json={"patient_id": "test-patient"})
        assert resp.json()["status"] == "final"


# ─────────────────────────────────────────────────────────────────────────────
# /triage/refill-risk — risk levels
# ─────────────────────────────────────────────────────────────────────────────

class TestRefillRiskLevels:

    def test_penicillin_conflict_returns_high(self):
        with patch("triage.main._get_client",
                   return_value=_mock_fhir_client(
                       medications=[_amoxicillin()],
                       allergies=[_penicillin_allergy()],
                   )):
            resp = client.post("/triage/refill-risk",
                               json={"patient_id": "test-patient"})
        body = resp.json()
        assert body["prediction"][0]["outcome"]["coding"][0]["code"] == "HIGH"

    def test_duplicate_antihistamines_returns_moderate(self):
        with patch("triage.main._get_client",
                   return_value=_mock_fhir_client(
                       medications=[_fexofenadine(), _loratadine()],
                       allergies=[],
                   )):
            resp = client.post("/triage/refill-risk",
                               json={"patient_id": "test-patient"})
        body = resp.json()
        assert body["prediction"][0]["outcome"]["coding"][0]["code"] == "MODERATE"

    def test_no_conflicts_returns_low(self):
        with patch("triage.main._get_client",
                   return_value=_mock_fhir_client(
                       medications=[_fexofenadine()],
                       allergies=[],
                   )):
            resp = client.post("/triage/refill-risk",
                               json={"patient_id": "test-patient"})
        body = resp.json()
        assert body["prediction"][0]["outcome"]["coding"][0]["code"] == "LOW"

    def test_empty_patient_returns_low(self):
        with patch("triage.main._get_client",
                   return_value=_mock_fhir_client()):
            resp = client.post("/triage/refill-risk",
                               json={"patient_id": "test-patient"})
        body = resp.json()
        assert body["prediction"][0]["outcome"]["coding"][0]["code"] == "LOW"

    def test_high_risk_note_contains_conflict_language(self):
        with patch("triage.main._get_client",
                   return_value=_mock_fhir_client(
                       medications=[_amoxicillin()],
                       allergies=[_penicillin_allergy()],
                   )):
            resp = client.post("/triage/refill-risk",
                               json={"patient_id": "test-patient"})
        note = resp.json()["note"][0]["text"]
        assert "CONFLICT" in note

    def test_high_risk_basis_contains_medication_and_allergy_refs(self):
        with patch("triage.main._get_client",
                   return_value=_mock_fhir_client(
                       medications=[_amoxicillin()],
                       allergies=[_penicillin_allergy()],
                   )):
            resp = client.post("/triage/refill-risk",
                               json={"patient_id": "test-patient"})
        basis_refs = [b["reference"] for b in resp.json()["basis"]]
        assert any("MedicationRequest/med-amox" in r for r in basis_refs)
        assert any("AllergyIntolerance/alg-pen" in r for r in basis_refs)


# ─────────────────────────────────────────────────────────────────────────────
# /triage/refill-risk — error handling
# ─────────────────────────────────────────────────────────────────────────────

class TestRefillRiskErrors:

    def test_missing_patient_id_returns_422(self):
        resp = client.post("/triage/refill-risk", json={})
        assert resp.status_code == 422

    def test_fhir_not_found_returns_404(self):
        from fhir_clinical_client import NotFoundError
        mock = MagicMock()
        mock.get_medications.side_effect = NotFoundError("not found", 404, {})
        with patch("triage.main._get_client", return_value=mock):
            resp = client.post("/triage/refill-risk",
                               json={"patient_id": "nonexistent"})
        assert resp.status_code == 404

    def test_fhir_server_error_returns_502(self):
        from fhir_clinical_client import FHIRClientError
        mock = MagicMock()
        mock.get_medications.side_effect = FHIRClientError("server error", 500, {})
        with patch("triage.main._get_client", return_value=mock):
            resp = client.post("/triage/refill-risk",
                               json={"patient_id": "test-patient"})
        assert resp.status_code == 502
