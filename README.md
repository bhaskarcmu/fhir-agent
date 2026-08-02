# Agentic Healthcare Workflow Platform

## Quick demo

A clinician types a natural-language query. The agent fetches FHIR data, evaluates medication safety, and returns a structured recommendation — in one turn.

```bash
docker compose up --build -d fhir triage
python3 data/scripts/seed_demo.py
# The mcp-agent image's entrypoint already runs the agent — pass only its args.
# No API key needed: the agent defaults to a self-hosted, free model (see below).
docker compose run --rm mcp-agent --query "Check refill risk for Kristle Mraz"
```

By default the agent runs against a self-hosted Ollama model — no API key, no cost, and PHI
never leaves this host (docs/phase6/decisions.md H45). The docker-compose `mcp-agent`/
`mcp-agent-api` services don't yet have host-Ollama networking wired in (a known, deferred gap —
see `docs/phase6/milestone-plan.md` M5), so for now, to use a real Claude model in the demo
above, set `ANTHROPIC_API_KEY` in `.env` (`cp .env.example .env`) and add
`--provider anthropic --model claude-sonnet-4-5` to the query above. Running the CLI directly on
the host (not via docker-compose) already works against a locally-running `ollama serve` with no
extra configuration.

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

## Documentation

Everything is indexed in **[`docs/`](docs/README.md)**. Start with what you're doing:

