# provider-registry-service — Provider Search's deterministic core (Phase 3, M2)

The **only** service in Phase 3 with clinical/business logic. It owns the canonical provider
registry (real NPPES data, curated to NC/CA/MT) and answers three questions: what NUCC
taxonomy codes match a clinical need, which providers are near a location, and what's the full
record for a given NPI. `provider-mcp-server` is a thin protocol adapter in front of it —
never the other way around.

## API (internal only — never on the Kong edge)

| Route | What it does |
|---|---|
| `POST /v1/taxonomy/resolve` | Free-text clinical need → ranked NUCC taxonomy codes. Deterministic fuzzy match (`rapidfuzz` + a small synonym table) — no LLM call, fully traceable. |
| `POST /v1/providers/search` | `{location, taxonomy_codes, radius_miles, limit, accepting_new_patients?, entity_type?}` → nearest-N real providers, sorted by distance. Haversine over a state-scoped full scan (`location.py`'s `LocationSearchPort` — a deliberate stub, not PostGIS). |
| `GET /v1/providers/{npi}` | Full registry record by NPI, with lineage. Still returns a **deactivated** record explicitly (never a bare 404) — a caller with a stale NPI on file needs to see *why*, not get an error that looks like a data problem. |
| `GET /health` | `{"status": "ok", "version": "..."}` |

Error taxonomy (design.md §8.4): `validation_error`→400, `not_found`→404,
`upstream_unavailable`→502/503; a search with zero matches or an ambiguous location is a
normal `200`, never an error.

## Running locally

```bash
# Needs Postgres. Either the docker-compose service:
docker compose --profile phase3 up -d postgres

# ...or your own, matching schema.sql's expected role/db (see below).

pip install -e "provider-registry-service[dev]"
export DATABASE_URL="postgresql://provider_registry:provider_registry@localhost:5432/provider_registry"
python -m provider_registry.init_db          # applies schema.sql (idempotent, CREATE ... IF NOT EXISTS)
uvicorn provider_registry.main:app --port 8002 --reload
```

API docs (Swagger UI): http://localhost:8002/docs

Schema is **not** a migration framework — `schema.sql` is plain, re-runnable DDL, matching
`rxclaim-emulator`'s `schema.sql` convention rather than introducing Alembic for a 7-table
schema. `init_db.py` is a separate step from the app itself (not FastAPI lifespan), so
route-level tests that don't need a database stay genuinely database-free.

## Data model

`providers` · `provider_addresses` · `provider_taxonomies` · `taxonomy_reference` ·
`zip_centroids` · `ingestion_runs` · `anomaly_flags` — full column-level detail in
`schema.sql` and design.md §4.1. Nothing here is written by this service itself: ingestion
(`data/scripts/provider_ingest/`) writes directly to Postgres (design.md §6, decision P10);
this service is read-only.

`accepting_new_patients` is deliberately not a column — NPPES has no such field, and every
search response reports it as `"unknown"` rather than guessing (decisions.md P6).
`npi_status` (`active`/`deactivated`) is real and enforced: `search_providers_near` excludes
deactivated providers by default.

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | Postgres connection string, e.g. `postgresql://provider_registry:provider_registry@localhost:5432/provider_registry` |
| `RATE_LIMIT_REQUESTS` | No | Max requests per window per caller (default `60`) — coarse in-memory defense-in-depth (design.md §12.1), not a substitute for correct IAM/VPC scoping |
| `RATE_LIMIT_WINDOW_SECONDS` | No | Window length in seconds (default `60`) |

## Test

```bash
pip install -e "provider-registry-service[dev]"
pytest provider-registry-service/src/provider_registry/tests
```

Split deliberately: validation/taxonomy/rate-limit tests need no database at all (Pydantic
validation short-circuits before any DB call); location/registry/API tests are DB-backed and
**self-skip** (not error) when Postgres is unreachable at `TEST_DATABASE_URL` — same pattern
as the project's e2e suite. `tests/fixtures.sql` is the small hand-written dataset those tests
run against, not real NPPES data.

## Cloud (design/stub — Phase 3b)

`infra/main.tf` is a Cloud Run stub, `ingress=internal`, `DATABASE_URL` from Secret Manager —
the Cloud Run equivalent of `rxclaim-emulator`'s `ingress=INTERNAL_ONLY` pattern. No
application-layer auth between callers and this service — verified (not assumed) against
Phase 2's actual code that internal calls carry no auth header there either; isolation is
IAM/VPC-scoping only (design.md §12.1). Composed into the root module at `infra/terraform/`
(M7) rather than applied standalone. Not applied until Phase 3b.
