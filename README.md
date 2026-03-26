# Agentic Healthcare Workflow Platform

## Quick demo

A clinician types a natural-language query. The agent fetches FHIR data, evaluates medication safety, and returns a structured recommendation — in one turn.

```bash
cp .env.example .env          # set ANTHROPIC_API_KEY
docker compose up --build -d fhir triage
python3 data/scripts/seed_demo.py
docker compose run --rm mcp-agent \
  python3 -m agent.agent --query "Check refill risk for Kristle Mraz"
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
| **triage-service** | Business logic for drug-allergy risk evaluation, interaction checking, and recommendation generation. | 🚧 Planned |
| **mcp-agent** | LLM-powered orchestration layer that uses MCP tools to execute workflows. | 🚧 Planned |

---

## Current Status (Phase 1)

A fully functional FHIR R4 server is running, built on the **official HAPI FHIR JPA starter (8.8.0)**. It supports:

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
cd fhir-service
./mvnw clean verify
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

### Phase 1 (Current)
- ✅ Generic FHIR R4 server (all resource endpoints)
- ✅ H2 in-memory (dev) and Neon serverless PostgreSQL (prod) profiles
- ✅ Versioned profile URL fallback for validation
- ✅ 39 unit and integration tests passing

### Phase 2 (Next)
- ⏳ **EHR Emulators**: Epic and Athena customizations (auth stubs, custom profiles, proprietary extensions)
- ⏳ **Triage Service**: Business logic for drug-allergy risk evaluation and recommendation generation
- ⏳ **MCP Agent**: LLM-powered orchestration layer using FHIR tools

### Known Issues
- Versioned profile URL fallback (`VersionedUrlFallbackValidationSupport`) is a workaround for a gap in HAPI FHIR core; can be removed once HAPI FHIR natively resolves versioned canonical URLs in `DefaultProfileValidationSupport`
- Binary storage defaults to database; filesystem mode requires explicit `hapi.fhir.binary_storage_mode` and `hapi.fhir.binary_storage_filesystem_base_directory` configuration
- MDM (patient matching) is disabled by default; enable with `hapi.fhir.mdm_enabled=true`

---

## Next Steps (Phase 1)

1. Add RestAssured integration tests to `fhir-service` (create, retrieve, and search `Patient` resources)
2. Build `triage-service` as a Spring Boot microservice that:
   - Queries the FHIR server for patient data
   - Evaluates drug-allergy conflicts and interactions
   - Returns a `RiskAssessment` FHIR resource
3. Wrap FHIR operations as MCP tools (e.g., `get_patient`, `get_medications`)
4. Implement `mcp-agent` to orchestrate the triage workflow end-to-end

---

## License

Proprietary. All rights reserved. Third-party components are used under their respective open-source licences. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE) for details.

---

## Acknowledgements

- [HAPI FHIR](https://hapifhir.io) — open-source FHIR implementation for Java (Apache License 2.0)
- [Neon](https://neon.tech) — serverless PostgreSQL
- [Ona (Gitpod)](https://ona.com) — cloud development environment
