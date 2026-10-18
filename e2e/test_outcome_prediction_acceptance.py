"""
Phase 8 M9 acceptance case (prd.md §9 criterion 9): the hospitalization-risk path, live, under the
`phase8` compose profile — the FHIR server, the scoring service with the real M2 artifact, the
agent on the self-hosted model. The three demo beats of docs/demo-guide.md §5b:

1. A seeded Synthea patient scored through the API — a valid R4 RiskAssessment whose `basis`
   resolves to that patient's own encounters, conditions and claims, none dated after `as_of`.
2. The same patient through the agent — every line of the reply traced to the RiskAssessment.
3. An encounter added after `as_of` doesn't move the score (and does count once `as_of` passes it).

Like the rest of Phase 8's tests (decisions.md O44), this suite **brings up what's missing and
fails if it can't**, rather than skipping: it starts `fhir` and `outcome-prediction` with docker
compose, seeds the pinned demo patients, and starts Ollama in a container if none is reachable —
and removes only what it started. The one thing it can't create is the trained model artifact
(it needs MEPS); without one it fails and says how to train it.

    pytest e2e/test_outcome_prediction_acceptance.py -v

Environment:
    FHIR_GATEWAY_URL         FHIR base URL, including /fhir (default http://localhost:8080/fhir)
    OUTCOME_PREDICTION_URL   scoring service (default http://localhost:8005)
    OLLAMA_HOST              default http://localhost:11434; model OLLAMA_MODEL (llama3.2:1b)
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parents[1]
FHIR_URL = os.environ.get("FHIR_GATEWAY_URL", "http://localhost:8080/fhir").rstrip("/")
SERVICE_URL = os.environ.get("OUTCOME_PREDICTION_URL", "http://localhost:8005").rstrip("/")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:1b")
OLLAMA_IMAGE = "ollama/ollama:0.6.5"
AS_OF = "2024-12-31"                     # the end of the pinned Synthea run (etl/synthea.py RUN)
DEMO_PATIENT = "e7149b17-d845-b43b-95fb-88a93a213601"     # Synthea ID of the richest living demo adult
AGENT_ATTEMPTS = 6                       # the 1B model completes ~60% of turns; every attempt is checked
NO_CACHE = {"Cache-Control": "no-cache"}


# ── bring up what's missing (O44) ────────────────────────────────────────────────────

def _up(url: str) -> bool:
    try:
        return httpx.get(url, timeout=5).status_code == 200
    except httpx.HTTPError:
        return False


def _wait(url: str, what: str, seconds: int = 240) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if _up(url):
            return
        time.sleep(3)
    pytest.fail(f"{what} did not become ready at {url} within {seconds}s", pytrace=False)


def _compose(*args: str) -> None:
    result = subprocess.run(["docker", "compose", "--profile", "phase8", *args], cwd=REPO,
                            capture_output=True, text=True)
    if result.returncode:
        pytest.fail(f"docker compose {' '.join(args)} failed:\n{result.stderr[-2000:]}", pytrace=False)


@pytest.fixture(scope="session", autouse=True)
def seed_fhir_patients():
    """Overrides e2e/conftest.py's claims-demo seeder for this module: Phase 8 seeds its own
    patients below, after making sure the FHIR server is up (that seeder would skip first)."""
    yield


@pytest.fixture(scope="module")
def stack():
    started = []
    if not _up(f"{FHIR_URL}/metadata"):
        _compose("up", "-d", "fhir")
        started.append("fhir")
        _wait(f"{FHIR_URL}/metadata", "the FHIR server")
    if not _up(f"{SERVICE_URL}/health"):
        models = REPO / "outcome-prediction-service" / "models"
        if not any(models.glob("gbm-meps25-v1-*")):
            pytest.fail("no trained artifact in outcome-prediction-service/models/ — train one first: "
                        "python -m outcome_prediction.meps.download && python -m outcome_prediction.meps.build "
                        "&& python -m outcome_prediction.model.train", pytrace=False)
        _compose("up", "-d", "--build", "outcome-prediction")
        started.append("outcome-prediction")
        _wait(f"{SERVICE_URL}/health", "the scoring service")
    yield
    if started:
        _compose("rm", "-sf", *started)


@pytest.fixture(scope="module")
def patients(stack) -> dict[str, dict]:
    from outcome_prediction.etl.synthea import seed
    return {p["synthea_id"]: p for p in seed(FHIR_URL)}


@pytest.fixture(scope="module")
def patient(patients) -> dict:
    return patients[DEMO_PATIENT]


@pytest.fixture(scope="module")
def ollama():
    container = None
    if not _up(f"{OLLAMA_HOST}/api/tags"):
        container = "phase8-e2e-ollama"
        port = OLLAMA_HOST.rsplit(":", 1)[-1]
        subprocess.run(["docker", "run", "-d", "--rm", "--name", container, "-p", f"{port}:11434",
                        "-v", "phase8-ollama-models:/root/.ollama", OLLAMA_IMAGE], check=True, capture_output=True)
        _wait(f"{OLLAMA_HOST}/api/tags", "Ollama")
    names = {m["name"] for m in httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=10).json().get("models", [])}
    if OLLAMA_MODEL not in names:
        with httpx.stream("POST", f"{OLLAMA_HOST}/api/pull", json={"name": OLLAMA_MODEL}, timeout=900) as r:
            r.raise_for_status()
            for _ in r.iter_lines():
                pass
    yield
    if container:
        subprocess.run(["docker", "stop", container], capture_output=True)


def _score(patient_id: str, as_of: str = AS_OF) -> dict:
    r = httpx.post(f"{SERVICE_URL}/risk/hospitalization-12m", json={"patient_id": patient_id, "as_of": as_of},
                   timeout=120)
    assert r.status_code == 200, r.text
    return r.json()


def _comparable(ra: dict) -> dict:
    """Everything that is the estimate: all but the resource id and its generated narrative."""
    return {k: v for k, v in ra.items() if k not in ("id", "text")}


# ── beat 1: a seeded patient through the API ─────────────────────────────────────────

def test_beat_1_a_seeded_patient_gets_a_valid_risk_assessment(patient):
    ra = _score(patient["id"])
    outcome = httpx.post(f"{FHIR_URL}/RiskAssessment/$validate", json=ra, timeout=60,
                         headers={"Content-Type": "application/fhir+json"}).json()
    problems = [i for i in outcome["issue"] if i["severity"] in ("error", "fatal", "warning")]
    assert problems == [], problems
    p = ra["prediction"][0]
    assert ra["subject"] == {"reference": f"Patient/{patient['id']}"} and ra["occurrenceDateTime"] == AS_OF
    assert p["outcome"]["coding"][0]["code"] == "32485007" and 0 < p["probabilityDecimal"] < 1
    assert "qualitativeRisk" not in p


def test_beat_1_basis_resolves_to_this_patients_own_records_before_as_of(patient):
    ra = _score(patient["id"])
    refs = [b["reference"] for b in ra["basis"]]
    kinds = {r.split("/")[0] for r in refs}
    assert {"Encounter", "Condition"} <= kinds and kinds <= {"Encounter", "Condition", "ExplanationOfBenefit"}
    for ref in refs:
        r = httpx.get(f"{FHIR_URL}/{ref}", timeout=30)
        assert r.status_code == 200, ref
        res = r.json()
        owner = (res.get("subject") or res.get("patient") or {}).get("reference")
        assert owner == f"Patient/{patient['id']}", (ref, owner)
        when = ((res.get("period") or {}).get("start") or res.get("onsetDateTime")
                or (res.get("billablePeriod") or {}).get("start") or "")
        assert when[:10] <= AS_OF, (ref, when)


def test_beat_1_no_estimate_for_a_patient_who_had_died(patients):
    dead = next(p for p in patients.values() if p["deceased"])
    r = httpx.post(f"{SERVICE_URL}/risk/hospitalization-12m", json={"patient_id": dead["id"], "as_of": AS_OF},
                   timeout=120)
    assert r.status_code == 422 and "not an adult alive" in r.json()["detail"]


# ── beat 2: the same patient through the agent ───────────────────────────────────────

def _trace(reply: str, ra: dict) -> list[tuple[str, str]]:
    """Map every line of the agent's reply to the part of the RiskAssessment it states."""
    from outcome_prediction_agent import explain
    p = ra["prediction"][0]
    ext = lambda name: explain._ext(p["extension"], name)  # noqa: E731
    sources = [
        ("prediction.probabilityDecimal + whenPeriod",
         lambda line: explain._pct(p["probabilityDecimal"]) in line and p["whenPeriod"]["start"] in line
         and p["whenPeriod"]["end"] in line),
        ("extension risk-percentile", lambda line: f": {ext('risk-percentile')[0]}." in line),
        ("extension comparison-probability", lambda line: explain._pct(ext("comparison-probability")[0]) in line),
        ("prediction.rationale", lambda line: line == p["rationale"]),
        ("extension input-warning",
         lambda line: line.startswith("Notes from the service")
         and all(w in line for w in explain._ext(ra.get("extension", []), "input-warning"))),
        ("method + note", lambda line: ra["method"]["coding"][0]["code"] in line and ra["note"][0]["text"] in line),
        ("fixed notice (no numbers)", lambda line: line in (explain.NOTICE_ADJUST, explain.NOTICE_BAND,
                                                            explain.NOTICE_POPULATION)),
    ]
    traced = []
    for line in reply.splitlines():
        source = next((name for name, matches in sources if matches(line)), None)
        assert source, f"untraceable line: {line!r}"
        traced.append((line, source))
    return traced


