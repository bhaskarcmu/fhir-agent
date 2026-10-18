"""The scoring API (M7, M12; design.md §5): 12-month hospitalization risk as FHIR R4.

    GET  /health                                    the models served, each verified and promoted
    GET  /model, GET /models                        the agent's model card / every served model's
    GET  /agent-tools, POST /agent-tools/{name}      the agent's only tools (tools.py, design.md §9)
    POST /risk/{target}                             {patient_id, as_of?} -> RiskAssessment
    POST /risk/{target}/contract-rows               {contract_version, rows} -> Bundle

Two targets (M12):
    hospitalization-12m          meps25-v1          the reproduced prototype: any inpatient stay
    nonobstetric-admission-12m   meps-portable-v2   the first promotion (O59): a stay not related to
                                                    pregnancy or childbirth — the agent's model (O77)

Internal only — no Kong route (O14). Every artifact is verified against its manifest and must
carry a valid promotion record (PROMOTION.json, O33): otherwise the service does not start.

Environment:
  FHIR_GATEWAY_URL             FHIR server or Kong gateway (required for the patient endpoints)
  FHIR_API_KEY                 Kong key; omit for local dev
  OUTCOME_PREDICTION_ARTIFACTS comma-separated artifact directories (default: the newest of each
                               contract under models/); OUTCOME_PREDICTION_ARTIFACT names a meps25-v1 one

    uvicorn outcome_prediction.api:app --port 8005
"""
from __future__ import annotations

import logging
import math
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from outcome_prediction import contract as portable
from outcome_prediction import tools
from outcome_prediction.etl.extract import fhir as fhir_extract
from outcome_prediction.etl.transform import to_contract
from outcome_prediction.fhir.risk_assessment import Bundle, Identifier, Reference, RiskAssessment, build, bundle
from outcome_prediction.model import CONTRACT_VERSION as V1, FEATURES
from outcome_prediction.observability import current_trace_id, setup_tracing, tag_current_span
from outcome_prediction.scoring import ArtifactNotFound, Scorer, find_artifact

log = logging.getLogger("outcome_prediction.api")
HISTORY_DAYS = 400              # encounters and claims read before as_of: the 12-month window + margin
MAX_ROWS = 1000
DEFAULTED_FEATURE = {to_contract.WARN_INCOME: "povcaty1"}
WARN_REGION = "regiony1 = 0: region unknown"
V2 = portable.CONTRACT_VERSION


@dataclass(frozen=True)
class Target:
    slug: str
    contract: str
    outcome_text: str


TARGETS = {
    "hospitalization-12m": Target("hospitalization-12m", V1, "Hospital admission"),
    "nonobstetric-admission-12m": Target("nonobstetric-admission-12m", V2,
                                         "Hospital admission not related to pregnancy or childbirth"),
}
AGENT_TARGETS = ("nonobstetric-admission-12m", "hospitalization-12m")   # the first one served (O77)
# Extractor notes that only matter to inputs a contract uses (v2's records tier uses no fills).
NOTES_NOT_USED = {V2: {fhir_extract.NOTE_FILLS_FROM_CLAIMS, fhir_extract.NOTE_NO_INCOME}, V1: {fhir_extract.NOTE_NO_INCOME}}


def _artifact_dirs() -> list[Path]:
    if listed := os.environ.get("OUTCOME_PREDICTION_ARTIFACTS"):
        return [Path(p.strip()) for p in listed.split(",") if p.strip()]
    dirs = []
    for contract in (V1, V2):
        try:
            dirs.append(find_artifact(contract))
        except ArtifactNotFound:
            pass
    return dirs


@asynccontextmanager
async def lifespan(app: FastAPI):
    scorers = {}
    for directory in _artifact_dirs():
        scorer = Scorer(directory)                  # unverified or unpromoted -> raises: no start
        target = next(t for t in TARGETS.values() if t.contract == scorer.contract)
        scorers[target.slug] = scorer
        log.info("serving %s for %s (promoted by %s)", scorer.model_id, target.slug, scorer.promotion["decision"])
    if not scorers:
        raise ArtifactNotFound("no promoted artifact to serve")
    app.state.scorers = scorers
    yield


app = FastAPI(title="Outcome prediction service",
              description="12-month hospitalization risk as a FHIR R4 RiskAssessment (Phase 8).",
              version="0.2.0", lifespan=lifespan)
setup_tracing(app)


def scorer_for(request: Request, target: str) -> Scorer:
    if target not in TARGETS:
        raise HTTPException(404, f"no target {target!r}; the targets are {sorted(TARGETS)}")
    if target not in request.app.state.scorers:
        raise HTTPException(503, f"{target}: no promoted model is loaded")
    return request.app.state.scorers[target]


