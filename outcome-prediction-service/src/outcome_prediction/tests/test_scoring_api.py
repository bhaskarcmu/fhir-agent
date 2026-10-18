"""M7: the scoring API — RiskAssessment shape, both triggers, guards, explanations, startup refusal.

Runs offline: a real artifact is trained by `model.train` on the synthetic table (no MEPS), and
the patient endpoint reads M6's recorded FHIR conversation (`fixtures/fhir_recording.json`).
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from outcome_prediction import api, scoring
from outcome_prediction.fhir import risk_assessment as ra
from outcome_prediction.model import FEATURES
from outcome_prediction.model.promotion import write_promotion
from outcome_prediction.model.train import train
from outcome_prediction.tests.synthetic_portable import build_portable_artifact
from outcome_prediction.tests.conftest import synthetic_table
from outcome_prediction.tests.test_etl_fhir import LINK, RECORDING, Replay

PATIENT = next(iter(LINK))
AS_OF = "2023-12-31"


class Server(Replay):
    """The recorded server. The recording reads from 2021 on; the API asks for as_of minus 400
    days, so its `since` is mapped onto the recorded one — the recording starts earlier, and
    scoring only uses the 12 months before as_of."""

    def _request(self, path, method="GET", body=None, headers=None):
        path = re.sub(r"(date|created)=ge\d{4}-\d{2}-\d{2}", rf"\1=ge{RECORDING['since']}", path)
        return super()._request(path, method, body, headers)


@pytest.fixture(scope="module")
def artifact(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("m7")
    table = root / "table.csv"
    synthetic_table(per_panel=200, seed=1).to_csv(table, index=False)
    directory, _ = train(table, root / "models", root / "reports")
    write_promotion(directory, "O2", note="test")
    return directory


@pytest.fixture(scope="module")
def portable_artifact(tmp_path_factory) -> Path:
    return build_portable_artifact(tmp_path_factory.mktemp("m12") / "models")


@pytest.fixture
def client(artifact, portable_artifact, monkeypatch):
    monkeypatch.setenv("OUTCOME_PREDICTION_ARTIFACTS", f"{artifact},{portable_artifact}")
    api.app.dependency_overrides[api.get_client] = lambda: Server()
    with TestClient(api.app) as c:
        yield c
    api.app.dependency_overrides.clear()


def _row(**overrides) -> dict:
    features = {f: 0 for f in FEATURES} | {"sex": 2, "racethx": 2, "regiony1": 3, "agey1x": 70, "inscovy1": 2,
                                          "povcaty1": 3, "obtotvy1": 6, "rxtoty1": 20, "totexpy1": 9000}
    return {"patient_ref": "row-1", "features": features | overrides}


# ── metadata ─────────────────────────────────────────────────────────────────────────

def test_health_reports_both_verified_promoted_models(client, artifact, portable_artifact):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["artifact_verified"] is True
    assert body["models"] == {"hospitalization-12m": {"model_id": artifact.name, "promoted_by": "O2"},
                              "nonobstetric-admission-12m": {"model_id": portable_artifact.name, "promoted_by": "O59"}}
    assert body["model_id"] == portable_artifact.name                 # the agent's model (O77)


def test_model_metadata_labels_its_metrics(client):
    cards = {c["target"]: c for c in client.get("/models").json()}
    v1 = cards["hospitalization-12m"]
    assert v1["contract_version"] == "meps25-v1" and v1["features"] == FEATURES
    assert "validation models" in v1["metrics_note"] and "auroc" in v1["validation_metrics"]["gbm"]
    assert client.get("/model").json()["contract_version"] == "meps-portable-v2"


def test_a_tampered_artifact_stops_the_service(artifact, monkeypatch, tmp_path):
    import shutil
    bad = tmp_path / artifact.name
    shutil.copytree(artifact, bad)
    (bad / "model.joblib").write_bytes(b"tampered")
    monkeypatch.setenv("OUTCOME_PREDICTION_ARTIFACT", str(bad))
    with pytest.raises(Exception, match="(?i)manifest|sha|mismatch|changed"):
        with TestClient(api.app):
            pass


# ── trigger A: a patient in the FHIR server ──────────────────────────────────────────

def test_patient_gets_a_risk_assessment(client):
    r = client.post("/risk/hospitalization-12m", json={"patient_id": PATIENT, "as_of": AS_OF})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["resourceType"] == "RiskAssessment" and body["status"] == "final"
    assert body["subject"] == {"reference": f"Patient/{PATIENT}"} and body["occurrenceDateTime"] == AS_OF
    p = body["prediction"][0]
    assert p["outcome"]["coding"][0] == ra.OUTCOME
    assert 0 < p["probabilityDecimal"] < 1
    assert p["whenPeriod"] == {"start": AS_OF, "end": "2024-12-31"}
    urls = {e["url"].rsplit("/", 1)[1] for e in p["extension"]}
    assert {"comparison-probability", "risk-percentile", "contract-version"} <= urls
    assert "qualitativeRisk" not in p                                    # O24: no unsigned-off bands
    assert body["method"]["coding"][0]["system"] == ra.MODEL_SYSTEM


def test_basis_cites_records_the_server_holds(client):
    body = client.post("/risk/hospitalization-12m", json={"patient_id": PATIENT, "as_of": AS_OF}).json()
    held = {f"{e['resource']['resourceType']}/{e['resource']['id']}"
            for page in RECORDING["responses"].values() for e in page.get("entry", [])}
    refs = [b["reference"] for b in body["basis"]]
    assert refs and set(refs) <= held and not any(r.startswith("Patient/") for r in refs)


def test_defaults_and_substitutions_are_warned_and_never_reasons(client):
    body = client.post("/risk/hospitalization-12m", json={"patient_id": PATIENT, "as_of": AS_OF}).json()
    warnings = [e["valueString"] for e in body["extension"] if e["url"].endswith("input-warning")]
    assert any("povcaty1 defaulted" in w for w in warnings)
    assert any("pharmacy claims" in w for w in warnings)
    reasons = [e["valueString"] for e in body["prediction"][0]["extension"] if e["url"].endswith("top-reasons")]
    assert "povcaty1" not in reasons


def test_unknown_patient_is_404(client):
    from fhir_clinical_client import NotFoundError

    class Missing(Server):
        def _request(self, path, method="GET", body=None, headers=None):
            raise NotFoundError("gone", 404)
    api.app.dependency_overrides[api.get_client] = lambda: Missing()
    assert client.post("/risk/hospitalization-12m", json={"patient_id": "nope"}).status_code == 404


def test_no_estimate_before_the_patient_is_an_adult(client):
    r = client.post("/risk/hospitalization-12m", json={"patient_id": PATIENT, "as_of": "1950-01-01"})
    assert r.status_code == 422 and "not an adult alive" in r.json()["detail"]


@pytest.mark.parametrize("payload", [{"patient_id": "a/b"}, {"patient_id": ""}, {"patient_id": "1", "age": 40}])
def test_patient_request_is_validated(client, payload):
    assert client.post("/risk/hospitalization-12m", json=payload).status_code == 422


# ── trigger B: contract rows ─────────────────────────────────────────────────────────

def test_contract_rows_return_a_bundle(client):
    rows = [_row(), {**_row(agey1x=30, rxtoty1=0, totexpy1=200), "patient_ref": "row-2"}]
    r = client.post("/risk/hospitalization-12m/contract-rows", json={"contract_version": "meps25-v1", "rows": rows})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["resourceType"] == "Bundle" and b["type"] == "collection" and len(b["entry"]) == 2
    first = b["entry"][0]["resource"]
    assert first["subject"] == {"identifier": {"value": "row-1"}}
    assert first.get("basis", []) == []                                 # contract rows cite no records
    assert b["entry"][0]["fullUrl"] == f"urn:uuid:{first['id']}"


@pytest.mark.parametrize("change, message", [
    ({"contract_version": "meps25-v2"}, "served on contract meps25-v1"),
    ({"rows": [_row(sex=-1)]}, "negative"),
    ({"rows": [_row(racethx=9)]}, "racethx"),
    ({"rows": [{"patient_ref": "x", "features": {"sex": 1}}]}, "missing"),
    ({"rows": [{**_row(), "features": {**_row()["features"], "bmi": 30}}]}, "unknown features"),
    ({"rows": []}, ""),
])
def test_bad_contract_rows_are_refused(client, change, message):
    payload = {"contract_version": "meps25-v1", "rows": [_row()]} | change
    r = client.post("/risk/hospitalization-12m/contract-rows", json=payload)
    assert r.status_code == 422 and message in r.text


def test_batch_limit(client):
    rows = [{**_row(), "patient_ref": f"r{i}"} for i in range(api.MAX_ROWS + 1)]
    r = client.post("/risk/hospitalization-12m/contract-rows", json={"contract_version": "meps25-v1", "rows": rows})
    assert r.status_code == 422


def test_unknown_region_is_warned(client):
    r = client.post("/risk/hospitalization-12m/contract-rows",
                    json={"contract_version": "meps25-v1", "rows": [_row(regiony1=0)]})
    ext = r.json()["entry"][0]["resource"]["extension"]
    assert [e["valueString"] for e in ext] == [api.WARN_REGION]


# ── explanations (FR-M8) ─────────────────────────────────────────────────────────────

def test_reasons_are_inputs_that_raise_the_estimate(artifact):
    scorer = scoring.Scorer(artifact)
    typical = pd.DataFrame([{"patient_ref": "t", **scorer.typical}])
    assert scorer.score(typical)[0].reasons == []                        # nothing differs from typical
    heavy = typical.assign(patient_ref="h", ipdisy1=4, ipngtdy1=30, agey1x=84)
    score = scorer.score(heavy)[0]
    assert score.reasons and set(score.reasons) <= {"ipdisy1", "ipngtdy1", "agey1x"}
    assert len(score.reasons) <= scoring.TOP_REASONS


def test_rationale_is_templated_from_reasons():
    assert ra.rationale(["agey1x", "ipdisy1"]) == ("Inputs raising the estimate most, compared with a typical "
                                                    "adult: age and hospital stays in the past year.")
    assert "No single input" in ra.rationale([])


# ── latency (deliverable: single row under 100 ms) ───────────────────────────────────

def test_single_row_latency_is_under_100_ms(client):
    payload = {"contract_version": "meps25-v1", "rows": [_row()]}
    client.post("/risk/hospitalization-12m/contract-rows", json=payload)           # warm up
    times = []
    for _ in range(30):
        t = time.perf_counter()
        assert client.post("/risk/hospitalization-12m/contract-rows", json=payload).status_code == 200
        times.append(time.perf_counter() - t)
    assert sorted(times)[len(times) // 2] < 0.100


def test_race_is_never_a_reason(artifact):
    """O50: race/ethnicity is used by meps25-v1 but never given as a per-patient reason."""
    scorer = scoring.Scorer(artifact)
    for race in (1, 3, 4, 5):
        row = pd.DataFrame([{"patient_ref": "r", **scorer.typical, "racethx": race}])
        assert "racethx" not in scorer.score(row)[0].reasons


def test_narrative_is_escaped_text(client):
    body = client.post("/risk/hospitalization-12m", json={"patient_id": PATIENT, "as_of": AS_OF}).json()
    div = body["text"]["div"]
    assert body["text"]["status"] == "generated" and div.startswith('<div xmlns="http://www.w3.org/1999/xhtml">')
    assert "percentile" in div and "not a diagnosis" in div
    assert ra._ordinal(1) == "1st" and ra._ordinal(12) == "12th" and ra._ordinal(83) == "83rd"


def test_batch_reasons_equal_one_at_a_time(artifact):
    scorer = scoring.Scorer(artifact)
    rows = pd.DataFrame([{"patient_ref": f"r{i}", **_row(agey1x=30 + 7 * i, ipdisy1=i % 3, chddx=i % 2)["features"]}
                         for i in range(8)])
    together = scorer.score(rows)
    alone = [scorer.score(rows.iloc[[i]])[0] for i in range(len(rows))]
    assert [s.reasons for s in together] == [s.reasons for s in alone]
    assert [round(s.probability, 12) for s in together] == [round(s.probability, 12) for s in alone]


# ── the agent's tools (M8, design.md §9) ─────────────────────────────────────────────

AGENT_SNAPSHOT = Path(__file__).resolve().parents[4] / "outcome-prediction-agent" / "tests" / "fixtures" / "service_tools.json"


def test_exactly_three_tools_and_none_takes_features_thresholds_or_models(client):
    defs = client.get("/agent-tools").json()
    assert [d["name"] for d in defs] == ["find_patient", "get_hospitalization_risk", "get_model_card"]
    for d in defs:
        props = set(d["input_schema"]["properties"])
        assert d["input_schema"]["additionalProperties"] is False
        assert props <= {"name", "patient_id", "as_of"}, d["name"]


def test_the_agents_snapshot_of_the_tools_is_current(client):
    """outcome-prediction-agent's tests replay this snapshot; drift fails here."""
    import json
    assert json.loads(AGENT_SNAPSHOT.read_text()) == client.get("/agent-tools").json()


