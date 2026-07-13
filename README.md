# Agentic Healthcare Workflow Platform

## Quick demo

A clinician types a natural-language query. The agent fetches FHIR data, evaluates medication safety, and returns a structured recommendation — in one turn.

```bash
cp .env.example .env          # set ANTHROPIC_API_KEY (or CLAUDE_API_KEY)
docker compose up --build -d fhir triage
python3 data/scripts/seed_demo.py
# The mcp-agent image's entrypoint already runs the agent — pass only its args:
docker compose run --rm mcp-agent --query "Check refill risk for Kristle Mraz"
```

Expected output:
```
🚨 HIGH RISK — Do not dispense without physician review
   Patient: Kristle Mraz  |  RiskAssessment/...
   Reason: Penicillin-class allergy conflicts with Amoxicillin prescription.
```

Demo patients loaded by `seed_demo.py`:

| Patient | Scenario | Expected result |
|---|---|---|
| Kristle Mraz | Penicillin allergy + Amoxicillin Rx | HIGH risk |
| John Doe | No allergies + Lisinopril Rx | LOW risk |

---

## Overview

This project builds a platform where clinicians can describe healthcare workflows in natural language, and an **agentic orchestration layer** (powered by LLMs and MCP) generates, deploys, and maintains FHIR-based automations. The goal is to replace traditional SaaS development with AI-driven orchestration, giving healthcare organisations custom tools without needing a full-time software development team.

**First workflow:** *Prescription Refill Risk Triage* — an agent that assesses drug-allergy conflicts, interactions, and fulfilment risks, producing triage recommendations with confidence scores and audit trails.

---

## Architecture

The platform is built as a collection of microservices, designed to be cloud-agnostic and fully compatible with FHIR R4.

```
┌─────────────────────────────────────────────────────────────────┐
│                    Agentic Orchestration                        │
│                (MCP Agent — LLM-powered)                       │
│   - Interprets user intents                                     │
│   - Discovers and composes MCP tools                           │
│   - Executes workflows, logs decisions                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       MCP Tool Servers                         │
│   - FHIR Tools (Patient, Medication, Allergy)                  │
│   - Safety Tools (drug-allergy, interactions)                  │
│   - Workflow Tools (submit triage, escalate)                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        FHIR Servers                            │
│   - Generic FHIR R4 server (development & testing)            │
│   - Future: EHR sandboxes (Epic, Athena) or emulators         │
└─────────────────────────────────────────────────────────────────┘
```

### Microservices

| Service | Purpose | Status |
|---|---|---|
| **fhir-service** | Generic FHIR R4 server (HAPI JPA). Used for local development and as the FHIR data source for the MCP agent. | ✅ Running (H2 local, Neon PostgreSQL cloud) |
| **epic-emulator** | Placeholder — will add Epic-specific customisations (auth stubs, custom profiles, proprietary extensions). | ⏳ Not yet implemented |
| **athena-emulator** | Placeholder — will add Athena-specific customisations. | ⏳ Not yet implemented |
| **triage-service** | FastAPI drug-allergy rule engine → FHIR `RiskAssessment` (HIGH/MODERATE/LOW) with audit trail. | ✅ Running (local + Docker Compose) |
| **mcp-agent** | LLM-powered orchestration layer (Anthropic tool-use) that composes FHIR + triage tools. | ✅ Running (local + Docker Compose) |

---

## Current Status

