"""
Triage service — FastAPI application.

Stateless microservice that evaluates drug-allergy conflict risk for a
patient. Fetches clinical data via fhir-clinical-client, runs the rule
engine, and returns a FHIR RiskAssessment resource.

Environment variables:
  FHIR_GATEWAY_URL   Base URL of the FHIR server (required)
                     e.g. http://fhir-service:8080/fhir  (docker-compose)
                          http://localhost:8080/fhir      (local dev)
                          http://<kong-ip>:8000/fhir      (deployed)
  FHIR_API_KEY       Kong API key — omit for local dev without Kong
"""

from __future__ import annotations

import os
import uuid
import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from fhir_clinical_client import FHIRClient, FHIRClientError, NotFoundError

from .models import (
    AnnotationModel,
    CodeableConceptModel,
    CodingModel,
    HealthResponse,
    PredictionModel,
    ReferenceModel,
    RiskAssessmentResponse,
    TriageRequest,
)
from .rules import RuleResult, evaluate

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
log = logging.getLogger("triage")

# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────

VERSION = "0.1.0"

app = FastAPI(
    title="Triage Service",
    description=(
        "Drug-allergy conflict triage microservice. "
        "Evaluates refill risk for a patient and returns a FHIR RiskAssessment."
    ),
    version=VERSION,
)


def _get_client() -> FHIRClient:
    """Build a FHIRClient from environment variables."""
    gateway_url = os.environ.get("FHIR_GATEWAY_URL", "")
    api_key = os.environ.get("FHIR_API_KEY", "")
    if not gateway_url:
        raise RuntimeError(
            "FHIR_GATEWAY_URL is not set. "
            "Set it to the Kong gateway URL, e.g. http://localhost:8000/fhir"
        )
    if not api_key:
        raise RuntimeError(
            "FHIR_API_KEY is not set. "
            "The triage service is a clinical-hat consumer — it always authenticates "
            "through Kong. Run: bash gateway/tools/create-key.sh <name>"
        )
    return FHIRClient(gateway_url=gateway_url, api_key=api_key)


def _build_risk_assessment(
    patient_id: str,
    result: RuleResult,
) -> RiskAssessmentResponse:
    """Convert a RuleResult into a FHIR RiskAssessment response."""
    risk_level = result.risk_level
    qualitative_code = risk_level.lower()  # "high", "moderate", "low"

    prediction = PredictionModel(
        outcome=CodeableConceptModel(
            coding=[CodingModel(
                system="http://fhir-agent.local/triage/risk-level",
                code=risk_level,
                display=f"{risk_level.title()} Risk",
            )],
            text=f"{risk_level.title()} Risk",
        ),
        qualitativeRisk=CodeableConceptModel(
            coding=[CodingModel(
                system="http://terminology.hl7.org/CodeSystem/risk-probability",
                code=qualitative_code,
                display=risk_level.title(),
            )],
        ),
    )

    basis = (
        [ReferenceModel(reference=f"MedicationRequest/{mid}")
         for mid in result.basis_medication_ids]
        + [ReferenceModel(reference=f"AllergyIntolerance/{aid}")
           for aid in result.basis_allergy_ids]
    )

    return RiskAssessmentResponse(
        id=f"risk-{uuid.uuid4().hex[:8]}",
        subject=ReferenceModel(reference=f"Patient/{patient_id}"),
        prediction=[prediction],
        note=[AnnotationModel(text=result.note)],
        basis=basis,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["ops"])
def health() -> HealthResponse:
    """Liveness check."""
    return HealthResponse(status="ok", version=VERSION)


@app.post(
    "/triage/refill-risk",
    response_model=RiskAssessmentResponse,
    tags=["triage"],
    summary="Evaluate refill risk for a patient",
    response_description="FHIR RiskAssessment resource with risk level and clinical rationale",
)
def assess_refill_risk(request: TriageRequest) -> RiskAssessmentResponse:
    """
    Evaluate drug-allergy conflict risk for a patient.

    Fetches the patient's active medications and all recorded allergies
    from the FHIR server, runs the rule engine, and returns a FHIR
    RiskAssessment resource.

    The `basis` field in the response contains references to the specific
    MedicationRequest and AllergyIntolerance resources that triggered the
    assessment — providing a full audit trail.
    """
    client = _get_client()
    patient_id = request.patient_id

    log.info("Assessing refill risk for patient %s", patient_id)

    # ── Fetch clinical data ───────────────────────────────────────────────────
    try:
        medications = client.get_medications(patient_id)
        allergies = client.get_allergies(patient_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found.")
    except FHIRClientError as exc:
        log.error("FHIR error for patient %s: %s", patient_id, exc)
        raise HTTPException(status_code=502, detail=f"FHIR server error: {exc}")

    # ── Filter to specific medication if requested ────────────────────────────
    if request.medication_id:
        medications = [m for m in medications if m.id == request.medication_id]
        if not medications:
            raise HTTPException(
                status_code=404,
                detail=f"MedicationRequest {request.medication_id} not found "
                       f"in active medications for patient {patient_id}.",
            )

    log.info(
        "Patient %s: %d medication(s), %d allergy/ies",
        patient_id, len(medications), len(allergies),
    )

    # ── Evaluate rules ────────────────────────────────────────────────────────
    result = evaluate(medications, allergies)

    log.info(
        "Patient %s: risk=%s rule=%s",
        patient_id, result.risk_level, result.rule_id,
    )

    return _build_risk_assessment(patient_id, result)
