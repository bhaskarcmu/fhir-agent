#!/usr/bin/env python3
"""
Clinical smoke test for the fhir-agent platform.

Audience: Clinical application developers (Hat 2) — engineers building
workflows and experiences on top of the deployed FHIR platform. Also used
to validate the full stack after a GCP deployment.

This test uses FHIRClient exclusively. It reads like a clinical workflow,
not an HTTP test. No FHIR mechanics appear here.

Usage:
    export FHIR_GATEWAY_URL="http://localhost:8000"
    export FHIR_API_KEY="your-api-key"
    python3 client/clinical/smoke_test.py

Prerequisites:
    Kong proxy port-forwarded on port 8000:
        kubectl port-forward svc/kong-kong-proxy 8000:80 -n kong

    A valid API key (obtain via):
        kubectl port-forward svc/kong-kong-admin 8001:8001 -n kong
        ./gateway/tools/create-key.sh test-client
"""

import os
import sys
import urllib.request
import urllib.error

# FHIRClient lives in the same directory — import directly.
# When this becomes a proper package, this import path will be updated.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from client.clinical.fhir_client import FHIRClient, AuthenticationError, FHIRClientError

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GATEWAY_URL = os.environ.get("FHIR_GATEWAY_URL", "http://localhost:8000")
API_KEY     = os.environ.get("FHIR_API_KEY", "")

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"

results = []
_patient_id = None   # track created patient for cleanup


def check(name, passed, detail=""):
    status = PASS if passed else FAIL
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    results.append((name, passed))


# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------
print("\nClinical smoke test")
print(f"  Gateway : {GATEWAY_URL}")
print(f"  API Key : {'set (' + API_KEY[:8] + '...)' if API_KEY else 'NOT SET'}")
print()

if not API_KEY:
    print(f"  [{FAIL}] FHIR_API_KEY is not set.")
    print("  Obtain a key:  ./gateway/tools/create-key.sh test-client")
    print("  Then:          export FHIR_API_KEY=<printed-key>")
    sys.exit(1)

client = FHIRClient(gateway_url=GATEWAY_URL, api_key=API_KEY)

# ---------------------------------------------------------------------------
# Test 1: Authentication — gateway rejects requests without a valid key
# ---------------------------------------------------------------------------
print("1. Authentication")

# Test unauthenticated directly — FHIRClient always sends the key, so we
# bypass it here for this one check only.
try:
    url = f"{GATEWAY_URL}/fhir/metadata"
    req = urllib.request.Request(url)   # no apikey header
    urllib.request.urlopen(req, timeout=10)
    check("No API key returns 401", False, "expected 401 but got 200")
except urllib.error.HTTPError as e:
    check("No API key returns 401", e.code == 401, f"got {e.code}")
except Exception as e:
    check("No API key returns 401", False, str(e))

# Test wrong key via FHIRClient with a bad key
bad_client = FHIRClient(gateway_url=GATEWAY_URL, api_key="wrong-key-000000000000")
try:
    bad_client.get_server_status()
    check("Wrong API key returns 401", False, "expected AuthenticationError")
except AuthenticationError:
    check("Wrong API key returns 401", True)
except Exception as e:
    check("Wrong API key returns 401", False, str(e))

# ---------------------------------------------------------------------------
# Test 2: Server reachability
# ---------------------------------------------------------------------------
print("\n2. Server reachability")
try:
    status = client.get_server_status()
    check("Server is reachable and healthy", status["status"] == "ok",
          f"status={status['status']}")
    check("FHIR version is R4",
          status["fhir_version"].startswith("4."),
          f"fhir_version={status['fhir_version']}")
except FHIRClientError as e:
    check("Server is reachable and healthy", False, str(e))
    check("FHIR version is R4", False, "skipped")

# ---------------------------------------------------------------------------
# Test 3: Patient workflow — create, retrieve, verify
# ---------------------------------------------------------------------------
print("\n3. Patient workflow")
try:
    _patient_id = client.create_patient(
        family="ClinicalTest",
        given="Smoke",
        gender="unknown",
        birth_date="1992-07-04",
    )
    check("Create patient returns an ID", bool(_patient_id), f"id={_patient_id}")
except FHIRClientError as e:
    check("Create patient returns an ID", False, str(e))
    _patient_id = None

if _patient_id:
    try:
        patient = client.get_patient(_patient_id)
        check("Retrieved patient has correct family name",
              patient.family_name == "ClinicalTest",
              f"family_name={patient.family_name}")
        check("Retrieved patient has correct given name",
              patient.given_name == "Smoke",
              f"given_name={patient.given_name}")
        check("Retrieved patient has correct birth date",
              str(patient.birth_date) == "1992-07-04",
              f"birth_date={patient.birth_date}")
        check("Retrieved patient has correct gender",
              patient.gender == "unknown",
              f"gender={patient.gender}")
    except FHIRClientError as e:
        check("Retrieved patient has correct family name", False, str(e))
        check("Retrieved patient has correct given name", False, "skipped")
        check("Retrieved patient has correct birth date", False, "skipped")
        check("Retrieved patient has correct gender", False, "skipped")
else:
    for name in ["family name", "given name", "birth date", "gender"]:
        check(f"Retrieved patient has correct {name}", False, "skipped — no patient ID")

# ---------------------------------------------------------------------------
# Test 4: Rate limiting — Kong plugin is active
# ---------------------------------------------------------------------------
print("\n4. Rate limiting")
try:
    url = f"{GATEWAY_URL}/fhir/metadata"
    req = urllib.request.Request(url, headers={"apikey": API_KEY})
    with urllib.request.urlopen(req, timeout=10) as resp:
        headers = {k.lower(): v for k, v in resp.headers.items()}
        check("X-RateLimit-Limit-Second header present",
              "x-ratelimit-limit-second" in headers,
              f"value={headers.get('x-ratelimit-limit-second', 'missing')}")
        check("X-RateLimit-Remaining-Day header present",
              "x-ratelimit-remaining-day" in headers,
              f"remaining={headers.get('x-ratelimit-remaining-day', 'missing')}")
except Exception as e:
    check("X-RateLimit-Limit-Second header present", False, str(e))
    check("X-RateLimit-Remaining-Day header present", False, "skipped")

# ---------------------------------------------------------------------------
# Cleanup — delete the test patient
# ---------------------------------------------------------------------------
if _patient_id:
    try:
        client.delete_patient(_patient_id)
    except FHIRClientError:
        pass   # cleanup failure is not a test failure

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print()
print("─" * 60)
passed = sum(1 for _, ok in results if ok)
total  = len(results)
print(f"  Results: {passed}/{total} passed")
print("─" * 60)

if passed < total:
    failed = [name for name, ok in results if not ok]
    print("\n  Failed tests:")
    for name in failed:
        print(f"    • {name}")
    sys.exit(1)
else:
    print("\n  All tests passed. Stack is operational.")
    sys.exit(0)