def test_tool_arguments_outside_the_schema_are_refused(client):
    r = client.post("/agent-tools/get_hospitalization_risk", json={"patient_id": PATIENT, "agey1x": 40})
    assert r.status_code == 422 and "agey1x" in r.text
    assert client.post("/agent-tools/rank_patients", json={}).status_code == 404
    assert client.post("/agent-tools/get_model_card", json={"threshold": 0.2}).status_code == 422


def test_risk_tool_returns_the_same_assessment_as_the_api(client):
    tool = client.post("/agent-tools/get_hospitalization_risk", json={"patient_id": PATIENT, "as_of": AS_OF}).json()
    direct = client.post("/risk/nonobstetric-admission-12m", json={"patient_id": PATIENT, "as_of": AS_OF}).json()
    assert tool["outcome"] == "estimate"
    strip = lambda ra: {k: v for k, v in ra.items() if k not in ("id", "text")}  # noqa: E731
    assert strip(tool["risk_assessment"]) == strip(direct)


def test_risk_tool_outcomes_are_explicit(client):
    early = client.post("/agent-tools/get_hospitalization_risk", json={"patient_id": PATIENT, "as_of": "1950-01-01"}).json()
    assert early["outcome"] == "no_estimate"
    card = client.post("/agent-tools/get_model_card", json={}).json()
    assert card["outcome"] == "model_card" and card["model_card"]["contract_version"] == "meps-portable-v2"


def test_find_patient_returns_candidates_and_never_picks(client):
    from fhir_clinical_client import Patient

    class Two(Server):
        def search_patients(self, name):
            return [Patient(id="1", family_name="Doe", given_name="Jane", gender="female"),
                    Patient(id="2", family_name="Doe", given_name="Jane", gender="female")]
    api.app.dependency_overrides[api.get_client] = lambda: Two()
    body = client.post("/agent-tools/find_patient", json={"name": "Jane Doe"}).json()
    assert body["outcome"] == "candidates" and body["ambiguous"] is True and len(body["candidates"]) == 2
    assert "patient_id" not in body