| I want to… | Read |
|---|---|
| **See it work**, or demo it (clinician / insurer / architect / layperson) | [`docs/demo-guide.md`](docs/demo-guide.md) |
| **Understand the code** and change it safely | [`docs/developer-guide.md`](docs/developer-guide.md) |
| **Run the tests**, or write good ones | [`docs/testing-guide.md`](docs/testing-guide.md) |
| **Operate the gateway** (local, cloud, migration) | [`docs/gateway-runbook.md`](docs/gateway-runbook.md) |
| **Know why** Phase 2 is built this way | [`docs/phase2/plan.md`](docs/phase2/plan.md) |
| **Know why** Phase 3 (Provider Search) is built this way | [`docs/phase3/design.md`](docs/phase3/design.md) |
| **Audit Phase 2 decisions** (status + supersession) | [`docs/phase2/decisions.md`](docs/phase2/decisions.md) |
| **Audit Phase 3 decisions** (status + supersession) | [`docs/phase3/decisions.md`](docs/phase3/decisions.md) |
| **Know what was agreed** (normative requirements) | [`docs/phase2/requirements.md`](docs/phase2/requirements.md) |
| **Know what to build next** | [`docs/phase2/plan.md` §16](docs/phase2/plan.md#16-future-work) |

Working agreements (git rules, the two worktrees, how to work here): [`CLAUDE.md`](CLAUDE.md).

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
| **mcp-agent** | LLM-powered orchestration layer that composes FHIR + triage tools. Self-hosted Ollama by default (no API key, no cost); Anthropic and other OpenAI-compatible providers available via explicit opt-in (`docs/phase6/decisions.md` H45). | ✅ Running (local + Docker Compose) |
| **rxclaim-emulator** *(Phase 2)* | Simulated legacy IBM i / RxClaim adjudication core: fixed-width DDS-style records, DB2/SQL400-style tables, RPG/CL-style `ADJRXCLM`. Internal-only. | ✅ Running (`--profile phase2`) |
| **claims-service** *(Phase 2)* | Spring Boot claims-adjudication façade: anti-corruption layer + layered rules engine + Decision Contract; persists a FHIR decision graph. | ✅ Running (`--profile phase2`) |
| **claims-agent** *(Phase 2)* | Non-authoritative agent that explains adjudication decisions in plain language. | ✅ Running (`--profile phase2`) |
| **provider-registry-service** *(Phase 3)* | FastAPI façade over the real, curated NPPES/NUCC provider registry: taxonomy resolution + haversine proximity search. Internal-only. | ✅ Running (`--profile phase3`) |
| **provider-mcp-server** *(Phase 3)* | The platform's first real, hand-built MCP server — genuine `initialize`/`tools/list`/`tools/call`, stdio transport. Thin adapter over `provider-registry-service`. | ✅ Running (local child process; no compose service — see [`docs/phase3/README.md`](docs/phase3/README.md)) |
| **provider-curation-agent** *(Phase 3)* | Non-authoritative agent that orchestrates real NPPES/NUCC/ZCTA ingestion and narrates the run. | ✅ Running (`--profile phase3`) |
| **provider-search-agent** *(Phase 3)* | Real MCP client/host: turns a natural-language clinical request into ranked, traceable providers by discovering and calling `provider-mcp-server`'s tools live. | ✅ Running (`--profile phase3`) |

---

## Current Status

**This section covers Phase 1 (the original walking skeleton) specifically.** Phase 2
(claims adjudication) and Phase 3 (provider search) are also complete and run locally —
see their own sections below, or [Status & future work](#status--future-work) for the
full picture across all three.

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

## Phase 2 — Claims Adjudication Modernisation Slice

Phase 2 extends the platform into **prescription claim adjudication**, wrapping a simulated
legacy RxClaim / IBM i core with modern services — an **API façade**, an **anti-corruption
layer**, a deterministic **rules engine**, an auditable **FHIR decision graph**, and a
plain-language **explanation agent**. Design, requirements, and architecture live in
[`docs/phase2/`](docs/phase2/README.md).

Request flow (opt-in `phase2` profile):

```
claims-agent ──▶ claims-service ──┬──▶ rxclaim-emulator   (legacy pricing/SOR, internal only)
 (explains)        (façade + ACL   ├──▶ triage-service     (clinical safety, reused Phase 1)
                    + rules engine) └──▶ fhir-service       (Claim/ClaimResponse/Task/Provenance)
```

The legacy core is **wrapped, not rewritten** (strangler pattern): the modern layer owns the
rules, experience, and audit trail; pricing and the member system-of-record remain "legacy".
Decisions are **deterministic** and **idempotent** — the same claim yields the same decision
and never double-writes its artefacts.

### Run the Phase 2 demo

```bash
# Bring up the full stack (Phase 1 services start automatically as dependencies)
docker compose --profile phase2 up --build -d

# Seed the FHIR fixtures and drive the six golden paths
# (approved / pended / routed / denied / multi-reason / clinical-safety)
python3 data/scripts/seed_claims_demo.py

# Explain a decision in plain language (deterministic without an API key)
docker compose --profile phase2 run --rm claims-agent \
  --no-llm --claim '{"claimId":"C1","memberId":"000000001","planId":"COM-SILVER","rxcui":"1991302","ndc":"63552-200","drugName":"semaglutide","quantity":1,"daysSupply":28,"dateOfService":"2026-06-01","prescriberNpi":"1234567890","coverageEffective":"2026-01-01","coverageTermination":"2026-12-31","priorAuthOnFile":false,"stepTherapyMet":false}'
```

A plain `docker compose up` (no profile) still runs **only** the Phase 1 stack — Phase 2 is
strictly additive.

> **The demo FHIR server is in-memory**, so it boots empty every time, and adjudication **fails
> closed** — a member with no clinical record pends rather than approving. Always run the seeder
> (it seeds fixtures *and* drives the paths). See the
> [demo prep checklist](docs/demo-guide.md#1-before-any-demo).

### Tests

```bash
pytest                                      # all Python suites (config in pytest.ini)
mvn -f claims-service/pom.xml test          # Phase 2 façade: unit + contract tests
mvn -f rxclaim-emulator/pom.xml test        # simulated legacy core
pytest e2e/                                 # golden paths (needs the phase2 stack up; else skips)
```

CI (`.github/workflows/tests.yml`) runs a **Phase-1-only** job (proving independence) plus the
Phase 2 suites. It does **not** run the e2e suite — that gap, and everything else that is and
isn't covered, is documented in the [testing guide](docs/testing-guide.md).

---

## Phase 3 — Provider Search & Referral

Phase 3 answers the question Phase 1/2 don't: *"who can this patient actually see?"* Given a
patient's location and a clinical need, it returns a ranked, explained list of **real**
providers — sourced from authoritative public data (NPPES), not a paid third-party directory
API — with full lineage back to the source record. **M1–M7 complete; Phase 3b (live cloud
deployment) not started.** Full design, milestone history, and every architectural decision
(with status tracking): [`docs/phase3/`](docs/phase3/README.md).

It's also this platform's **first genuine Model Context Protocol integration**. Prior "agent
tools" (`mcp-agent/src/agent/tools.py`) are in-process Python function dispatch; Phase 3 builds
a real, hand-built MCP server and a real MCP client/host, talking the actual protocol
(`initialize` → `tools/list` → `tools/call`) — not a simulation of it.

Request flow (opt-in `phase3` profile):

```
provider-search-agent ──(MCP: stdio)──▶ provider-mcp-server ──(HTTP)──▶ provider-registry-service ──▶ Postgres
  (NL request, real MCP        (real MCP server —              (taxonomy resolution +
   client/host, discovers       genuine protocol                haversine proximity search;
   tools live via tools/list)   boundary)                       internal-only, never on Kong edge)

provider-curation-agent ──▶ data/scripts/provider_ingest/*.py ──▶ Postgres
  (orchestrates + narrates       (real NPPES/NUCC/Census ingestion —
   a run; NOT an MCP client)      curated to NC/CA/MT, 12,582 real providers)
```

Real, not synthetic, on the provider side: 12,582 real providers across three curated states
(NC/CA/MT), pulled live from the NPPES NPI Registry and NUCC taxonomy sources, with lineage
from every registry record back to its ingestion run. (Patients stay synthetic, as elsewhere in
this repo — Phase 3 is about *finding* a provider, not about patient data.)

### Run the Phase 3 demo

```bash
# Bring up Postgres + the registry service (Phase 1/2 services start automatically as
# dependencies if you also pass their profiles; phase3 alone is self-contained)
docker compose --profile phase3 up --build -d postgres provider-registry

# Seed real data (NC only — fast; add CA,MT for the full curated set, ~1-2 min)
docker compose --profile phase3 run --rm -T provider-curation-agent --states NC --no-llm

# Ask a real question (needs ANTHROPIC_API_KEY or CLAUDE_API_KEY in .env — this agent has
# no deterministic fallback, unlike claims-agent: its whole job is NL understanding)
docker compose --profile phase3 run --rm provider-search-agent \
  --query "find an endocrinologist near 27514"
```

> **Use `-T` with `docker compose run` for any Phase 3 CLI agent** (`provider-curation-agent`,
> `provider-search-agent`) if you're scripting it non-interactively — some environments
> silently swallow stdout without it. `docker run -d ... && docker logs <container>` is a
> reliable fallback if output still doesn't show up. See [`docs/phase3/README.md`](docs/phase3/README.md).

A plain `docker compose up` (no profile) still runs **only** the Phase 1 stack — Phase 3 is
strictly additive, same guarantee as Phase 2.

### Tests

```bash
pytest                                      # all Python suites, including Phase 3 (config in pytest.ini)
```

CI (`.github/workflows/tests.yml`) runs `phase3-python` (the full Phase 3 suite against a
**real Postgres service container** — DB-backed tests execute for real in CI, not just
locally) and `phase3-terraform` (`terraform validate`, matrix across all four Phase 3
Terraform directories — deliberately `validate`, not `plan`, since `plan` needs live GCP
credentials this project doesn't provision). The real, billed-API-call groundedness eval
self-skips in CI (no key secret configured) — a deliberate cost-conscious choice.

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
python -m pip install -e "client/clinical[dev]" -e "agent-platform[dev]" -e "triage-service[dev]" -e "mcp-agent[dev]"
pytest                              # runs all Python suites (config in pytest.ini)
pytest agent-platform/tests -q      # separate invocation -- see pytest.ini's own comment on why

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

## Status & future work

### Done
- ✅ **Phase 1** — FHIR R4 server (H2 dev / Neon PostgreSQL cloud), triage rule engine, MCP
  agent, end-to-end demo. Tagged `phase1-v1` and independently runnable.
- ✅ **Phase 2 (M0–M7)** — legacy emulator, adjudication façade + ACL + rules engine, Decision
  Contract, FHIR audit graph, explanation agent, compose profiles, DB-less Kong, golden paths.
  Runs end to end locally.
- ✅ **Phase 3 (M1–M7)** — real NPPES/NUCC provider registry (12,582 real providers, 3 states),
  a hand-built MCP server + real MCP client/host agent (this platform's first genuine MCP
  integration), a curation agent, a root Terraform module, `deploy-phase3.sh`, and CI wired to
  actually run the Phase 3 suite against a real Postgres service container. Runs end to end
  locally, including through the real Docker images. Design/decisions:
  [`docs/phase3/`](docs/phase3/README.md).

### Next
Phase 2's prioritised backlog lives in
**[`docs/phase2/plan.md` §16](docs/phase2/plan.md#16-future-work)**. The headlines: run e2e in
CI (the top gap), non-regression decision snapshots, a circuit breaker on the triage call, the
Postgres swap behind the C3 seam, and **M8 / Phase 2b** — the cloud deploy, which needs its
root Terraform module **written** before it can be applied
([cloud-delivery gap](docs/phase2/plan.md#6-workstreams--milestones)).

For Phase 3: **Phase 3b** — live GCP deployment (`terraform apply` + `deploy-phase3.sh`
against a real project; nothing has been deployed yet, only `terraform validate`). Also
tracked but not built: an `accepting_new_patients` data source (NPPES has none — every
provider reports `unknown`, honestly, rather than guessing), and a taxonomy-matcher quality
pass (found real: `resolve_specialty("endocrinologist")` returns `ambiguous` against the full
NUCC code set — see [`docs/phase3/design.md` §14](docs/phase3/design.md#14-risks)).

Longer-standing: EHR emulators (`epic-emulator/`, `athena-emulator/` are placeholders),
drug-drug interaction rules, and load testing.

### Known issues
- Versioned profile URL fallback (`VersionedUrlFallbackValidationSupport`) is a workaround for a
  gap in HAPI FHIR core; removable once HAPI resolves versioned canonical URLs natively in
  `DefaultProfileValidationSupport`.
- Binary storage defaults to database; filesystem mode needs explicit
  `hapi.fhir.binary_storage_mode` + `hapi.fhir.binary_storage_filesystem_base_directory`.
- MDM (patient matching) is disabled by default; enable with `hapi.fhir.mdm_enabled=true`.
- Compose pins HAPI `v7.2.0` while docs reference `8.8.0` — drift to reconcile.

---

## License

Proprietary. All rights reserved. Third-party components are used under their respective open-source licences. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE) for details.

---

## Acknowledgements

- [HAPI FHIR](https://hapifhir.io) — open-source FHIR implementation for Java (Apache License 2.0)
- [Neon](https://neon.tech) — serverless PostgreSQL
- [Ona (Gitpod)](https://ona.com) — cloud development environment