The end-to-end walking skeleton runs locally and via Docker Compose:
**mcp-agent → triage-service → fhir-service**. A natural-language clinician query
resolves a patient, evaluates drug-allergy risk, and returns a structured
recommendation (see [Quick demo](#quick-demo)).

The FHIR R4 server is built on the **official HAPI FHIR JPA starter (8.8.0)**. It supports:

- All FHIR R4 resource endpoints (`Patient`, `MedicationRequest`, `AllergyIntolerance`, etc.)
- Local development with an in-memory H2 database (`./mvnw spring-boot:run`)
- Cloud deployment with Neon serverless PostgreSQL (environment-variable-based configuration)
- FHIR `CapabilityStatement` at `GET /fhir/metadata`

The server is intentionally generic — it does not emulate any specific EHR. The agent and MCP tooling are built against a standard FHIR R4 endpoint first, ensuring portability. EHR-specific authentication, profiles, and extensions will be added later in the emulator modules.

---

## Getting Started

### Prerequisites

- **Java 21** (JDK — required; pom.xml targets Java 21)
- **Maven 3.8+** (or use the included Maven wrapper `./mvnw`)
- **Docker** (optional — required for integration tests using Testcontainers)
- **Neon** account (optional — required for cloud PostgreSQL profile)

### Clone the repository

```bash
git clone https://github.com/bhaskarcmu/fhir-agent.git
cd fhir-agent
```

### Run the FHIR server locally (H2)

```bash
cd fhir-service
./mvnw spring-boot:run
```

The server starts on `http://localhost:8080`. Visit `http://localhost:8080/fhir/metadata` to see the FHIR `CapabilityStatement`.

### Run with Neon PostgreSQL (cloud)

1. Create a [Neon](https://neon.tech) account and database.
2. Get your connection string from the Neon dashboard (format: `postgresql://user:password@host/db?sslmode=require`).
3. Convert it to JDBC format: `jdbc:postgresql://host/db?user=user&password=password&sslmode=require`
4. Run:

```bash
cd fhir-service
SPRING_DATASOURCE_URL="jdbc:postgresql://host/db?user=user&password=password&sslmode=require" \
SPRING_DATASOURCE_DRIVER_CLASS_NAME="org.postgresql.Driver" \
HIBERNATE_DIALECT="ca.uhn.fhir.jpa.model.dialect.HapiFhirPostgresDialect" \
./mvnw spring-boot:run -Dspring-boot.run.profiles=neon -Dmaven.test.skip=true
```

---

## Development Environment

The project uses a **devcontainer** to ensure a consistent environment across all contributors. The `.devcontainer/` directory defines:

- `Dockerfile` — Java 21, Python 3, Node.js, Maven, Docker-in-Docker, kubectl, Helm, Terraform
- VS Code extensions — Java, Spring Boot, Python, GitHub Copilot, Continue, Roo Code
- Post-start automation — configures AI tools (Claude Code, Continue, Roo Code) using secrets stored in Ona

**Opening the project:**

- **Local (Docker Desktop):** Open the folder in VS Code and click *Reopen in Container*
- **Cloud (Ona):** The container builds automatically on first launch

### Build and test before committing

```bash
# Python packages (editable installs + test tooling via the [dev] extras)
python -m pip install -e "client/clinical[dev]" -e "triage-service[dev]" -e "mcp-agent[dev]"
pytest                              # runs all Python suites (config in pytest.ini)

# FHIR service (Java).
# NOTE: unset any SPRING_DATASOURCE_URL / NEON_* env vars first, so the tests use
# the in-memory H2 default. Otherwise MdmTest boots the full app against a live
# database and fails on auth — a config/env issue, not a code failure.
cd fhir-service && ./mvnw clean verify
```

---

## Project Goals and Success Metrics

| Goal | Metric |
|---|---|
| Interoperability | System can pull FHIR data from any R4-compliant endpoint |
| Risk accuracy | Triage recommendations match a validated clinical ruleset ≥ 95% |
| Guardrail effectiveness | Zero autonomous actions below confidence threshold; all high-risk scenarios escalate |
| Agent adaptation | Agent learns from human overrides |
| Development velocity | Adding a new MCP tool takes < 1 day |

---

## Known Limitations & Future Work

### Done
- ✅ Generic FHIR R4 server (all resource endpoints)
- ✅ H2 in-memory (dev) and Neon serverless PostgreSQL (prod) profiles
- ✅ Versioned profile URL fallback for validation
- ✅ **Triage service** — drug-allergy rule engine → FHIR `RiskAssessment`
- ✅ **MCP agent** — Anthropic tool-use orchestration (FHIR + triage tools)
- ✅ End-to-end demo, both local processes and full Docker Compose
- ✅ Test suites: 39 Java (fhir-service) + 105 Python (client, triage, agent, data)

### Next
- ⏳ **EHR Emulators**: Epic and Athena customizations (auth stubs, custom profiles, proprietary extensions)
- ⏳ **Kong gateway on GKE**: production deployment with key-auth + rate limiting
- ⏳ Interaction checking and additional clinical rules

### Known Issues
- Versioned profile URL fallback (`VersionedUrlFallbackValidationSupport`) is a workaround for a gap in HAPI FHIR core; can be removed once HAPI FHIR natively resolves versioned canonical URLs in `DefaultProfileValidationSupport`
- Binary storage defaults to database; filesystem mode requires explicit `hapi.fhir.binary_storage_mode` and `hapi.fhir.binary_storage_filesystem_base_directory` configuration
- MDM (patient matching) is disabled by default; enable with `hapi.fhir.mdm_enabled=true`

---

## Next Steps

1. Add EHR emulators (Epic, Athena) — auth stubs, custom profiles, proprietary extensions
2. Deploy the Kong gateway + services to GKE (see `deploy.sh` and `gateway/`)
3. Expand the clinical ruleset (drug-drug interactions, dosage checks)
4. Add end-to-end smoke tests against the deployed, Kong-gated stack

---

## License

Proprietary. All rights reserved. Third-party components are used under their respective open-source licences. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE) for details.

---

## Acknowledgements

- [HAPI FHIR](https://hapifhir.io) — open-source FHIR implementation for Java (Apache License 2.0)
- [Neon](https://neon.tech) — serverless PostgreSQL
- [Ona (Gitpod)](https://ona.com) — cloud development environment
