#!/usr/bin/env python3
"""
End-to-end smoke test for the fhir-service stack.

Tests the full path: client → Kong (auth + rate-limit) → fhir-service → Neon

Usage:
    export FHIR_GATEWAY_URL="http://localhost:8000"
    export FHIR_API_KEY="your-api-key"
    python3 fhir-service/tests/smoke_test.py

Prerequisites:
    Kong proxy port-forwarded on port 8000:
        kubectl port-forward svc/kong-kong-proxy 8000:80 -n kong

    Kong Admin API port-forwarded on port 8001 (for key provisioning):
        kubectl port-forward svc/kong-kong-admin 8001:8001 -n kong

Environment variables:
    FHIR_GATEWAY_URL   Base URL of the Kong proxy (default: http://localhost:8000)
    FHIR_API_KEY       Valid API key for the test-client consumer (required)
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_URL = os.environ.get("FHIR_GATEWAY_URL", "http://localhost:8000").rstrip("/")
API_KEY  = os.environ.get("FHIR_API_KEY", "")

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"

results = []


def check(name, passed, detail=""):
    status = PASS if passed else FAIL
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    results.append((name, passed))


def request(path, key=None, method="GET", body=None):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/fhir+json"}
    if key:
        headers["apikey"] = key
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------
print("\nfhir-service smoke test")
print(f"  Gateway : {BASE_URL}")
print(f"  API Key : {'set (' + API_KEY[:8] + '...)' if API_KEY else 'NOT SET'}")
print()

if not API_KEY:
    print(f"  [{FAIL}] FHIR_API_KEY environment variable is not set.")
    print("  Run: export FHIR_API_KEY=<your-key>")
    print("  Get a key: ./gateway/tools/create-key.sh test-client")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Test 1: Unauthenticated request → 401
# ---------------------------------------------------------------------------
print("1. Authentication")
status, _ = request("/fhir/metadata")
check("No API key returns 401", status == 401, f"got {status}")

# ---------------------------------------------------------------------------
# Test 2: Wrong key → 401
# ---------------------------------------------------------------------------
status, _ = request("/fhir/metadata", key="wrong-key-000000000000")
check("Wrong API key returns 401", status == 401, f"got {status}")

# ---------------------------------------------------------------------------
# Test 3: Valid key → 200 + CapabilityStatement
# ---------------------------------------------------------------------------
print("\n2. FHIR server reachability")
status, body = request("/fhir/metadata", key=API_KEY)
check("Valid key returns 200", status == 200, f"got {status}")
check(
    "Response is a FHIR CapabilityStatement",
    body.get("resourceType") == "CapabilityStatement",
    f"resourceType={body.get('resourceType')}",
)
check(
    "FHIR version is R4",
    body.get("fhirVersion", "").startswith("4."),
    f"fhirVersion={body.get('fhirVersion')}",
)

# ---------------------------------------------------------------------------
# Test 4: Create a Patient
# ---------------------------------------------------------------------------
print("\n3. FHIR CRUD — Patient")
patient = {
    "resourceType": "Patient",
    "name": [{"family": "SmokeTest", "given": ["Automated"]}],
    "gender": "unknown",
    "birthDate": "1990-01-01",
}
status, body = request("/fhir/Patient", key=API_KEY, method="POST", body=patient)
check("POST /fhir/Patient returns 201", status == 201, f"got {status}")

patient_id = body.get("id", "")
check("Created Patient has an ID", bool(patient_id), f"id={patient_id}")

# ---------------------------------------------------------------------------
# Test 5: Retrieve the Patient
# ---------------------------------------------------------------------------
if patient_id:
    status, body = request(f"/fhir/Patient/{patient_id}", key=API_KEY)
    check("GET /fhir/Patient/{id} returns 200", status == 200, f"got {status}")
    check(
        "Retrieved Patient matches created family name",
        body.get("name", [{}])[0].get("family") == "SmokeTest",
        f"family={body.get('name', [{}])[0].get('family')}",
    )
else:
    check("GET /fhir/Patient/{id} returns 200", False, "skipped — no patient ID")
    check("Retrieved Patient matches created family name", False, "skipped")

# ---------------------------------------------------------------------------
# Test 6: Rate limit headers present
# ---------------------------------------------------------------------------
print("\n4. Rate limiting")
status, _ = request("/fhir/metadata", key=API_KEY)

# Re-request with header inspection via urllib
url = f"{BASE_URL}/fhir/metadata"
req = urllib.request.Request(url, headers={"apikey": API_KEY})
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        headers = {k.lower(): v for k, v in resp.headers.items()}
        has_limit  = "x-ratelimit-limit-second" in headers
        has_remain = "x-ratelimit-remaining-second" in headers
        limit_val  = headers.get("x-ratelimit-limit-second", "?")
        remain_val = headers.get("x-ratelimit-remaining-day", "?")
except Exception as e:
    has_limit = has_remain = False
    limit_val = remain_val = f"error: {e}"

check("X-RateLimit-Limit-Second header present", has_limit, f"value={limit_val}")
check("X-RateLimit-Remaining-Day header present", has_remain, f"remaining={remain_val}")

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
    print(f"\n  Failed tests:")
    for name in failed:
        print(f"    • {name}")
    sys.exit(1)
else:
    print("\n  All tests passed. Stack is operational.")
    sys.exit(0)
