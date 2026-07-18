# provider_ingest — real NPPES/NUCC/ZCTA ingestion (Phase 3, M3)

Deterministic ETL: pulls real public provider data and loads it directly into
`provider-registry-service`'s Postgres schema. Writes directly to the database (design.md §6,
decisions.md P10) — no HTTP layer, `provider-registry-service` gains no write endpoints from
this. Curated data lives in [`data/reference/providers/`](../../reference/providers/) (small,
public-domain, committed — see that policy in `data/reference/.gitignore`).

## Scripts

| Script | What it does |
|---|---|
| `fetch_nucc_taxonomy.py` | Downloads the real NUCC taxonomy CSV (nucc.org, no auth) → `data/reference/providers/taxonomy_reference.csv` (all 883 codes — already small, no sub-sampling needed) |
| `fetch_zcta_centroids.py` | Downloads the Census Gazetteer ZCTA file + the 2020 ZCTA-to-county relationship file (the Gazetteer file alone has no state column — checked, not assumed), joins them (majority-land-area rule for split ZCTAs), filters to `--states` → `data/reference/providers/zip_centroids.csv` |
| `fetch_nppes.py` | Pulls real NPPES NPI Registry records for one state, paired with a curated `TAXONOMY_TERMS` list → `data/reference/providers/nppes_<state>.json` |
| `run_ingestion.py` | Loads the curated CSV/JSON files into Postgres: upserts `taxonomy_reference` + `zip_centroids`, then for each state upserts `providers`/`provider_addresses`/`provider_taxonomies` and flags `anomaly_flags`. Idempotent — re-running updates, never duplicates. |

`provider-curation-agent` orchestrates these (deterministic subprocess calls) and narrates the
result; running them directly here is for ingestion/dev work, not day-to-day querying.

## Usage

```bash
pip install -e "provider-registry-service[dev]"   # for psycopg — these scripts reuse its install
export DATABASE_URL=postgresql://provider_registry:provider_registry@localhost:5432/provider_registry

python3 data/scripts/provider_ingest/fetch_nucc_taxonomy.py
python3 data/scripts/provider_ingest/fetch_zcta_centroids.py --states NC,CA,MT
python3 data/scripts/provider_ingest/fetch_nppes.py --state NC     # repeat per state
python3 data/scripts/provider_ingest/run_ingestion.py --states NC,CA,MT
```

The curated files already committed in `data/reference/providers/` mean you usually only need
`run_ingestion.py` — the fetchers are for pulling fresh data or adding a new state.

## Real data sources (verified live, not assumed)

| Source | URL | Cadence | Key gotchas |
|---|---|---|---|
| NPPES NPI Registry (CMS) | `npiregistry.cms.hhs.gov/api/?version=2.1` | Near-real-time | A bare `state` filter is rejected — must pair with `taxonomy_description`. `state=NC` matches *any* of a provider's addresses, not just the practice one — `fetch_nppes.py` filters to the LOCATION address actually being in the queried state. `basic.status` was `"A"` on every sampled record (hundreds) — deactivated NPIs may not surface via this endpoint at all. |
| NUCC Health Care Provider Taxonomy | `nucc.org/images/stories/CSV/nucc_taxonomy_260.csv` (v26.0) | ~2 releases/year | Codes are 10 chars, alphanumeric, always ending in `X` — verified against all 883, zero exceptions. |
| Census Gazetteer ZCTA file | `www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_zcta_national.zip` | Per decennial + intercensal | No state column — joined against the ZCTA-to-county relationship file. ZCTA ≠ USPS ZIP exactly; non-residential/institutional ZIPs (e.g. a hospital's own ZIP) often have no ZCTA at all — a confirmed real example is in design.md §7. |

Full gotcha detail, coordinate-resolution rate (measured 94.2%, not the ≥99% first assumed),
and the KPI revision this produced: design.md §6/§7/§14, decisions.md P11/P12.

## Real result (curated NC/CA/MT set, as of M4)

12,582 unique real providers (5,040 NC + 5,519 CA + 2,023 MT), 883/883 NUCC codes, 3,025 ZIP
centroids. Bounded pull, not a full-state census — a few pages per taxonomy term per state,
mirroring Phase 2's "curated slice, not the full CMS PUF" precedent
(`data/reference/README.md`). A true full-state pull is a longer-running operation this
project deliberately didn't run.

## Test

```bash
pip install -e "provider-registry-service[dev]"
pytest data/scripts/provider_ingest
```

`test_fetch_*.py` mock HTTP (no network). `test_run_ingestion.py` is DB-backed and self-skips
when Postgres is unreachable at `TEST_DATABASE_URL`.

## Cloud (design/stub — Phase 3b)

`infra/main.tf` is a Cloud Run **Job** stub (manually-triggered, not a standing service —
matches the "manually re-run, one-time-per-state seed" decision, not a live pipeline).
