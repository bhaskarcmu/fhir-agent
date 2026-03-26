#!/usr/bin/env python3
"""
seed_demo.py — Load a minimal deterministic demo dataset into HAPI FHIR.

Creates two patients with known clinical scenarios so the walking-skeleton
demo produces predictable output:

  Patient 1 — Kristle Mraz
    Allergy: Penicillin (HIGH criticality)
    Medication: Amoxicillin (penicillin-class antibiotic)
    Expected triage result: HIGH risk (drug-allergy conflict)

  Patient 2 — John Doe
    No allergies
    Medication: Lisinopril
    Expected triage result: LOW risk

Usage:
  python3 data/scripts/seed_demo.py

Environment variables:
  FHIR_GATEWAY_URL   FHIR server base URL (default: http://localhost:8080/fhir)
  FHIR_API_KEY       Kong API key (omit for local dev)
"""

from __future__ import annotations

import os
import sys

import httpx

FHIR_BASE = os.environ.get("FHIR_GATEWAY_URL", "http://localhost:8080/fhir").rstrip("/")
FHIR_API_KEY = os.environ.get("FHIR_API_KEY", "")

HEADERS: dict[str, str] = {"Content-Type": "application/fhir+json"}
if FHIR_API_KEY:
    HEADERS["apikey"] = FHIR_API_KEY


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _post(resource_type: str, body: dict) -> dict:
    url = f"{FHIR_BASE}/{resource_type}"
    r = httpx.post(url, headers=HEADERS, json=body, timeout=30)
    if r.status_code not in (200, 201):
        print(f"  ✗ POST {resource_type} failed: {r.status_code}")
        print(f"    {r.text[:400]}")
        sys.exit(1)
    created = r.json()
    rid = created.get("id", "?")
    print(f"  ✓ {resource_type}/{rid}")
    return created


def _patient(family: str, given: str, birth_date: str, gender: str) -> dict:
    return {
        "resourceType": "Patient",
        "name": [{"use": "official", "family": family, "given": [given]}],
        "birthDate": birth_date,
        "gender": gender,
    }


def _allergy(patient_id: str, display: str, snomed_code: str, criticality: str) -> dict:
    # Allergies use SNOMED CT, not RxNorm. RxNorm codes identify medications;
    # SNOMED CT codes identify the substance the patient is allergic to.
    return {
        "resourceType": "AllergyIntolerance",
        "patient": {"reference": f"Patient/{patient_id}"},
        "clinicalStatus": {
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
                "code": "active",
            }]
        },
        "verificationStatus": {
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification",
                "code": "confirmed",
            }]
        },
        "criticality": criticality,
        "code": {
            "coding": [{
                "system": "http://snomed.info/sct",
                "code": snomed_code,
                "display": display,
            }],
            "text": display,
        },
    }


def _medication_request(patient_id: str, display: str, rxnorm_code: str) -> dict:
    return {
        "resourceType": "MedicationRequest",
        "status": "active",
        "intent": "order",
        "subject": {"reference": f"Patient/{patient_id}"},
        "medicationCodeableConcept": {
            "coding": [{
                "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                "code": rxnorm_code,
                "display": display,
            }],
            "text": display,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Scenarios
# ─────────────────────────────────────────────────────────────────────────────

def seed_kristle_mraz() -> None:
    """HIGH-risk: penicillin allergy + amoxicillin prescription."""
    print("\n── Patient 1: Kristle Mraz (HIGH risk scenario) ──")

    patient = _post("Patient", _patient("Mraz", "Kristle", "1985-04-12", "female"))
    pid = patient["id"]

    _post("AllergyIntolerance", _allergy(
        patient_id=pid,
        display="Penicillin",
        snomed_code="764146007",   # SNOMED CT: Penicillin
        criticality="high",
    ))

    med = _post("MedicationRequest", _medication_request(
        patient_id=pid,
        display="Amoxicillin 500 MG Oral Capsule",
        rxnorm_code="723",
    ))

    print(f"\n  Query:      Check refill risk for Kristle Mraz")
    print(f"  Expected:   HIGH — penicillin-class conflict")
    print(f"  Patient ID: {pid}")
    print(f"  Med ID:     {med['id']}")


def seed_john_doe() -> None:
    """LOW-risk: no allergies, routine medication."""
    print("\n── Patient 2: John Doe (LOW risk scenario) ──")

    patient = _post("Patient", _patient("Doe", "John", "1970-01-15", "male"))
    pid = patient["id"]

    med = _post("MedicationRequest", _medication_request(
        patient_id=pid,
        display="Lisinopril 10 MG Oral Tablet",
        rxnorm_code="29046",
    ))

    print(f"\n  Query:      Check refill risk for John Doe")
    print(f"  Expected:   LOW — no conflicts found")
    print(f"  Patient ID: {pid}")
    print(f"  Med ID:     {med['id']}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"Seeding demo data into {FHIR_BASE}")
    print("=" * 60)

    seed_kristle_mraz()
    seed_john_doe()

    print("\n" + "=" * 60)
    print("Done. Run the agent:")
    print()
    print('  python3 -m agent.agent \\')
    print('    --query "Check refill risk for Kristle Mraz"')
    print()


if __name__ == "__main__":
    main()
