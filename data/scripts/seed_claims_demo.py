#!/usr/bin/env python3
"""
Phase 2 claims-adjudication demo driver.

Submits a set of golden-path prescription claims to the claims-service and prints the
deterministic outcome + reasons + pricing for each. Run after the phase2 stack is up:

  docker compose --profile phase2 up --build -d
  python3 data/scripts/seed_claims_demo.py

Environment:
  CLAIMS_GATEWAY_URL  claims-service base URL (default http://localhost:8090;
                      point at the Kong proxy for the gated setup)
  CLAIMS_API_KEY      Kong API key (omit for local/direct)

All member/drug data is synthetic; member 000000001 exists in the emulator's MBRMST.
"""
from __future__ import annotations

import os
import sys
import time

import httpx

CLAIMS_URL = os.environ.get("CLAIMS_GATEWAY_URL", "http://localhost:8090").rstrip("/")
API_KEY = os.environ.get("CLAIMS_API_KEY", "")
# FHIR server — used only to seed the clinical-safety demo patient (member 000000009).
FHIR_BASE = os.environ.get("FHIR_GATEWAY_URL", "http://localhost:8080/fhir").rstrip("/")
FHIR_API_KEY = os.environ.get("FHIR_API_KEY", "")
SAFETY_MEMBER = "000000009"

_ACTIVE = {"coverageEffective": "2026-01-01", "coverageTermination": "2026-12-31"}
_INACTIVE = {"coverageEffective": "2025-01-01", "coverageTermination": "2026-01-31"}
_BASE = {
    "memberId": "000000001", "prescriberNpi": "1234567890",
    "dateOfService": "2026-06-01", "daysSupply": 30,
    "priorAuthOnFile": False, "stepTherapyMet": False,
}


def _claim(**over) -> dict:
    return {**_BASE, **_ACTIVE, **over}


# 5 golden paths (expected outcome in the label).
CLAIMS = [
    ("APPROVED  — on-formulary generic", _claim(
        claimId="DEMO-APPROVED", planId="COM-SILVER", rxcui="29046", ndc="51655-999",
        drugName="lisinopril", quantity=30)),
    ("PENDED    — specialty drug, PA required", _claim(
        claimId="DEMO-PENDED", planId="COM-SILVER", rxcui="1991302", ndc="63552-200",
        drugName="semaglutide", quantity=1)),
    ("ROUTED    — quantity over plan limit", _claim(
        claimId="DEMO-ROUTED", planId="COM-SILVER", rxcui="7646", ndc="60505-0065",
        drugName="omeprazole", quantity=180)),
    ("DENIED    — coverage inactive on date of service", _claim(
        claimId="DEMO-INACTIVE", planId="COM-SILVER", rxcui="29046", ndc="51655-999",
        drugName="lisinopril", quantity=30, **_INACTIVE)),
    ("DENIED    — non-formulary + quantity (multi-reason)", _claim(
        claimId="DEMO-MULTI", planId="EMP-PPO", rxcui="1991302", ndc="63552-200",
        drugName="semaglutide", quantity=8)),
    ("DENIED    — clinical safety (penicillin allergy + amoxicillin)", _claim(
        claimId="DEMO-SAFETY", memberId=SAFETY_MEMBER, planId="COM-SILVER", rxcui="723",
        ndc="0093-8675", drugName="amoxicillin", quantity=30)),
]


def _fhir_headers() -> dict:
    h = {"Content-Type": "application/fhir+json"}
    if FHIR_API_KEY:
        h["apikey"] = FHIR_API_KEY
    return h


def seed_safety_patient(client: httpx.Client) -> None:
    """Seed member 000000009 as a FHIR patient with a penicillin allergy + amoxicillin med,
    so the reused triage service flags the drug-allergy conflict (→ HIGH → clinical DENY).

    Uses PUT with fixed logical ids (idempotent upsert): the Patient's logical id IS the member
    id, so claims-service resolves it with a consistent READ (no search-index race)."""
    pid = f"member-{SAFETY_MEMBER}"   # non-numeric logical id (HAPI requires this for PUT)

    def put(rt, rid, body):
        r = client.put(f"{FHIR_BASE}/{rt}/{rid}", json={**body, "id": rid},
                       headers=_fhir_headers())
        r.raise_for_status()

    put("Patient", pid, {
        "resourceType": "Patient", "identifier": [{"value": SAFETY_MEMBER}],
        "name": [{"family": "Mraz", "given": ["Kristle"]}],
        "gender": "female", "birthDate": "1985-04-12"})
    put("AllergyIntolerance", f"pcn-{pid}", {
        "resourceType": "AllergyIntolerance", "patient": {"reference": f"Patient/{pid}"},
        "criticality": "high", "category": ["medication"],
        "clinicalStatus": {"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
            "code": "active"}]},
        "code": {"coding": [{"system": "http://snomed.info/sct",
                             "code": "764146007", "display": "Penicillin"}]}})
    put("MedicationRequest", f"amox-{pid}", {
        "resourceType": "MedicationRequest", "status": "active", "intent": "order",
        "subject": {"reference": f"Patient/{pid}"},
        "medicationCodeableConcept": {"coding": [{
            "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
            "code": "723", "display": "amoxicillin"}]}})

    # Wait until triage's own inputs (the patient's active meds + allergies) are indexed,
    # so the very first adjudication sees the conflict.
    def _count(q):
        return client.get(f"{FHIR_BASE}/{q}", headers=_fhir_headers()).json().get("total") or 0
    med = alg = 0
    for _ in range(30):
        med = _count(f"MedicationRequest?patient={pid}&status=active&_summary=count")
        alg = _count(f"AllergyIntolerance?patient={pid}&_summary=count")
        if med and alg:
            break
        time.sleep(0.5)
    print(f"seeded clinical-safety patient (Patient/{pid}); triage inputs indexed "
          f"(meds={med}, allergies={alg})")


def main() -> int:
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["apikey"] = API_KEY

    failures = 0
    with httpx.Client(timeout=30) as client:
        try:
            seed_safety_patient(client)
        except httpx.HTTPError as e:
            print(f"(could not seed safety patient: {e} — that path will show LOW risk)")
        print(f"Submitting {len(CLAIMS)} demo claims to {CLAIMS_URL}\n" + "─" * 72)
        for label, claim in CLAIMS:
            try:
                r = client.post(f"{CLAIMS_URL}/claims/adjudicate", json=claim, headers=headers)
                r.raise_for_status()
                d = r.json()
            except httpx.HTTPError as e:
                print(f"✗ {label}\n    request failed: {e}")
                failures += 1
                continue
            reasons = "; ".join(x.get("code", "") for x in d.get("reasons", [])) or "—"
            pricing = d.get("pricing")
            price = ""
            if pricing and pricing.get("paid"):
                price = f" | total ${float(pricing['totalAmount']):.2f}"
            print(f"• {label}")
            print(f"    → outcome={d['outcome']}  reasons=[{reasons}]  decision={d['decisionId']}{price}")
    print("─" * 72)
    if failures:
        print(f"{failures} claim(s) failed to reach the service.")
        return 1
    print("Demo complete. Explain any decision with:\n"
          "  docker compose --profile phase2 run --rm claims-agent --claim '<claim-json>'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
