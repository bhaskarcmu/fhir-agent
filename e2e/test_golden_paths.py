"""
End-to-end golden-path contract test for the Phase 2 claims stack.

Runs against a LIVE claims-service (which calls the emulator + triage + FHIR). It self-skips
when the stack is not reachable, so it is safe to collect anywhere but only asserts when the
services are up. Bring the stack up first:

    docker compose --profile phase2 up --build -d
    pytest e2e/

`conftest.py` seeds the demo members' FHIR records automatically — adjudication fails closed,
so without them every approving path would pend on `clinical-safety-unavailable`.

Environment:
    CLAIMS_GATEWAY_URL  claims-service base URL (default http://localhost:8090)
    CLAIMS_API_KEY      Kong API key (omit for local/direct)
"""
from __future__ import annotations

import os

import httpx
import pytest

CLAIMS_URL = os.environ.get("CLAIMS_GATEWAY_URL", "http://localhost:8090").rstrip("/")
API_KEY = os.environ.get("CLAIMS_API_KEY", "")


def _reachable() -> bool:
    try:
        httpx.get(f"{CLAIMS_URL}/actuator/health", timeout=2.0)
        return True
    except Exception:  # noqa: BLE001 - any connectivity failure → skip
        return False


pytestmark = pytest.mark.skipif(
    not _reachable(), reason=f"claims-service not reachable at {CLAIMS_URL}")

_ACTIVE = {"coverageEffective": "2026-01-01", "coverageTermination": "2026-12-31"}
_INACTIVE = {"coverageEffective": "2025-01-01", "coverageTermination": "2026-01-31"}
_BASE = {"memberId": "000000001", "prescriberNpi": "1234567890",
         "dateOfService": "2026-06-01", "daysSupply": 30,
         "priorAuthOnFile": False, "stepTherapyMet": False}


def _claim(**over) -> dict:
    return {**_BASE, **_ACTIVE, **over}


# (claim, expected_outcome, expected_reason_codes)
GOLDEN = [
    (_claim(claimId="E2E-APPROVED", planId="COM-SILVER", rxcui="29046", ndc="51655-999",
            drugName="lisinopril", quantity=30), "APPROVED", []),
    (_claim(claimId="E2E-PENDED", planId="COM-SILVER", rxcui="1991302", ndc="63552-200",
            drugName="semaglutide", quantity=1), "PENDED", ["prior-auth-required"]),
    (_claim(claimId="E2E-ROUTED", planId="COM-SILVER", rxcui="7646", ndc="60505-0065",
            drugName="omeprazole", quantity=180), "ROUTED_FOR_REVIEW", ["quantity-limit-exceeded"]),
    (_claim(claimId="E2E-INACTIVE", planId="COM-SILVER", rxcui="29046", ndc="51655-999",
            drugName="lisinopril", quantity=30, **_INACTIVE), "DENIED", ["coverage-inactive"]),
    (_claim(claimId="E2E-MULTI", planId="EMP-PPO", rxcui="1991302", ndc="63552-200",
            drugName="semaglutide", quantity=8), "DENIED", ["non-formulary"]),
    # Clinical safety: member 000000009 has a penicillin allergy on file; amoxicillin conflicts.
    # This is the one path that proves the reused triage service is actually consulted.
    (_claim(claimId="E2E-SAFETY", memberId="000000009", planId="COM-SILVER", rxcui="723",
            ndc="0093-8675", drugName="amoxicillin", quantity=30),
     "DENIED", ["clinical-safety-high"]),
]


@pytest.mark.parametrize("claim,expected_outcome,expected_codes",
                         GOLDEN, ids=[c["claimId"] for c, _, _ in GOLDEN])
def test_golden_path(claim, expected_outcome, expected_codes):
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["apikey"] = API_KEY
    r = httpx.post(f"{CLAIMS_URL}/claims/adjudicate", json=claim, headers=headers, timeout=30)
    r.raise_for_status()
    d = r.json()

    assert d["outcome"] == expected_outcome
    assert [x["code"] for x in d["reasons"]] == expected_codes
    assert d["decisionId"] == "DEC-" + claim["claimId"]


def test_idempotent_resubmit_is_stable():
    """Re-submitting the same claim returns the same decision (R18.3)."""
    claim = _claim(claimId="E2E-IDEMPOTENT", planId="COM-SILVER", rxcui="29046",
                   ndc="51655-999", drugName="lisinopril", quantity=30)
    first = httpx.post(f"{CLAIMS_URL}/claims/adjudicate", json=claim, timeout=30).json()
    second = httpx.post(f"{CLAIMS_URL}/claims/adjudicate", json=claim, timeout=30).json()
    assert first["decisionId"] == second["decisionId"]
    assert first["outcome"] == second["outcome"]
