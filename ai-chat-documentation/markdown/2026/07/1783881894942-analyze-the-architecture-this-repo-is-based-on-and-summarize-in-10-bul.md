# Analyze the architecture this repo is based on and summarize in 10 bullets

## Prompt

Analyze the architecture this repo is based on and summarize in 10 bullets

## Final response

## Architecture Summary — Agentic Healthcare Workflow Platform

- **Microservices, cloud-agnostic design**: The system is decomposed into independent services (fhir-service, triage-service, mcp-agent, gateway, epic/athena emulators) rather than a monolith, orchestrated via Docker Compose locally and Kubernetes/GKE in production.

- **Layered flow**: Requests move top-down through 3 layers — Agentic Orchestration (LLM agent) → MCP Tool Servers → FHIR Servers — each layer only talking to the one below it.

- **LLM-powered agent orchestration (mcp-agent)**: A Python agent using the raw Anthropic tool-use API (Claude Sonnet) interprets natural-language clinical queries in a loop, calling tools and feeding results back to the model until a final answer is produced. It intentionally contains **no clinical logic** — it only orchestrates.

- **MCP (Model Context Protocol) tool abstraction**: FHIR operations (get_patient, get_medications) and workflow/safety actions are exposed as discrete, composable "tools" the LLM can call, decoupling agent reasoning from underlying service implementations.

- **Separation of clinical logic (triage-service)**: Drug-allergy/interaction risk evaluation lives in a dedicated Spring Boot/Python service, which queries FHIR data and returns a structured FHIR `RiskAssessment` resource — keeping business rules out of both the FHIR store and the agent.

- **Standards-based FHIR data layer (fhir-service)**: Built on the official HAPI FHIR JPA server (R4), providing a generic, standards-compliant persistence and API layer, ensuring portability across any FHIR R4-compliant backend. Supports H2 (dev) and Neon serverless PostgreSQL (prod).

- **API gateway enforcement (Kong)**: All client traffic to the FHIR server is routed through Kong, which enforces API-key authentication, rate limiting, and daily quotas — services never talk to HAPI directly, only through the gateway, per the "clinical-hat consumer" pattern seen in docker-compose.

- **EHR abstraction via emulators (planned)**: `epic-emulator` and `athena-emulator` are placeholders meant to layer EHR-specific auth, profiles, and proprietary extensions on top of the generic FHIR core, so the same agent/tooling can later target real-world EHR quirks without changing core logic.

- **Guardrails and auditability by design**: Every clinical assessment is persisted as a FHIR resource (RiskAssessment) with confidence levels and audit trails; the goal is zero autonomous high-risk actions without escalation, reflecting a safety-first agentic design.

- **Consistent, reproducible dev environment**: A devcontainer standardizes Java 21/Python/Node/Maven/Docker-in-Docker/kubectl/Helm/Terraform tooling and AI assistant configuration across contributors, supporting both local (Docker Desktop) and cloud (Ona) development.

<details>
<summary>Execution details — 7 tool call(s)</summary>

### Files inspected

- `README.md`
- `docker-compose.yml`
- `gateway/README.md`
- `mcp-agent/src/agent/agent.py`
- `NOTICE`
- `fhir-service/pom.xml`
- `mcp-agent/pyproject.toml`

### Tool activity

#### 1. `read_file`

```json
{
  "path": "README.md"
}
```

#### 2. `read_file`

```json
{
  "path": "docker-compose.yml"
}
```

#### 3. `read_file`

```json
{
  "path": "gateway/README.md"
}
```

#### 4. `read_file`

```json
{
  "path": "mcp-agent/src/agent/agent.py"
}
```

#### 5. `read_file`

```json
{
  "path": "NOTICE"
}
```

#### 6. `read_file`

```json
{
  "path": "fhir-service/pom.xml"
}
```

#### 7. `read_file`

```json
{
  "path": "mcp-agent/pyproject.toml"
}
```

</details>

---

## Archive metadata

- **Cline task ID:** `1783881894942`
- **Approximate creation time:** 12 July 2026, 18:44 UTC
- **Stored API messages:** 12
- **Recorded tool calls:** 7

The complete original Cline records are retained in the corresponding `raw/` directory.
