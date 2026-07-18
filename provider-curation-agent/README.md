# provider-curation-agent — ingestion run-summary agent (Phase 3, M4)

A **separate** agent from `provider-search-agent`, mirroring the Phase 2 precedent of
`claims-agent` being separate from `mcp-agent` (decisions.md P1). It orchestrates the
deterministic ingestion pipeline (`data/scripts/provider_ingest/`) and narrates the result. It
is **non-authoritative**: it never writes to the registry, computes record counts, or resolves
an anomaly itself — only the deterministic scripts do that; this agent describes what they did.

Deliberately **not** an MCP client — ingestion is a batch/offline concern, out of the MCP
boundary `provider-search-agent`/`provider-mcp-server` use for queries (design.md §3.2).

## How it works

1. `run_provider_ingestion` tool → for each requested state without an already-fetched curated
   file, run `fetch_nppes.py`; then run `run_ingestion.py` for all requested states; then read
   the **authoritative** result back from Postgres (`ingestion_runs` + `anomaly_flags`) — never
   from subprocess stdout text.
2. Narrate it: record counts, an anomaly breakdown by type, a couple of concrete examples.

Two modes, same as `claims-agent`:
- **LLM mode** (Anthropic tool-use loop) when a key is present — richer narrative.
- **Deterministic mode** (`--no-llm`, or automatically when no key is set) — a template
  renderer (`summarize.py`), so it runs and tests without any API key.

## Usage

```bash
python3 -m provider_curation_agent --states NC,CA,MT              # LLM if key set, else deterministic
python3 -m provider_curation_agent --states NC --no-llm
```

Example (deterministic) output:
```
📋 Ingestion run: NC, CA, MT
   Run id: e3d6517b-99d0-4ea8-b45b-14dc53cd0fb8
────────────────────────────────────────────────────────────────────
Ingestion run e3d6517b-... for NC, CA, MT complete. 7542 record(s) added, 5040 updated,
396 anomalies flagged. Anomaly breakdown: 396 missing_coordinate. Sample flags: NPI ... —
missing_coordinate: zip5='27157' not found in zip_centroids | ...
```

## Environment

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | Postgres connection string — see `provider-registry-service/schema.sql` |
| `ANTHROPIC_API_KEY` / `CLAUDE_API_KEY` | No | Optional (falls back to deterministic) |

## Test

```bash
pip install -e "provider-curation-agent[dev]"
pytest provider-curation-agent/tests
```

`test_summarize.py` is pure logic (no DB). `test_ingestion_tools.py` mixes mocked-subprocess
tests (no DB) with DB-backed tests that self-skip when Postgres is unreachable at
`TEST_DATABASE_URL`. **Naming note:** this file is *not* called `test_tools.py` on purpose — a
file with that exact name in `claims-agent/tests/` silently collided with an
identically-named one here under this repo's `--import-mode=importlib` (both packages'
`tests/` resolve to the same dotted module name), so one set of tests ran twice and the other
never ran at all, with a passing exit code throughout. See design.md §14 / decisions.md P15
before adding any new `tests/` file anywhere in this repo.

## Scope / notes

At single-source (NPPES-only) scale, "AI curation" mostly means *summarizing and flagging*,
not *resolving conflicts* — there's no cross-source entity resolution to do yet since NPI is
already a unique, authoritative identity key. The architecture leaves the seam
(`upsert_golden_record` in `run_ingestion.py`) for when a second source is added.
