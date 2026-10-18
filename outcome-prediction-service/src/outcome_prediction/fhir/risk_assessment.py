"""FHIR R4 `RiskAssessment` and `Bundle` for a 12-month hospitalization estimate (O3, design.md §4).

A superset of triage-service's shape: it adds the numeric probability. Deliberately absent:
`qualitativeRisk` — no thresholds have been clinically signed off (O24). The rationale is
templated from the reasons, never model-generated.
"""
from __future__ import annotations

import html
import uuid
from datetime import date

import pandas as pd
from pydantic import BaseModel, ConfigDict

from outcome_prediction.scoring import FEATURE_NAMES, Score

EXT = "http://fhir-agent.local/StructureDefinition/"
MODEL_SYSTEM = "http://fhir-agent.local/outcome-prediction/model"
# SNOMED CT 32485007 — checked in M7 against tx.fhir.org (International edition 2025-02-01):
# active, FSN "Hospital admission (procedure)", parent "Admission to establishment" (O22).
OUTCOME = {"system": "http://snomed.info/sct", "code": "32485007", "display": "Hospital admission (procedure)"}
NOTE = ("12-month planning estimate for population care management, not a diagnosis and not for "
        "emergencies. Trained on US MEPS public survey data; not yet validated on this organisation's "
        "patients. The reasons describe what the model weighed, not what causes admissions.")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Coding(_Model):
    system: str
    code: str
    display: str | None = None


class CodeableConcept(_Model):
    coding: list[Coding]
    text: str | None = None


class Identifier(_Model):
    value: str


class Reference(_Model):
    reference: str | None = None
    identifier: Identifier | None = None


class Extension(_Model):
    url: str
    valueDecimal: float | None = None
    valueInteger: int | None = None
    valueString: str | None = None


class Period(_Model):
    start: str
    end: str


class Prediction(_Model):
    outcome: CodeableConcept
    probabilityDecimal: float
    whenPeriod: Period
    rationale: str
    extension: list[Extension]


class Annotation(_Model):
    text: str


class Narrative(_Model):
    status: str = "generated"
    div: str


class RiskAssessment(_Model):
    resourceType: str = "RiskAssessment"
    id: str
    text: Narrative | None = None
    status: str = "final"
    subject: Reference
    occurrenceDateTime: str
    method: CodeableConcept
    basis: list[Reference] = []
    prediction: list[Prediction]
    note: list[Annotation]
    extension: list[Extension] = []


class BundleEntry(_Model):
    fullUrl: str
    resource: RiskAssessment


class Bundle(_Model):
    resourceType: str = "Bundle"
    id: str
    type: str = "collection"
    entry: list[BundleEntry]


def rationale(reasons: list[str]) -> str:
    if not reasons:
        return "No single input raises this estimate much above a typical adult's."
    names = [FEATURE_NAMES[r] for r in reasons]
    joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    return f"Inputs raising the estimate most, compared with a typical adult: {joined}."


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def build(score: Score, *, model_id: str, contract_version: str, as_of: date, subject: Reference,
          basis: list[str] = (), warnings: list[str] = (), outcome_text: str = "Hospital admission") -> RiskAssessment:
    """One RiskAssessment. `basis` are FHIR `Type/id` references to the records used (FR-F4).
    `outcome_text` names the target (M12): SNOMED has no concept for "a hospital admission not related
    to pregnancy or childbirth", so the code stays 32485007 and the text says what is predicted (O77)."""
    extensions = [
        Extension(url=EXT + "comparison-probability", valueDecimal=round(score.comparison, 4)),
        Extension(url=EXT + "risk-percentile", valueInteger=score.percentile),
        Extension(url=EXT + "contract-version", valueString=contract_version),
        *[Extension(url=EXT + "top-reasons", valueString=r) for r in score.reasons],
    ]
    summary = (f"Estimated chance of a {outcome_text[0].lower() + outcome_text[1:]} in the 12 months from {as_of.isoformat()}: "
               f"{score.probability:.1%} ({_ordinal(score.percentile)} percentile of the training population). "
               f"{rationale(score.reasons)}")
    return RiskAssessment(
        id=str(uuid.uuid4()),
        text=Narrative(div=f'<div xmlns="http://www.w3.org/1999/xhtml"><p>{html.escape(summary)}</p>'
                           f"<p>{html.escape(NOTE)}</p></div>"),
        subject=subject,
        occurrenceDateTime=as_of.isoformat(),
        method=CodeableConcept(coding=[Coding(system=MODEL_SYSTEM, code=model_id)], text=model_id),
        basis=[Reference(reference=ref) for ref in basis],
        prediction=[Prediction(
            outcome=CodeableConcept(coding=[Coding(**OUTCOME)], text=outcome_text),
            probabilityDecimal=round(score.probability, 4),
            whenPeriod=Period(start=as_of.isoformat(), end=(pd.Timestamp(as_of) + pd.DateOffset(months=12)).date().isoformat()),
            rationale=rationale(score.reasons),
            extension=extensions)],
        note=[Annotation(text=NOTE)],
        extension=[Extension(url=EXT + "input-warning", valueString=w) for w in warnings],
    )


def bundle(assessments: list[RiskAssessment]) -> Bundle:
    return Bundle(id=str(uuid.uuid4()),
                  entry=[BundleEntry(fullUrl=f"urn:uuid:{a.id}", resource=a) for a in assessments])
