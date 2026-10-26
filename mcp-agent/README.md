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

# With the triage service and FHIR server already running (see repo README),
# and a local Ollama serving llama3.2:1b (the default provider; no API key):
FHIR_GATEWAY_URL=http://localhost:8080/fhir \
TRIAGE_SERVICE_URL=http://localhost:8001 \
python3 -m agent.agent --query "Check refill risk for Kristle Mraz"

# Interactive REPL: omit --query
python3 -m agent.agent

# To use Claude instead, opt in explicitly. An API key alone does not switch
# providers (docs/phase6/decisions.md H46), and patient data then leaves this host:
LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=<key> \
FHIR_GATEWAY_URL=http://localhost:8080/fhir \
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
| `LLM_PROVIDER` | No | `ollama` (default when unset: self-hosted, free, PHI never leaves this host), `anthropic` or `openai_compatible` |
| `LLM_MODEL` | No | Model name (defaults: `llama3.2:1b` for Ollama, `claude-sonnet-4-5` for Anthropic). Required for `openai_compatible` |
| `LLM_BASE_URL` | No | Default `http://localhost:11434/v1` for Ollama. Required for `openai_compatible` |
| `LLM_API_KEY` | No | Key for an `openai_compatible` endpoint that needs one; Ollama needs none |
| `ANTHROPIC_API_KEY` | Only with `LLM_PROVIDER=anthropic` | Anthropic API key. `CLAUDE_API_KEY` (the Codespaces secret name) is accepted as a fallback. Setting it does not change the provider on its own |
| `DEPLOYMENT_ENV` | No | `production` refuses to fall back to Ollama silently when `LLM_PROVIDER` is unset |
| `FHIR_GATEWAY_URL` | Yes | FHIR server base URL, e.g. `http://localhost:8080/fhir` |
| `FHIR_API_KEY` | No | Kong API key — omit for local dev without Kong |
| `TRIAGE_SERVICE_URL` | No | Triage service base URL (default `http://localhost:8001`) |
