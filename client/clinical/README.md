# Clinical Client

Domain-abstracted client for clinical application developers and the MCP agent.

**Audience:** Engineers at healthcare providers, digital health firms, and care
delivery organisations who build workflows and experiences on top of the FHIR
platform. You do not need to understand FHIR to use this client.

This client is intentionally blind to `fhir-service` internals. It speaks in
clinical domain terms — patients, medications, conditions — not FHIR bundles,
search parameters, or HTTP verbs.

---

## Files

| File | Purpose |
|---|---|
| `fhir_client.py` | `FHIRClient` class — domain-abstracted FHIR operations |
| `smoke_test.py` | End-to-end test of the deployed stack via `FHIRClient` |
| `requirements.txt` | Python dependencies (stdlib only for now) |

---

## Prerequisites

### 1. A running deployed stack

The clinical client runs against the **deployed GCP stack** — Kong gateway in
front of `fhir-service`. The stack must be deployed before you can use this client.

If the stack is not yet deployed, see [`gateway/README.md`](../../gateway/README.md)
and [`fhir-service/README.md`](../../fhir-service/README.md).

### 2. An API key

API keys are issued by the platform team. To obtain one:

```bash
# Port-forward the Kong Admin API (requires cluster access)
kubectl port-forward svc/kong-kong-admin 8001:8001 -n kong

# In a separate terminal, provision a key for your application
./gateway/tools/create-key.sh <your-app-name>
```

The key is printed **once only** — store it immediately in a password manager
or as a secret in your environment.

### 3. Environment variables

```bash
export FHIR_GATEWAY_URL="http://localhost:8000"   # Kong proxy URL
export FHIR_API_KEY="your-api-key-here"
```

For the GCP-deployed stack, port-forward the Kong proxy first:
```bash
kubectl port-forward svc/kong-kong-proxy 8000:80 -n kong
```

---

## Using FHIRClient

```python
import os
from client.clinical.fhir_client import FHIRClient

client = FHIRClient(
    gateway_url=os.environ["FHIR_GATEWAY_URL"],
    api_key=os.environ["FHIR_API_KEY"],
)

# Check the platform is reachable
status = client.get_server_status()
print(status)   # {"status": "ok", "fhir_version": "4.0.1"}

# Register a patient
patient_id = client.create_patient(
    family="Smith",
    given="Jane",
    gender="female",
    birth_date="1990-03-15",
)

# Retrieve the patient — returns a typed Patient object, not raw JSON
patient = client.get_patient(patient_id)
print(patient.family_name)    # "Smith"
print(patient.given_name)     # "Jane"
print(patient.birth_date)     # datetime.date(1990, 3, 15)
print(patient.gender)         # "female"
```

### Available methods

| Method | Returns | Description |
|---|---|---|
| `get_server_status()` | `dict` | Check platform reachability and FHIR version |
| `create_patient(family, given, gender, birth_date)` | `str` (patient ID) | Register a new patient |
| `get_patient(patient_id)` | `Patient` | Retrieve a patient by ID |
| `delete_patient(patient_id)` | `None` | Delete a patient (primarily for test cleanup) |

### Coming in Phase 2

| Method | Description |
|---|---|
| `get_medications(patient_id)` | Active medication requests |
| `get_conditions(patient_id)` | Active diagnoses |
| `get_allergies(patient_id)` | Allergy intolerances |
| `get_appointments(patient_id)` | Upcoming appointments |

### The Patient dataclass

```python
@dataclass
class Patient:
    id: str
    family_name: str
    given_name: str
    gender: str
    birth_date: Optional[date]   # None if not recorded
```

---

## Running the smoke test

The smoke test validates the full stack end-to-end: authentication, server
reachability, patient CRUD, and rate limiting.

```bash
# From the repository root
FHIR_GATEWAY_URL=http://localhost:8000 \
FHIR_API_KEY=<your-key> \
python3 client/clinical/smoke_test.py
```

Expected output:
```
Clinical smoke test
  Gateway : http://localhost:8000
  API Key : set (abcd1234...)

1. Authentication
  [PASS] No API key returns 401
  [PASS] Wrong API key returns 401

2. Server reachability
  [PASS] Server is reachable and healthy — status=ok
  [PASS] FHIR version is R4 — fhir_version=4.0.1

3. Patient workflow
  [PASS] Create patient returns an ID — id=1102
  [PASS] Retrieved patient has correct family name — family_name=ClinicalTest
  [PASS] Retrieved patient has correct given name — given_name=Smoke
  [PASS] Retrieved patient has correct birth date — birth_date=1992-07-04
  [PASS] Retrieved patient has correct gender — gender=unknown

4. Rate limiting
  [PASS] X-RateLimit-Limit-Second header present — value=10
  [PASS] X-RateLimit-Remaining-Day header present — remaining=995

────────────────────────────────────────────────────────────
  Results: 11/11 passed
────────────────────────────────────────────────────────────

  All tests passed. Stack is operational.
```

---

## Error handling

`FHIRClient` raises typed exceptions — never raw HTTP errors:

```python
from client.clinical.fhir_client import FHIRClient, AuthenticationError, NotFoundError, FHIRClientError

try:
    patient = client.get_patient("nonexistent-id")
except NotFoundError:
    print("Patient not found")
except AuthenticationError:
    print("Invalid API key — check FHIR_API_KEY")
except FHIRClientError as e:
    print(f"Unexpected error: {e} (HTTP {e.status_code})")
```

---

## Design notes

### Why `urllib` instead of `requests` or `httpx`?

`urllib` ships with every CPython installation, so a clinical developer can
run `smoke_test.py` immediately after cloning the repo — no `pip install`, no
virtualenv, no version conflicts. The FHIR calls made here are simple
request/response interactions (no streaming, no async, no HTTP/2) that fit
comfortably within `urllib`'s feature set. When Phase 2 introduces async
workflows or OAuth token refresh, the client will migrate to `httpx`; the
swap is isolated to `fhir_client.py` and invisible to callers.

---

## What this client does NOT expose

By design, the following FHIR concepts are hidden inside `fhir_client.py`
and never appear in clinical application code:

- FHIR resource types (`Patient`, `Bundle`, `CapabilityStatement`)
- FHIR search parameters (`?patient=`, `?clinical-status=active`)
- HTTP verbs and status codes
- JSON parsing of FHIR responses
- Kong gateway configuration or API key headers