def test_beat_2_the_agent_narrates_only_the_risk_assessment(patient, ollama):
    from agent_platform.providers import OpenAICompatibleProvider
    from outcome_prediction_agent import explain
    from outcome_prediction_agent.agent import run_query
    from outcome_prediction_agent.explain import Outcome
    from outcome_prediction_agent.service import ServiceTools

    llm = OpenAICompatibleProvider(base_url=f"{OLLAMA_HOST}/v1")
    question = f"What is the hospitalization risk for patient {patient['id']} as of {AS_OF}?"
    outcomes = []
    for _ in range(AGENT_ATTEMPTS):
        reply = run_query(llm, OLLAMA_MODEL, question, ServiceTools(SERVICE_URL))
        outcomes.append(reply.outcome.value)
        assert explain.grounded(reply.text, reply.evidence) == [], reply.text      # every attempt, not just the last
        if reply.outcome is Outcome.ESTIMATE:
            break
    assert reply.outcome is Outcome.ESTIMATE, f"no estimate in {AGENT_ATTEMPTS} attempts: {outcomes}"
    ra = _score(patient["id"])
    agent_ra = next(e["result"]["risk_assessment"] for e in reply.evidence if e["tool"] == "get_hospitalization_risk")
    assert _comparable(agent_ra) == _comparable(ra)                   # the agent saw exactly what the API returns
    traced = _trace(reply.text, ra)
    assert {s for _, s in traced} >= {"prediction.probabilityDecimal + whenPeriod", "prediction.rationale",
                                      "method + note"}