def agent_target(request: Request) -> str:
    return next(t for t in AGENT_TARGETS if t in request.app.state.scorers)


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
def health(request: Request) -> dict:
    scorers = request.app.state.scorers
    return {"status": "ok", "artifact_verified": True,
            "model_id": scorers[agent_target(request)].model_id,
            "models": {t: {"model_id": s.model_id, "promoted_by": s.promotion["decision"]} for t, s in scorers.items()}}


def card(scorer: Scorer, target: str) -> dict:
    m = scorer.artifact.metadata
    note = m.get("metrics_note") or ("Measured on the validation models (trained on panels 21-25, tested on "
                                     "26-27); the served model is refit on all panels, so its own held-out "
                                     "performance is unknown.")
    return {
        "target": target, "model_id": m["model_id"], "contract_version": m["contract_version"],
        "outcome": m["outcome"], "features": m["features"], "categorical": m["categorical"],
        "training": {k: m["training"][k] for k in ("panels", "rows", "events") if k in m["training"]},
        "validation_metrics": m["validation_metrics"], "metrics_note": note,
        "promoted_by": scorer.promotion["decision"],
        "explanations": "occlusion against a typical MEPS adult; reasons describe what the model weighed, not causes",
        "versions": m["versions"], "created_at": m["created_at"],
    }


@app.get("/model")
def model(request: Request) -> dict:
    """The agent's model (the first promotion, when served)."""
    target = agent_target(request)
    return card(request.app.state.scorers[target], target)


@app.get("/models")
def models(request: Request) -> list[dict]:
    return [card(s, t) for t, s in request.app.state.scorers.items()]


# ── scoring ──────────────────────────────────────────────────────────────────────────

class PatientRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9\-.]+$")
    as_of: date | None = None


class ContractRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_ref: str = Field(min_length=1, max_length=128)
    features: dict[str, int | float | str | None]


class ContractRowsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: str
    rows: list[ContractRow] = Field(min_length=1, max_length=MAX_ROWS)


def assess(target: str, req: PatientRequest, scorer: Scorer, client) -> RiskAssessment:
    """One patient from the FHIR server, scored for `target`."""
    from fhir_clinical_client import FHIRClientError, NotFoundError
    as_of = req.as_of or datetime.now(timezone.utc).date()
    tag_current_span("outcome-prediction", trigger="patient", contract=scorer.contract, target=target)
    try:
        extract = fhir_extract.read(client, [req.patient_id], since=as_of - timedelta(days=HISTORY_DAYS))
    except NotFoundError:
        raise HTTPException(404, f"patient {req.patient_id} not found")
    except FHIRClientError as e:
        log.warning("FHIR read failed for patient_ref=%s: %s", req.patient_id, e)
        raise HTTPException(502, "the FHIR server could not be read")
    rows_for = to_contract.scoring_rows if scorer.contract == V1 else to_contract.portable_scoring_rows
    rows, basis, warnings = rows_for(extract.canonical, pd.Timestamp(as_of), explain=True)
    if rows.empty:
        raise HTTPException(422, f"patient {req.patient_id} is not an adult alive on {as_of}: no estimate is made")
    texts = list(warnings.warning) + [n for n in extract.notes.note if n not in NOTES_NOT_USED[scorer.contract]]
    defaulted = {req.patient_id: {DEFAULTED_FEATURE[w] for w in warnings.warning if w in DEFAULTED_FEATURE}}
    score = scorer.score(rows, defaulted)[0]
    refs = [r for r in dict.fromkeys(basis.source_ref) if not r.startswith("Patient/")]
    log.info("scored patient_ref=%s model=%s", req.patient_id, scorer.model_id)
    return build(score, model_id=scorer.model_id, contract_version=scorer.contract, as_of=as_of,
                 subject=Reference(reference=f"Patient/{req.patient_id}"), basis=refs, warnings=texts,
                 outcome_text=TARGETS[target].outcome_text)


@app.post("/risk/{target}", response_model=RiskAssessment, response_model_exclude_none=True)
def score_patient(target: str, req: PatientRequest, request: Request, client=Depends(get_client)):
    return assess(target, req, scorer_for(request, target), client)


def _v1_rows(req: ContractRowsRequest) -> tuple[pd.DataFrame, dict]:
    problems = []
    for i, row in enumerate(req.rows):
        if missing := [f for f in FEATURES if f not in row.features]:
            problems.append(f"row {i}: missing {missing}")
        if extra := sorted(set(row.features) - set(FEATURES)):
            problems.append(f"row {i}: unknown features {extra}")
        if not_int := [f for f, v in row.features.items() if not isinstance(v, int) or isinstance(v, bool)]:
            problems.append(f"row {i}: {not_int} must be integers")
        elif negative := [f for f, v in row.features.items() if v < 0]:
            problems.append(f"row {i}: negative values for {negative} (send 0 for unknown categorical codes)")
    if problems:
        raise HTTPException(422, problems)
    rows = pd.DataFrame([{"patient_ref": r.patient_ref, **{f: r.features[f] for f in FEATURES}} for r in req.rows])
    rows[FEATURES] = rows[FEATURES].astype("int64")
    if problems := to_contract.check(rows):
        raise HTTPException(422, problems)
    return rows, {r.patient_ref: [WARN_REGION] if r.features["regiony1"] == 0 else [] for r in req.rows}


