"""
Tests for assess_refill_risk's M6 addition (docs/phase6/decisions.md
H15): surfacing the flagged medication's RxNorm code/display for the
post-decision citation lookup, without changing the risk determination
itself (which already happened via the triage service response parsed
above it).

Run:
  python3 -m pytest mcp-agent/tests/test_assess_refill_risk_citations.py -v
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

from agent.tools import assess_refill_risk


def _triage_response(risk_code: str, basis_references: list[str]):
    return SimpleNamespace(
        status_code=200,
        json=lambda: {
            "id": "risk-1",
            "prediction": [{"outcome": {"coding": [{"code": risk_code}]}}],
            "note": [{"text": "conflict detected"}],
            "basis": [{"reference": ref} for ref in basis_references],
        },
        raise_for_status=lambda: None,
    )


def _medication(id_: str, code: str, display: str):
    return SimpleNamespace(id=id_, code=code, display=display)


def test_flagged_medications_included_when_basis_references_a_medication_request():
    triage_resp = _triage_response("HIGH", ["MedicationRequest/5", "AllergyIntolerance/9"])
    medications = [
        _medication("5", "723", "Amoxicillin 500 MG Oral Capsule"),
        _medication("6", "310965", "Some other drug"),
    ]

    with patch("agent.tools.httpx.post", return_value=triage_resp), \
         patch("agent.tools._fhir_client") as mock_client_factory:
        mock_client_factory.return_value.get_medications.return_value = medications
        result = assess_refill_risk("patient-1")

    assert result["risk_level"] == "HIGH"
    assert result["flagged_medications"] == [
        {"rxnorm_code": "723", "display": "Amoxicillin 500 MG Oral Capsule"}
    ]


def test_no_flagged_medications_key_when_basis_has_no_medication_reference():
    triage_resp = _triage_response("LOW", ["AllergyIntolerance/9"])

    with patch("agent.tools.httpx.post", return_value=triage_resp):
        result = assess_refill_risk("patient-1")

    assert "flagged_medications" not in result


def test_medication_fetch_failure_does_not_affect_the_already_computed_risk_result():
    """
    Best-effort per decisions.md H15: the risk determination already
    happened via the triage response above -- a failure fetching
    supplementary medication details must never change or hide it.
    """
    triage_resp = _triage_response("HIGH", ["MedicationRequest/5"])

    with patch("agent.tools.httpx.post", return_value=triage_resp), \
         patch("agent.tools._fhir_client", side_effect=RuntimeError("FHIR_GATEWAY_URL is not set.")):
        result = assess_refill_risk("patient-1")

    assert result["risk_level"] == "HIGH"  # unaffected
    assert "flagged_medications" not in result  # simply absent, not an error


def test_full_result_is_json_serializable_through_execute_tool():
    """Regression guard: flagged_medications must round-trip through execute_tool's json.dumps."""
    from agent.tools import execute_tool

    triage_resp = _triage_response("HIGH", ["MedicationRequest/5"])
    medications = [_medication("5", "723", "Amoxicillin 500 MG Oral Capsule")]

    with patch("agent.tools.httpx.post", return_value=triage_resp), \
         patch("agent.tools._fhir_client") as mock_client_factory:
        mock_client_factory.return_value.get_medications.return_value = medications
        result_str = execute_tool("assess_refill_risk", {"patient_id": "patient-1"})

    parsed = json.loads(result_str)
    assert parsed["flagged_medications"][0]["rxnorm_code"] == "723"
