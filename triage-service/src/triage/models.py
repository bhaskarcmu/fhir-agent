"""
Pydantic models for the triage service API.

Request and response shapes are defined here. The response is a FHIR
RiskAssessment resource — using the FHIR structure means the result can
be stored directly in an EHR for audit and traceability.
"""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


class TriageRequest(BaseModel):
    patient_id: str = Field(..., description="FHIR Patient ID")
    medication_id: Optional[str] = Field(
        None,
        description="Optional: evaluate a specific MedicationRequest ID. "
                    "If omitted, all active medications are evaluated.",
    )


class CodingModel(BaseModel):
    system: Optional[str] = None
    code: str
    display: str


class CodeableConceptModel(BaseModel):
    coding: list[CodingModel]
    text: Optional[str] = None


class PredictionModel(BaseModel):
    outcome: CodeableConceptModel
    qualitativeRisk: CodeableConceptModel


class AnnotationModel(BaseModel):
    text: str


class ReferenceModel(BaseModel):
    reference: str


class RiskAssessmentResponse(BaseModel):
    """
    FHIR RiskAssessment resource.

    Returned by POST /triage/refill-risk. The structure follows the FHIR R4
    RiskAssessment resource so it can be POSTed directly to a FHIR server
    for audit storage.
    """
    resourceType: Literal["RiskAssessment"] = "RiskAssessment"
    id: str
    status: Literal["registered", "preliminary", "final", "amended"] = "final"
    subject: ReferenceModel
    prediction: list[PredictionModel]
    note: list[AnnotationModel]
    basis: list[ReferenceModel] = Field(
        default_factory=list,
        description="References to the FHIR resources (MedicationRequest, "
                    "AllergyIntolerance) that contributed to this assessment.",
    )


class HealthResponse(BaseModel):
    status: str
    version: str
