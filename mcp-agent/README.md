# MCP Agent

LLM-powered clinical workflow orchestrator built directly on the Anthropic
tool-use API (no framework). It interprets a natural-language clinician query,
calls FHIR and triage tools, and composes a structured recommendation.

**The agent holds no clinical logic.** It orchestrates tool calls and writes the
narrative; all risk evaluation lives in the triage service.

---

## Tools

| Tool | What it does | Backend |
|---|---|---|
| `get_patient_summary` | Resolve a patient name → FHIR ID + demographics | `fhir-clinical-client` → FHIR server |
| `assess_refill_risk` | Evaluate drug-allergy risk for a patient | HTTP → triage service |

---

## Running locally

```bash
pip install -e "client/clinical[dev]" -e "triage-service[dev]" -e "mcp-agent[dev]"

# With the triage service and FHIR server already running (see repo README):
ANTHROPIC_API_KEY=<key> \
FHIR_GATEWAY_URL=http://localhost:8080/fhir \
TRIAGE_SERVICE_URL=http://localhost:8001 \
python3 -m agent.agent --query "Check refill risk for Kristle Mraz"

# Interactive REPL: omit --query
python3 -m agent.agent
```

Via Docker Compose, the image entrypoint already runs the agent — pass only args:

```bash
docker compose run --rm mcp-agent --query "Check refill risk for Kristle Mraz"
```

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key. `CLAUDE_API_KEY` (the Ona secret name) is accepted as a fallback. |
| `FHIR_GATEWAY_URL` | Yes | FHIR server base URL, e.g. `http://localhost:8080/fhir` |
| `FHIR_API_KEY` | No | Kong API key — omit for local dev without Kong |
| `TRIAGE_SERVICE_URL` | No | Triage service base URL (default `http://localhost:8001`) |