V2_MAY_BE_NULL = set(portable.OPTIONAL) | {"regiony1"}      # inputs a record may not carry (O53)
V2_CODES = {"sex": {1, 2}, "racethx": {1, 2, 3, 4, 5}, "regiony1": {1, 2, 3, 4}, "inscovy1": {1, 2, 3},
            "povcaty1": {1, 2, 3, 4, 5}}


def _v2_rows(req: ContractRowsRequest, scorer: Scorer) -> tuple[pd.DataFrame, dict]:
    inputs, problems = scorer.inputs, []
    for i, row in enumerate(req.rows):
        f = row.features
        if missing := [c for c in inputs if c not in f]:
            problems.append(f"row {i}: missing {missing}")
        if extra := sorted(set(f) - set(inputs)):
            problems.append(f"row {i}: unknown features {extra}")
        for c, v in f.items():
            if c == portable.TEXT_COLUMN:
                if not isinstance(v, str):
                    problems.append(f"row {i}: {c} must be a string of ICD-10 codes, e.g. 'icdI10 icdE11'")
            elif v is None:
                if c not in V2_MAY_BE_NULL:
                    problems.append(f"row {i}: {c} is required (only {sorted(V2_MAY_BE_NULL)} may be null)")
            elif isinstance(v, str) or isinstance(v, bool) or (isinstance(v, float) and math.isnan(v)) or v < 0:
                problems.append(f"row {i}: {c} must be a number ≥ 0 or null")
            elif c in V2_CODES and v not in V2_CODES[c]:
                problems.append(f"row {i}: {c} = {v} is not one of {sorted(V2_CODES[c])}")
    if problems:
        raise HTTPException(422, problems)
    rows = pd.DataFrame([{"patient_ref": r.patient_ref, **r.features} for r in req.rows])
    numeric = [c for c in inputs if c != portable.TEXT_COLUMN]
    rows[numeric] = rows[numeric].astype(float)
    warnings = {r.patient_ref: [n for c, n in (("povcaty1", to_contract.WARN_NO_INCOME_V2), ("regiony1", "region unknown"))
                                if r.features.get(c) is None] for r in req.rows}
    return rows, warnings


@app.post("/risk/{target}/contract-rows", response_model=Bundle, response_model_exclude_none=True)
def score_rows(target: str, req: ContractRowsRequest, request: Request):
    scorer = scorer_for(request, target)
    if req.contract_version != scorer.contract:
        raise HTTPException(422, f"{target} is served on contract {scorer.contract}, not {req.contract_version}")
    rows, warnings = _v1_rows(req) if scorer.contract == V1 else _v2_rows(req, scorer)
    tag_current_span("outcome-prediction", trigger="contract-rows", rows=len(rows), target=target)
    today = datetime.now(timezone.utc).date()
    assessments = [build(s, model_id=scorer.model_id, contract_version=scorer.contract, as_of=today,
                         subject=Reference(identifier=Identifier(value=s.patient_ref)),
                         warnings=warnings[s.patient_ref], outcome_text=TARGETS[target].outcome_text)
                   for s in scorer.score(rows)]
    return bundle(assessments)


# ── the agent's tools (design.md §9; tools.py) ───────────────────────────────────────

@app.get("/agent-tools")
def agent_tools() -> list[dict]:
    """The complete list of what an agent may call — nothing else is reachable."""
    return tools.DEFINITIONS


@app.post("/agent-tools/{name}")
def call_agent_tool(name: str, args: dict, request: Request) -> dict:
    """Run one tool. Arguments outside its schema are refused (422); an unknown tool is 404.
    A tool that ran answers 200 with an explicit `outcome`, so the agent never has to guess."""
    if name not in tools.INPUTS:
        raise HTTPException(404, f"no tool {name!r}; the tools are {tools.NAMES}")
    try:
        parsed = tools.INPUTS[name](**args)
    except ValidationError as e:
        raise HTTPException(422, [err["msg"] + f" ({'.'.join(map(str, err['loc']))})" for err in e.errors()])
    tag_current_span("outcome-prediction", trigger="agent-tool", tool=name)
    target = agent_target(request)
    if name == "get_model_card":
        return {"outcome": "model_card", "model_card": card(request.app.state.scorers[target], target)}
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
        ra = assess(target, PatientRequest(patient_id=parsed.patient_id, as_of=parsed.as_of),
                    request.app.state.scorers[target], client)
    except HTTPException as e:
        outcome = {404: "not_found", 422: "no_estimate"}.get(e.status_code, "unavailable")
        return {"outcome": outcome, "detail": e.detail}
    return {"outcome": "estimate", "risk_assessment": ra.model_dump(exclude_none=True)}
