# Triage Service

Stateless FastAPI microservice that evaluates drug-allergy conflict risk for a
patient. Fetches clinical data via `fhir-clinical-client`, runs a rule engine,
and returns a FHIR `RiskAssessment` resource.

---

## Running locally

```bash
pip install -e client/clinical
pip install -e triage-service

FHIR_GATEWAY_URL=http://localhost:8080/fhir \
uvicorn triage.main:app --port 8001 --reload
```

API docs (Swagger UI): http://localhost:8001/docs

---

## API

### `POST /triage/refill-risk`

Request:
```json
{ "patient_id": "544f37bb-e6aa-87d4-f813-0745fe0e524f" }
```

Returns a FHIR RiskAssessment with risk level HIGH/MODERATE/LOW,
clinical rationale, and basis references to the triggering resources.

### `GET /health`

```json
{ "status": "ok", "version": "0.1.0" }
```

---

## Rules

| Rule | Trigger | Risk |
|---|---|---|
| Penicillin conflict | Active penicillin-family medication + penicillin allergy | HIGH |
| Duplicate therapeutic class | Two or more medications in the same class | MODERATE |
| High-criticality allergy | Any criticality:high allergy + active medications | MODERATE |
| Default | No conflicts detected | LOW |

Rules are evaluated in priority order. First match wins.
Adding a new rule is adding one item to RULES in src/triage/rules.py.

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| FHIR_GATEWAY_URL | Yes | FHIR server base URL, e.g. http://localhost:8080/fhir |
| FHIR_API_KEY | No | Kong API key — omit for local dev without Kong |