# ── beat 3: an encounter after as_of doesn't move the score ──────────────────────────

def test_beat_3_a_record_after_as_of_changes_nothing(patient):
    before = _score(patient["id"])
    stay = {"resourceType": "Encounter", "status": "finished",
            "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "IMP"},
            "type": [{"coding": [{"system": "http://snomed.info/sct", "code": "32485007",
                                  "display": "Hospital admission (procedure)"}]}],
            "subject": {"reference": f"Patient/{patient['id']}"},
            "period": {"start": "2025-03-01T09:00:00+00:00", "end": "2025-03-06T09:00:00+00:00"}}
    created = httpx.post(f"{FHIR_URL}/Encounter", json=stay, timeout=60,
                         headers={"Content-Type": "application/fhir+json"})
    assert created.status_code == 201, created.text
    new_ref = f"Encounter/{created.json()['id']}"
    try:
        after = _score(patient["id"])
        assert _comparable(after) == _comparable(before)                      # not one field moves
        assert new_ref not in [b["reference"] for b in after["basis"]]
        # The server really has it: scored as of a date after the stay, it counts.
        later = _score(patient["id"], "2025-12-31")
        assert new_ref in [b["reference"] for b in later["basis"]]
    finally:
        httpx.delete(f"{FHIR_URL}/{new_ref}", timeout=60)
