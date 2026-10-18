"""The ONLY things `outcome-prediction-agent` can do (design.md §9, O15) — published over HTTP.

The agent never imports this package: it reads these definitions from `GET /agent-tools` and
calls `POST /agent-tools/{name}`. So the service, not the agent, decides what an agent can ask:

| Tool | Does | Cannot |
|---|---|---|
| find_patient(name) | Candidates by name: ID, name, birth date | Pick among several — that goes back to the human |
| get_hospitalization_risk(patient_id, as_of?) | The service's RiskAssessment | Change any input, feature, threshold or model |
| get_model_card() | How the model was built (`/model`) | — |

There is no tool that takes feature values, a threshold, a model choice or a population: an agent
can't "re-score with a different age" or "flag everyone over 20%" — that would be clinical logic.
Every input schema forbids extra fields, and the API enforces it.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

MAX_CANDIDATES = 10

DEFINITIONS = [
    {
        "name": "find_patient",
        "description": ("Find patients by name. Returns candidates (id, name, birth date). If more than "
                        "one matches, do not choose: report the candidates and ask which patient is meant."),
        "input_schema": {"type": "object", "additionalProperties": False, "required": ["name"],
                         "properties": {"name": {"type": "string", "description": "Full or partial name"}}},
    },
    {
        "name": "get_hospitalization_risk",
        "description": ("The service's 12-month hospitalization risk estimate for ONE patient, as a FHIR "
                        "RiskAssessment. Takes only the patient id (and optionally the as-of date). It cannot "
                        "be adjusted, re-scored with different inputs, or classified as high/low."),
        "input_schema": {"type": "object", "additionalProperties": False, "required": ["patient_id"],
                         "properties": {"patient_id": {"type": "string"},
                                        "as_of": {"type": "string", "description": "YYYY-MM-DD; default today"}}},
    },
    {
        "name": "get_model_card",
        "description": "How the risk model was built: model version, training data, validation metrics.",
        "input_schema": {"type": "object", "additionalProperties": False, "properties": {}},
    },
]
NAMES = [d["name"] for d in DEFINITIONS]


class FindPatient(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)


class GetRisk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9\-.]+$")
    as_of: date | None = None


class GetModelCard(BaseModel):
    model_config = ConfigDict(extra="forbid")


INPUTS = {"find_patient": FindPatient, "get_hospitalization_risk": GetRisk, "get_model_card": GetModelCard}


def find_patient(client, name: str) -> dict:
    """Candidates only — never a choice among them."""
    found = client.search_patients(name)
    candidates = [{"id": p.id, "name": " ".join(x for x in (p.given_name, p.family_name) if x),
                   "birth_date": p.birth_date.isoformat() if p.birth_date else None}
                  for p in found[:MAX_CANDIDATES]]
    return {"found": len(found), "candidates": candidates, "ambiguous": len(found) > 1,
            "truncated": len(found) > MAX_CANDIDATES}
