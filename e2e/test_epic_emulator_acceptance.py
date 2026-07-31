"""
Phase 4 M5 acceptance case (PRD FR9/G5): the existing prescription-refill-risk-triage scenario,
re-pointed at `epic-emulator` instead of `fhir-service` directly, must produce the same clinical
outcome. Runs against a LIVE `fhir-service` and `epic-emulator`. Self-skips when either is not
reachable, so it is safe to collect anywhere but only asserts when the stack is up.

Bring the stack up first:

    # 1. fhir-service on :8080 (already up in most dev environments; otherwise see fhir-service/README.md)

    # 2. epic-emulator on :8092, pointed at fhir-service, with the fixture test client registered
    #    (decision E8: dev-simple, config-only registration -- these env vars ARE the registration)
    JWK=$(python3 -c "import json; print(json.dumps(json.load(open('e2e/fixtures/epic_emulator_test_client_public_jwk.json'))))")
    EPIC_AUTH_CLIENTS_0_CLIENT_ID=e2e-acceptance-test-client \\
    EPIC_AUTH_CLIENTS_0_JWK="$JWK" \\
    java -Dfhir.base-url=http://localhost:8080 -jar epic-emulator/target/epic-emulator-0.1.0.jar

    # 3. pytest e2e/test_epic_emulator_acceptance.py

This test spawns its own two `triage-service` subprocesses on ephemeral ports (one pointed
directly at fhir-service, one via epic-emulator) rather than assuming docker-compose already
runs two simultaneous instances -- there is no such wiring (design.md §8 explicitly does not
require a compose profile for Phase 4's acceptance bar). Only fhir-service and epic-emulator are
treated as pre-existing "the stack."

The bearer token for the epic-emulator-routed instance is obtained through the *real* SMART
Backend Services flow (a signed JWT client assertion, e2e/fixtures/epic_emulator_test_client_*)
and passed to triage-service via FHIR_API_KEY, which triage-service already sends as an `apikey`
header -- accepted by epic-emulator's auth gate as a fallback to `Authorization: Bearer` (decision
E15). This is what makes FR9 achievable with zero code changes to triage-service or client/clinical.

Environment:
    FHIR_GATEWAY_URL    fhir-service base URL, INCLUDING /fhir (default http://localhost:8080/fhir)
    EPIC_EMULATOR_URL   epic-emulator base URL, NOT including /fhir (default http://localhost:8092)
"""
from __future__ import annotations

import importlib.util
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization

_REPO_ROOT = Path(__file__).resolve().parents[1]
FHIR_URL = os.environ.get("FHIR_GATEWAY_URL", "http://localhost:8080/fhir").rstrip("/")
EMULATOR_URL = os.environ.get("EPIC_EMULATOR_URL", "http://localhost:8092").rstrip("/")

_CLIENT_ID = "e2e-acceptance-test-client"
_TOKEN_ENDPOINT = f"{EMULATOR_URL}/oauth2/token"
_PRIVATE_KEY_PATH = _REPO_ROOT / "e2e" / "fixtures" / "epic_emulator_test_client_private_key.pem"


def _reachable(url: str, timeout: float = 2.0) -> bool:
    try:
        httpx.get(url, timeout=timeout)
        return True
    except Exception:  # noqa: BLE001 - any connectivity failure -> skip
        return False


pytestmark = pytest.mark.skipif(
    not (_reachable(f"{FHIR_URL}/metadata") and _reachable(f"{EMULATOR_URL}/actuator/health")),
    reason=f"fhir-service ({FHIR_URL}) or epic-emulator ({EMULATOR_URL}) not reachable",
)

