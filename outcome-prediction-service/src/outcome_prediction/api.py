"""The scoring API (M7; design.md §5): 12-month hospitalization risk as FHIR R4.

    GET  /health                                    artifact loaded and verified?
    GET  /model                                     model ID, contract, training summary, metrics
    GET  /agent-tools, POST /agent-tools/{name}      the agent's only tools (tools.py, design.md §9)
    POST /risk/hospitalization-12m                  {patient_id, as_of?} -> RiskAssessment
    POST /risk/hospitalization-12m/contract-rows    {contract_version, rows} -> Bundle

Internal only — no Kong route (O14). Serves the `meps25-v1` model (approved by O2/O3; design.md
§8). The artifact is verified against its manifest at startup; a mismatch stops the service.

Environment:
  FHIR_GATEWAY_URL             FHIR server or Kong gateway (required for the patient endpoint)
  FHIR_API_KEY                 Kong key; omit for local dev
  OUTCOME_PREDICTION_ARTIFACT  artifact directory (default: newest gbm-meps25-v1-* under models/)

    uvicorn outcome_prediction.api:app --port 8005
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from outcome_prediction import tools
from outcome_prediction.etl.extract import fhir as fhir_extract
from outcome_prediction.etl.transform import to_contract
from outcome_prediction.fhir.risk_assessment import Bundle, Identifier, Reference, RiskAssessment, build, bundle
from outcome_prediction.model import CONTRACT_VERSION, FEATURES
from outcome_prediction.observability import current_trace_id, setup_tracing, tag_current_span
from outcome_prediction.scoring import Scorer

log = logging.getLogger("outcome_prediction.api")
HISTORY_DAYS = 400              # encounters and claims read before as_of: the 12-month window + margin
MAX_ROWS = 1000
DEFAULTED_FEATURE = {to_contract.WARN_INCOME: "povcaty1"}
WARN_REGION = "regiony1 = 0: region unknown"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.scorer = Scorer()                    # raises -> the service does not start
    log.info("serving %s", app.state.scorer.model_id)
    yield


app = FastAPI(title="Outcome prediction service",
              description="12-month hospitalization risk as a FHIR R4 RiskAssessment (Phase 8).",
              version="0.1.0", lifespan=lifespan)
setup_tracing(app)


def get_scorer(request: Request) -> Scorer:
    return request.app.state.scorer


def get_client():
    from fhir_clinical_client import FHIRClient
    url = os.environ.get("FHIR_GATEWAY_URL", "")
    if not url:
        raise HTTPException(503, "FHIR_GATEWAY_URL is not set: patient scoring is unavailable")
    return FHIRClient(gateway_url=url, api_key=os.environ.get("FHIR_API_KEY") or None)


@app.middleware("http")
async def trace_header(request: Request, call_next):
    response = await call_next(request)
    if trace_id := current_trace_id():
        response.headers["X-Trace-Id"] = trace_id
    return response


# ── metadata ─────────────────────────────────────────────────────────────────────────

@app.get("/health")
def health(scorer: Annotated[Scorer, Depends(get_scorer)]) -> dict:
    return {"status": "ok", "model_id": scorer.model_id, "artifact_verified": True}


@app.get("/model")
def model(scorer: Annotated[Scorer, Depends(get_scorer)]) -> dict:
    m = scorer.artifact.metadata
    return {
        "model_id": m["model_id"], "contract_version": m["contract_version"], "outcome": m["outcome"],
        "features": m["features"], "categorical": m["categorical"],
        "training": {k: m["training"][k] for k in ("panels", "rows", "events") if k in m["training"]},
        "validation_metrics": m["validation_metrics"],
        "metrics_note": "Measured on the validation models (trained on panels 21-25, tested on 26-27); "
                        "the served model is refit on all panels, so its own held-out performance is unknown.",
        "explanations": "occlusion against a typical MEPS adult; reasons describe what the model weighed, not causes",
        "versions": m["versions"], "created_at": m["created_at"],
    }


# ── scoring ──────────────────────────────────────────────────────────────────────────

class PatientRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9\-.]+$")
    as_of: date | None = None


class ContractRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_ref: str = Field(min_length=1, max_length=128)
    features: dict[str, int]


class ContractRowsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: str
    rows: list[ContractRow] = Field(min_length=1, max_length=MAX_ROWS)


@app.post("/risk/hospitalization-12m", response_model=RiskAssessment, response_model_exclude_none=True)
def score_patient(req: PatientRequest, scorer: Annotated[Scorer, Depends(get_scorer)],
                  client=Depends(get_client)):
    from fhir_clinical_client import FHIRClientError, NotFoundError
    as_of = req.as_of or datetime.now(timezone.utc).date()
    tag_current_span("outcome-prediction", trigger="patient", contract=CONTRACT_VERSION)
    try:
        extract = fhir_extract.read(client, [req.patient_id], since=as_of - timedelta(days=HISTORY_DAYS))
    except NotFoundError:
        raise HTTPException(404, f"patient {req.patient_id} not found")
    except FHIRClientError as e:
        log.warning("FHIR read failed for patient_ref=%s: %s", req.patient_id, e)
        raise HTTPException(502, "the FHIR server could not be read")
    rows, basis, warnings = to_contract.scoring_rows(extract.canonical, pd.Timestamp(as_of), explain=True)
    if rows.empty:
        raise HTTPException(422, f"patient {req.patient_id} is not an adult alive on {as_of}: no estimate is made")
    texts = list(warnings.warning) + [n for n in extract.notes.note if n != fhir_extract.NOTE_NO_INCOME]
    defaulted = {req.patient_id: {DEFAULTED_FEATURE[w] for w in warnings.warning if w in DEFAULTED_FEATURE}}
    score = scorer.score(rows, defaulted)[0]
    refs = [r for r in dict.fromkeys(basis.source_ref) if not r.startswith("Patient/")]
    log.info("scored patient_ref=%s model=%s", req.patient_id, scorer.model_id)
    return build(score, model_id=scorer.model_id, contract_version=CONTRACT_VERSION, as_of=as_of,
                 subject=Reference(reference=f"Patient/{req.patient_id}"), basis=refs, warnings=texts)


@app.post("/risk/hospitalization-12m/contract-rows", response_model=Bundle, response_model_exclude_none=True)
def score_rows(req: ContractRowsRequest, scorer: Annotated[Scorer, Depends(get_scorer)]):
    if req.contract_version != CONTRACT_VERSION:
        raise HTTPException(422, f"this service serves contract {CONTRACT_VERSION}, not {req.contract_version}")
    problems = []
    for i, row in enumerate(req.rows):
        if missing := [f for f in FEATURES if f not in row.features]:
            problems.append(f"row {i}: missing {missing}")
        if extra := sorted(set(row.features) - set(FEATURES)):
            problems.append(f"row {i}: unknown features {extra}")
        if negative := [f for f, v in row.features.items() if v < 0]:
            problems.append(f"row {i}: negative values for {negative} (send 0 for unknown categorical codes)")
    if problems:
        raise HTTPException(422, problems)
    rows = pd.DataFrame([{"patient_ref": r.patient_ref, **{f: r.features[f] for f in FEATURES}} for r in req.rows])
    rows[FEATURES] = rows[FEATURES].astype("int64")
    if problems := to_contract.check(rows):
        raise HTTPException(422, problems)
    tag_current_span("outcome-prediction", trigger="contract-rows", rows=len(rows))
    today = datetime.now(timezone.utc).date()
    warnings = {r.patient_ref: [WARN_REGION] if r.features["regiony1"] == 0 else [] for r in req.rows}
    assessments = [build(s, model_id=scorer.model_id, contract_version=CONTRACT_VERSION, as_of=today,
                         subject=Reference(identifier=Identifier(value=s.patient_ref)),
                         warnings=warnings[s.patient_ref])
                   for s in scorer.score(rows)]
    return bundle(assessments)


# ── the agent's tools (design.md §9; tools.py) ───────────────────────────────────────

@app.get("/agent-tools")
def agent_tools() -> list[dict]:
    """The complete list of what an agent may call — nothing else is reachable."""
    return tools.DEFINITIONS


@app.post("/agent-tools/{name}")
def call_agent_tool(name: str, args: dict, request: Request,
                    scorer: Annotated[Scorer, Depends(get_scorer)]) -> dict:
    """Run one tool. Arguments outside its schema are refused (422); an unknown tool is 404.
    A tool that ran answers 200 with an explicit `outcome`, so the agent never has to guess."""
    if name not in tools.INPUTS:
        raise HTTPException(404, f"no tool {name!r}; the tools are {tools.NAMES}")
    try:
        parsed = tools.INPUTS[name](**args)
    except ValidationError as e:
        raise HTTPException(422, [err["msg"] + f" ({'.'.join(map(str, err['loc']))})" for err in e.errors()])
    tag_current_span("outcome-prediction", trigger="agent-tool", tool=name)
    if name == "get_model_card":
        return {"outcome": "model_card", "model_card": model(scorer)}
    try:
        client = request.app.dependency_overrides.get(get_client, get_client)()
    except HTTPException as e:
        return {"outcome": "unavailable", "detail": e.detail}
    if name == "find_patient":
        from fhir_clinical_client import FHIRClientError
        try:
            return {"outcome": "candidates", **tools.find_patient(client, parsed.name)}
        except FHIRClientError:
            return {"outcome": "unavailable", "detail": "the FHIR server could not be searched"}
    try:
        ra = score_patient(PatientRequest(patient_id=parsed.patient_id, as_of=parsed.as_of), scorer, client)
    except HTTPException as e:
        outcome = {404: "not_found", 422: "no_estimate"}.get(e.status_code, "unavailable")
        return {"outcome": outcome, "detail": e.detail}
    return {"outcome": "estimate", "risk_assessment": ra.model_dump(exclude_none=True)}
