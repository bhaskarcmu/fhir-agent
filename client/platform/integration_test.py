#!/usr/bin/env python3
"""
Platform integration test for fhir-service.

Audience: Platform engineers (Hat 1) — FHIR infrastructure engineers who build
and maintain fhir-service. Runs directly against the FHIR server with no Kong
gateway, no API key, and no GCP dependency.

Usage:
    # Start fhir-service first:
    #   cd fhir-service && ./mvnw spring-boot:run
    #
    # Then run:
    python3 client/platform/integration_test.py

Environment variables:
    FHIR_BASE_URL   Base URL of the local FHIR server (default: http://localhost:8080/fhir)
                    No trailing slash. No API key — this hits the server directly.
"""

import os
import sys
import json
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Configuration — one env var, no API key
# ---------------------------------------------------------------------------
BASE_URL = os.environ.get("FHIR_BASE_URL", "http://localhost:8080/fhir").rstrip("/")

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"

results = []


def check(name, passed, detail=""):
    status = PASS if passed else FAIL
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    results.append((name, passed))


def request(path, method="GET", body=None):
    """Make a direct FHIR request — no authentication headers."""
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"}
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            body_text = e.read().decode("utf-8", errors="replace")
            body = json.loads(body_text)
        except Exception:
            body = {"error": body_text if "body_text" in dir() else str(e)}
        return e.code, body
    except Exception as e:
        return 0, {"error": str(e)}


# ---------------------------------------------------------------------------
# Test run
# ---------------------------------------------------------------------------
print("\nPlatform integration test")
print(f"  Server: {BASE_URL}")
print()

# ---------------------------------------------------------------------------
# 1. Server reachability
# ---------------------------------------------------------------------------
print("1. Server reachability")
status, body = request("/metadata")
check("GET /metadata returns 200", status == 200, f"got {status}")
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
# 2. Patient CRUD
# ---------------------------------------------------------------------------
print("\n2. Patient CRUD")
patient_payload = {
    "resourceType": "Patient",
    "name": [{"family": "PlatformTest", "given": ["Integration"]}],
    "gender": "unknown",
    "birthDate": "1985-06-15",
}
status, body = request("/Patient", method="POST", body=patient_payload)
check("POST /Patient returns 201", status == 201, f"got {status}")

patient_id = body.get("id", "")
check("Created Patient has an ID", bool(patient_id), f"id={patient_id}")

if patient_id:
    status, body = request(f"/Patient/{patient_id}")
    check("GET /Patient/{id} returns 200", status == 200, f"got {status}")
    retrieved_family = body.get("name", [{}])[0].get("family", "")
    check(
        "Retrieved family name matches",
        retrieved_family == "PlatformTest",
        f"family={retrieved_family}",
    )

    # Clean up — delete the test patient
    request(f"/Patient/{patient_id}", method="DELETE")
else:
    check("GET /Patient/{id} returns 200", False, "skipped — no patient ID")
    check("Retrieved family name matches", False, "skipped")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print()
print("─" * 40)
passed = sum(1 for _, ok in results if ok)
total = len(results)
print(f"  Results: {passed}/{total} passed")
print("─" * 40)

if passed < total:
    failed = [name for name, ok in results if not ok]
    print("\n  Failed tests:")
    for name in failed:
        print(f"    • {name}")
    sys.exit(1)
else:
    print("\n  All tests passed.")
    sys.exit(0)