# Reuse the committed Phase 1 demo seeder (one reproducible generator per fixture, same
# import-by-path convention conftest.py already uses for seed_claims_demo.py) rather than
# restating the drug-allergy-conflict scenario here.
_SEEDER_PATH = _REPO_ROOT / "data" / "scripts" / "seed_demo.py"
_spec = importlib.util.spec_from_file_location("seed_demo", _SEEDER_PATH)
_seeder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_seeder)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_ready(url: str, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _reachable(url, timeout=1.0):
            return True
        time.sleep(0.5)
    return False


def _spawn_triage(fhir_gateway_url: str, api_key: str | None) -> tuple[subprocess.Popen, str]:
    port = _free_port()
    env = dict(os.environ)
    env["FHIR_GATEWAY_URL"] = fhir_gateway_url
    env["FHIR_API_KEY"] = api_key or ""
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "triage.main:app",
         "--app-dir", str(_REPO_ROOT / "triage-service" / "src"), "--port", str(port)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    if not _wait_ready(f"{base}/docs"):
        proc.terminate()
        pytest.skip(f"triage-service did not become ready on {base}")
    return proc, base


@pytest.fixture(scope="session", autouse=True)
def seed_fhir_patients() -> dict[str, str]:
    """Seeds the two demo patients directly into fhir-service. Session-scoped; not idempotent
    (seed_demo.py POSTs with server-assigned ids), so this fixture seeds once per test run and
    both triage-service instances query the same freshly-created patient ids."""
    original_base = _seeder.FHIR_BASE
    _seeder.FHIR_BASE = FHIR_URL
    try:
        try:
            kristle_id = _seeder.seed_kristle_mraz()
            john_id = _seeder.seed_john_doe()
        except SystemExit as exc:  # seed_demo.py sys.exit(1)s on a failed POST
            pytest.skip(f"could not seed fhir-service fixtures: {exc}")
    finally:
        _seeder.FHIR_BASE = original_base
    return {"kristle_mraz": kristle_id, "john_doe": john_id}


def _fetch_access_token() -> str:
    private_key = serialization.load_pem_private_key(
        _PRIVATE_KEY_PATH.read_bytes(), password=None)
    now = int(time.time())
    claims = {
        "iss": _CLIENT_ID, "sub": _CLIENT_ID, "aud": _TOKEN_ENDPOINT,
        "jti": str(uuid.uuid4()), "iat": now, "exp": now + 120,
    }
    assertion = pyjwt.encode(claims, private_key, algorithm="RS384", headers={"kid": _CLIENT_ID})
    resp = httpx.post(_TOKEN_ENDPOINT, data={
        "grant_type": "client_credentials",
        "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
        "client_assertion": assertion,
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()["access_token"]


@pytest.fixture(scope="session")
def triage_direct(seed_fhir_patients):
    proc, base = _spawn_triage(FHIR_URL, api_key=None)
    yield base
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="session")
def triage_via_emulator(seed_fhir_patients):
    token = _fetch_access_token()
    proc, base = _spawn_triage(f"{EMULATOR_URL}/fhir", api_key=token)
    yield base
    proc.terminate()
    proc.wait(timeout=10)


@pytest.mark.parametrize(
    "patient_key,expected_risk",
    [("kristle_mraz", "HIGH"), ("john_doe", "LOW")],
)
def test_same_clinical_outcome_direct_vs_via_epic_emulator(
    seed_fhir_patients, triage_direct, triage_via_emulator, patient_key, expected_risk
):
    patient_id = seed_fhir_patients[patient_key]

    direct = httpx.post(f"{triage_direct}/triage/refill-risk",
                         json={"patient_id": patient_id}, timeout=30)
    direct.raise_for_status()
    via_emulator = httpx.post(f"{triage_via_emulator}/triage/refill-risk",
                               json={"patient_id": patient_id}, timeout=30)
    via_emulator.raise_for_status()

    direct_code = direct.json()["prediction"][0]["outcome"]["coding"][0]["code"]
    emulator_code = via_emulator.json()["prediction"][0]["outcome"]["coding"][0]["code"]

    assert direct_code == expected_risk
    assert emulator_code == expected_risk
    assert emulator_code == direct_code
