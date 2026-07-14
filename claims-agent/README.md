# claims-agent — Claim adjudication explanation agent (Phase 2, M5)

A **separate** agent from the Phase 1 `mcp-agent` (deviation D3): it explains prescription-claim
adjudication decisions in plain language. It is **non-authoritative** (R17.8) — it calls the
claims-service to obtain the *authoritative* decision and only narrates it; it never computes,
changes, or overrides an outcome. All clinical/business logic stays in the deterministic services.

## How it works
1. `adjudicate_claim` tool → POST the claim to `claims-service` (`/claims/adjudicate`).
2. Explain the returned decision (outcome, aggregated reasons, pricing, decision id), in the
   style of PRD §9.4.

Two modes:
- **LLM mode** (Anthropic tool-use loop) when a key is present — richer narrative.
- **Deterministic mode** (`--no-llm`, or automatically when no key is set) — a template
  renderer, so it runs and tests without any API key.

## Usage
```bash
python3 -m claims_agent --claim claim.json                 # LLM if key set, else deterministic
python3 -m claims_agent --claim '{"claimId":"C1", ...}' --no-llm
python3 -m claims_agent --claim claim.json --claims-url http://localhost:8090
```
Example (deterministic) output:
```
✅ APPROVED
   Decision: DEC-C1
────────────────────────────────────────────────────────────────────
Claim approved. Pricing: total $241.50, patient pays $48.30, plan pays $193.20 (auth RX…). Decision id: DEC-C1.
```

## Environment
- `ANTHROPIC_API_KEY` / `CLAUDE_API_KEY` — optional (falls back to deterministic).
- `CLAIMS_GATEWAY_URL` — claims-service base URL (default `http://localhost:8090`; point at the
  Kong proxy for the gated setup).
- `CLAIMS_API_KEY` — Kong API key (omit for local/direct).

## Test
```bash
pip install -e "claims-agent[dev]"
pytest claims-agent/tests            # explanation renderer + tool client (mocked httpx)
```

## Scope / notes
Standalone; shares no code with the Phase 1 `mcp-agent` (kept untouched, D3). Compose/gateway
wiring with the live claims-service + emulator + triage is **M6**.
