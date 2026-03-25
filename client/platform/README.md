# Platform Client — FHIR Infrastructure Engineers

This directory is for platform engineers who build and maintain `fhir-service`.
Tests here run directly against the FHIR server — no Kong gateway, no API key,
no GCP required.

**Audience:** Health IT engineers, EHR integration specialists, FHIR implementation
engineers. You understand FHIR resources, Spring Boot, and Neon PostgreSQL.

---

## What these tests cover

`integration_test.py` validates the FHIR server's own behaviour:

- Server is reachable and returns a valid CapabilityStatement
- Patient resources can be created and retrieved
- The FHIR R4 profile is active

What these tests deliberately do **not** cover:
- API key authentication (that is Kong's concern, tested in `client/clinical/`)
- Rate limiting (Kong's concern)
- GCP deployment (use `client/clinical/` for that)

---

## Prerequisites

The FHIR service must be running locally before you run these tests.

### Option A — Run with H2 (in-memory, no database setup needed)

```bash
cd fhir-service
./mvnw spring-boot:run
```

Wait for the log line:
```
Started Application in X seconds
```

The server is ready when `curl http://localhost:8080/actuator/health` returns `{"status":"UP"}`.

### Option B — Run with Neon (production profile)

```bash
cd fhir-service
SPRING_PROFILES_ACTIVE=neon \
SPRING_DATASOURCE_URL="jdbc:postgresql://HOST/fhirdb?user=USER&password=PASS&sslmode=require" \
SPRING_DATASOURCE_DRIVER_CLASS_NAME=org.postgresql.Driver \
SPRING_JPA_PROPERTIES_HIBERNATE_DIALECT=ca.uhn.fhir.jpa.model.dialect.HapiFhirPostgresDialect \
HIBERNATE_DIALECT=ca.uhn.fhir.jpa.model.dialect.HapiFhirPostgresDialect \
./mvnw spring-boot:run
```

---

## Running the tests

```bash
# Default — hits http://localhost:8080/fhir
python3 client/platform/integration_test.py

# Custom URL (e.g., different port)
FHIR_BASE_URL=http://localhost:9090/fhir python3 client/platform/integration_test.py
```

Expected output:
```
Platform integration test
  Server: http://localhost:8080/fhir

1. Server reachability
  [PASS] GET /metadata returns 200
  [PASS] Response is a FHIR CapabilityStatement
  [PASS] FHIR version is R4

2. Patient CRUD
  [PASS] POST /Patient returns 201
  [PASS] Created Patient has an ID
  [PASS] GET /Patient/{id} returns 200
  [PASS] Retrieved family name matches

────────────────────────────────────────
  Results: 7/7 passed
────────────────────────────────────────
```

---

## Relationship to other tests

| Test location | What it tests | Requires |
|---|---|---|
| `fhir-service/src/test/` | Unit tests, Spring context | Maven |
| `client/platform/` (here) | FHIR server behaviour | Local running server |
| `client/clinical/` | Full stack via Kong | GCP deployment + API key |
