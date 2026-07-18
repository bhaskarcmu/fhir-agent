# Phase 3 Design Proposal — Provider Search & Referral

**Status:** Draft — committed locally for review, not yet opened as a PR. Companion to `prd.md`.
Open questions from the first draft are resolved in §15 using best judgement.
**Terminology:** internal work is tracked as milestones (M1, M2, ...) — never "Phase 3.x". Phase
3b is the one exception: it names the future GCP cloud-deployment phase, mirroring Phase 2b.

---

## 1. Target architecture

```
 ┌─────────────────────────────┐
 │   Clinician / care coord.    │   same NL-request UX as existing
 │   (natural-language request) │   triage / claims agents
 └───────────────┬──────────────┘
                 │
                 ▼
 ┌──────────────────────────────────────────┐
 │  provider-search-agent                     │   NEW — standalone package
 │  MCP CLIENT/HOST                             │   (Phase 2 precedent: claims-agent
 │  Anthropic tool-use loop:                     │   kept separate from mcp-agent)
 │  NL → structured plan → MCP tool calls          │
 └───────────────┬──────────────────────────┘
                 │  MCP protocol, stdio transport
                 │  initialize → tools/list → tools/call
                 ▼
 ┌──────────────────────────────────────────┐
 │  provider-mcp-server                        │   NEW — the actual protocol boundary
 │  MCP SERVER (Python `mcp` SDK)                │   this phase exists to build
 │  tools: resolve_specialty                       │
 │         search_providers_near                    │
 │         get_provider                                │
 └───────────────┬──────────────────────────┘
                 │  internal HTTP (httpx) — same pattern
                 │  mcp-agent already uses to call triage-service
                 ▼
 ┌──────────────────────────────────────────┐
 │  provider-registry-service (FastAPI)         │   NEW — internal-only, never on
 │  modules: registry · taxonomy · location        │   Kong edge (rxclaim-emulator
 │  LocationSearchPort → HaversineSqlSearch          │   precedent)
 └───────────────┬──────────────────────────┘
                 │ SQL
                 ▼
 ┌──────────────────────────┐
 │  Postgres (Neon)           │   providers · provider_addresses ·
 │                              │   provider_taxonomies · taxonomy_reference ·
 │                              │   zip_centroids · ingestion_runs · anomaly_flags
 └────────────┬──────────────┘
              ▲
              │ upsert, manual re-run (one-time seed per state)
 ┌────────────┴──────────────────────────────┐
 │  provider-curation-agent                      │   NEW — standalone package,
 │  orchestrates deterministic ETL +               │   NOT an MCP client (ingestion
 │  generates an AI run-summary/anomaly report       │   is out of the MCP boundary —
 └────────────┬──────────────────────────────┘   see §3.2)
              │ pulls
 ┌────────────┴──────────────────────────────┐
 │  NPPES NPI Registry API (curated states)      │   public, real, authoritative
 │  NUCC taxonomy CSV                               │   — see §7
 │  Census ZCTA centroid file                          │
 └──────────────────────────────────────────┘
```

**Where this sits relative to the existing platform:** `provider-registry-service` and
`provider-mcp-server` join the *internal, east–west plane* alongside `rxclaim-emulator` —
no Kong route, Cloud Run ingress `internal` (mirrors Phase 2's C1 hybrid: GKE for
untouched Phase 1, Cloud Run for new services). `provider-search-agent` and
`provider-curation-agent` are CLI entrypoints this phase, same as `claims-agent` — no new
HTTP surface, no Kong route (decided, §15).

## 2. Package layout (new)

Following the Phase 2 precedent of standalone packages, not extensions of `mcp-agent`:

```
provider-registry-service/     FastAPI app — registry, taxonomy, location modules
provider-mcp-server/           Python MCP server (stdio), thin adapter over registry-service HTTP API
provider-search-agent/         MCP client/host — Anthropic tool-use loop
provider-curation-agent/       ETL orchestrator + AI run-summary generator
data/scripts/provider_ingest/  NPPES/NUCC/ZCTA fetch + normalize scripts the curation agent calls
```

Each gets its own `pyproject.toml` (src layout, `[dev]` extra) and a `pytest.ini` entry,
matching the convention already used by `triage-service` and `mcp-agent`.

## 3. The two agents

### 3.1 `provider-search-agent` (MCP client/host)

**Purpose.** Turn a natural-language or structured clinical request into an explained,
ranked provider list, entirely by orchestrating MCP tool calls.

**Tools it may call (via MCP, never in-process):**

| Tool | Input | Output |
|---|---|---|
| `resolve_specialty` | `{ query: str }` | ranked candidate NUCC codes + descriptions |
| `search_providers_near` | `{ location, taxonomy_codes, radius_miles, limit, accepting_new_patients? }` | ranked provider matches with distance + lineage |
| `get_provider` | `{ npi: str }` | full registry record + lineage |

**Inputs:** a clinician's NL request (e.g. *"find an endocrinologist within 15 miles of
27514 who's taking new patients"*), optionally structured fields if called from another
service instead of a chat surface.

**Outputs:** a ranked list of providers, each with NPI, name, address, distance, specialty
match, `accepting_new_patients` status (`true` / `false` / `unknown`), and a one-line
rationale (*"3rd nearest endocrinologist within 15 miles; specialty match: Endocrinology,
Diabetes & Metabolism"*).

**Guardrails (hard constraints, not suggestions):**
- Never state a provider fact not present in a `search_providers_near` / `get_provider`
  response. No inferred phone numbers, no guessed addresses, no invented "accepting new
  patients" values.
- Every provider in a response must be traceable: NPI + `ingestion_run_id` +
  `source_pulled_at` travel with every result, unsummarized.
- If `resolve_specialty` returns no confident match, or `search_providers_near` returns
  zero results, say so plainly and ask a clarifying question — never substitute a nearby
  specialty or a wider radius without saying that's what happened.
- The agent performs **no clinical judgment** beyond specialty matching — it does not
  assess whether a referral is medically appropriate.

**Groundedness mechanism:** every tool response the agent receives is the literal
registry record (JSON), not a paraphrase generated upstream — the agent's job is to
select/rank/explain, never to author facts. An eval harness (§10) asserts 100% of NPIs
in an agent transcript resolve via `get_provider`.

### 3.2 `provider-curation-agent` (ingestion/curation)

**Purpose.** Orchestrate the deterministic ETL pipeline and produce a human-readable
summary of each ingestion run — not to perform heroic cross-source entity resolution,
because **this phase has exactly one source (NPPES)**, and NPI is already a unique,
authoritative identity key. Fuzzy golden-record merging only becomes necessary once a
second source without NPI (e.g. a state licensing board) is added — a separate future initiative, not Phase 3b.

Being candid about this rather than overstating the agent's role: at MVP scale, "AI
curation" mostly means *summarizing and flagging*, not *resolving conflicts*. The
architecture leaves the seam (see `anomaly_flags`, golden-record merge function as an
isolated, swappable unit) for when that changes.

**What it orchestrates (deterministic, human-authored functions):**

| Function | What it does |
|---|---|
| `fetch_nppes_state(state)` | Paginated pull from the NPPES public API for one state |
| `normalize_taxonomy(record)` | Maps NPPES taxonomy codes to `taxonomy_reference`, flags unknown codes |
| `geocode_via_zip(record)` | Joins practice ZIP to `zip_centroids`; flags missing joins |
| `upsert_golden_record(record)` | Deterministic upsert keyed by NPI; today a straight upsert, structured as the seam for future multi-source merge rules |
| `flag_anomalies(run)` | Missing taxonomy, missing coordinate, address conflict vs. prior run |

**What the agent adds on top:** after a run completes, it reads the deterministic
`ingestion_runs` + `anomaly_flags` output and generates a plain-language run summary
("Pulled 8,412 NC records; 8,391 geocoded successfully; 21 flagged for missing practice
address; 3 taxonomy codes not found in the current NUCC reference — likely a stale
reference file"). This is a **read-only narrative layer** — the agent never writes to the
registry itself; only the deterministic functions do.

**Guardrails:** never invents record counts or flags not present in `ingestion_runs`/
`anomaly_flags`; never silently resolves an anomaly (e.g., never guesses a missing
coordinate) — it can only describe what the deterministic pipeline already decided.

**Not an MCP client.** The PRD's MCP requirement (FR6/FR7) is scoped to the three
query-side tools consumed by `provider-search-agent`. Ingestion is a batch/offline
concern; routing it through MCP would add protocol overhead with no client that needs
tool-discovery — flagged as a deliberate scoping choice, not an oversight.

## 4. Provider Registry Service

A single FastAPI app (matches `triage-service`'s shape: one deployable, internal HTTP
API, Pydantic request/response models), with three modules:

- **`registry`** — CRUD/read against the golden-record tables; `GET /providers/{npi}`.
- **`taxonomy`** — `POST /taxonomy/resolve`, fuzzy-matches free text against
  `taxonomy_reference` plus a small curated synonym table (e.g. "heart doctor" →
  *Cardiovascular Disease*). Deterministic (`rapidfuzz` or equivalent token match) — no
  LLM call inside this endpoint, so it stays a traceable, testable, human-authored tool.
- **`location`** — `POST /providers/search`, implements `LocationSearchPort` (below).

No separate "Specialty/Taxonomy service" deployment — folding it into
`provider-registry-service` as a module avoids standing up a second deployable for what
is, at this data volume, a single table lookup. Revisit if taxonomy resolution grows
real independent scaling needs.

### 4.1 Data model (Postgres, single instance — see §5 for the persistence decision)

**Domain terms, for readers who know FHIR provider-directory conventions:** the schema below
is a custom relational shape, not FHIR resources (§9 explains why), but it's worth naming the
correspondence to HL7's Da Vinci PDex Plan-Net IG — the real standard for this domain — so the
mapping is obvious if a future phase does go FHIR-native: `providers` (entity_type=1) ≈
Plan-Net `Practitioner`; `providers` (entity_type=2) ≈ `Organization`; `provider_addresses` ≈
`Location`; the practitioner-at-a-location-with-a-specialty combination that
`provider_taxonomies` + `provider_addresses` jointly express ≈ `PractitionerRole`. No
`HealthcareService` equivalent exists — Phase 3 doesn't model bookable services, only
providers and where to find them.

```
providers
  npi                 char(10) PK
  entity_type         smallint        -- 1=individual, 2=organization
  first_name          text NULL
  last_name           text NULL
  organization_name   text NULL
  phone               text NULL
  is_sole_proprietor  boolean NULL
  npi_status          text            -- 'active' | 'deactivated' (see status policy below)
  deactivated_at       date NULL       -- from NPPES deactivation date, if present
  deactivation_reason  text NULL       -- NPPES reason code, if present (to verify exact field
                                        -- name/values against the live schema at M3)
  source              text            -- 'NPPES'
  source_pulled_at    timestamptz
  ingestion_run_id    uuid FK -> ingestion_runs
  created_at / updated_at

provider_addresses
  id                  uuid PK
  npi                 char(10) FK -> providers
  address_1, address_2, city, state, zip5, zip4
  lat, lon            double precision NULL   -- NULL if ZIP centroid join failed
  is_primary_practice boolean

provider_taxonomies
  id                  uuid PK
  npi                 char(10) FK -> providers
  taxonomy_code       text FK -> taxonomy_reference
  is_primary          boolean

taxonomy_reference
  code                text PK          -- NUCC 10-char code
  grouping, classification, specialization  text
  definition          text
  nucc_version        text             -- e.g. "24.1" — pin what release this row came from

zip_centroids
  zip5                char(5) PK
  lat, lon            double precision
  state               char(2)

ingestion_runs
  id                  uuid PK
  started_at / completed_at
  states_pulled       text[]
  records_added / records_updated / records_flagged  int

anomaly_flags
  id                  uuid PK
  npi                 char(10) FK
  run_id              uuid FK -> ingestion_runs
  flag_type           text     -- missing_taxonomy | missing_coordinate | stale | address_conflict
  detail              text
```

`accepting_new_patients` is **deliberately not a column on `providers`** until §7's data
gap is resolved (decided to ship as `unknown` this build, §15). If a usable source is confirmed later, it lands as a
nullable boolean on `provider_addresses` (it's a practice-location-level fact, not an
NPI-level one) with its own `source`/`source_pulled_at` lineage pair, not silently merged
into the NPPES lineage fields.

**Provider status & serving policy (closes a real gap in the first draft).** NPPES tracks
deactivation for individual and organizational NPIs (retirement, death, fraud/error
correction) via deactivation-date/reason fields in the source data — the first draft's schema
had nowhere to put that fact, and no rule about what a search should do with it. Fixed here:

- `fetch_nppes_state` captures whatever deactivation signal NPPES exposes for the pulled
  record (field names/values to verify against the live API/bulk schema at M3 — not assumed)
  and `upsert_golden_record` sets `npi_status`/`deactivated_at`/`deactivation_reason`
  accordingly.
- **`search_providers_near` excludes `npi_status = 'deactivated'` by default.** A retired or
  deceased provider must never surface in a referral list — this is a correctness rule, not a
  ranking preference, so it's a hard filter, not something `accepting_new_patients`-style
  "unknown ≠ excluded" leniency applies to.
- **`get_provider` still returns a deactivated record** (by NPI, explicit lookup) — a
  downstream caller who already has an NPI on file needs to be able to see *why* it's stale,
  not get a 404 that looks like a data error.
- **Known residual gap, named rather than hidden:** because ingestion is a manually re-run,
  one-time-per-state seed (§6, PRD §6 Freshness), a provider that becomes deactivated *between*
  runs won't be caught until the next manual re-run — there is no live polling of NPPES's
  weekly deactivation file this build (§6). This is an accepted consequence of the one-time-seed
  decision, tracked as a named risk in §14, not an oversight.

### 4.2 `LocationSearchPort` — the swappable interface

```python
class Coordinate(NamedTuple):
    lat: float
    lon: float

class ProviderMatch(TypedDict):
    npi: str
    distance_miles: float
    # ...provider + address + taxonomy fields, lineage

class LocationSearchPort(Protocol):
    def search_near(
        self,
        origin: Coordinate,
        radius_miles: float,
        taxonomy_codes: list[str],
        limit: int,
        accepting_new_patients: bool | None,
        entity_type: Literal["individual", "organization"] | None = None,
        include_deactivated: bool = False,   # False = default hard filter, see §4.1
    ) -> list[ProviderMatch]: ...
```

**This phase's implementation — `HaversineSqlLocationSearch`:** a state-scoped full scan
computing great-circle distance in SQL, correct and fast at curated-subset scale:

```sql
SELECT p.npi, a.lat, a.lon,
  3959 * acos(
    cos(radians(:origin_lat)) * cos(radians(a.lat)) * cos(radians(a.lon) - radians(:origin_lon))
    + sin(radians(:origin_lat)) * sin(radians(a.lat))
  ) AS distance_miles
FROM provider_addresses a
JOIN providers p ON p.npi = a.npi
JOIN provider_taxonomies t ON t.npi = p.npi
WHERE t.taxonomy_code = ANY(:taxonomy_codes)
  AND a.state = ANY(:candidate_states)   -- cheap pre-filter, no PostGIS needed
  AND a.lat IS NOT NULL
  AND (:include_deactivated OR p.npi_status = 'active')   -- default hard filter, §4.1
  AND (:entity_type IS NULL OR p.entity_type = :entity_type)
HAVING distance_miles <= :radius_miles
ORDER BY distance_miles ASC
LIMIT :limit;
```

`:candidate_states` is derived from a coarse bounding box around the origin before the
query runs — enough to keep the scan small without any spatial index.

**Explicitly a stub.** No PostGIS, no Elasticsearch geo, no geohashing. **Future real
implementation** (not built now): PostGIS with a GiST index on a `geography` column, or
an Elasticsearch/OpenSearch `geo_distance` query, swapped in behind this same
`LocationSearchPort` — callers (the `location` module's route, and transitively the MCP
tool) don't change.

### 4.3 Ranking approach

Kept deliberately simple and explainable:

1. `resolve_specialty` does the only fuzzy matching in the system, producing a ranked
   list of taxonomy codes from free text.
2. `search_providers_near` takes those codes as an **exact filter** (not fuzzy) —
   candidates must have a matching `taxonomy_code` row.
3. Within the filtered set, the **sole rank key is distance ascending**. No weighted
   scoring, no relevance blending. This keeps the rationale trivially explainable
   ("nearest N providers with matching specialty") and avoids a second layer of
   unexplainable ranking logic.
4. `accepting_new_patients` filter semantics: if the caller passes `true`, the query
   includes providers where the flag is `true` **or `unknown`**, never silently excluding
   `unknown` as if it were `false` — and the response tags each result's flag as
   `true` / `unknown` so the agent can say "unconfirmed" rather than implying certainty.
5. `entity_type` filter, optional (gap in the first draft, closed here): a clinician asking
   "find an endocrinologist" almost always means an individual practitioner, but the first
   draft's search had no way to exclude organization-type NPIs (entity_type=2, e.g. a hospital
   system that also carries an Endocrinology taxonomy) from surfacing ahead of an individual.
   Rather than bake a default preference into the ranking logic — which would break the
   "distance is the only rank key" simplicity principle above — `search_providers_near` gains
   an optional `entity_type: "individual" | "organization" | null` filter param (default
   `null` = unrestricted). Whether to apply it is pushed up to `provider-search-agent`'s NL
   decomposition (FR8): the agent infers "endocrinologist" → `individual` the same way it
   already infers a taxonomy code, and states that inference in its rationale rather than the
   deterministic tool silently guessing it.

## 5. Persistence decision

**Postgres-only this phase, behind the `LocationSearchPort` and a `ProviderRepository`
interface.** This mirrors Phase 2's C3 decision ("Postgres behind a repository
interface; Bigtable/Firestore = scale swap") rather than re-litigating it.

Trade-offs considered:

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Postgres only | One store to run/operate; curated-subset scale doesn't need more; ports isolate future swaps | Won't demonstrate polyglot patterns this phase | **Chosen** |
| + document/search store for high-cardinality key reads | Real perf story if `get_provider`-by-NPI volume grows huge | No such volume this phase; second store to run for a problem that doesn't exist yet | Deferred |
| + Neo4j for provider↔org↔location↔network graph | Real value once network/affiliation modeling (a separate future initiative) needs multi-hop queries | No graph-shaped queries exist yet — Phase 3 has no network data (out of scope, PRD §7) | Deferred, revisit when network data is in scope |

## 6. Ingestion pipeline

Manually re-run, one-time-per-state seed (no scheduler, no CDC — matches the Phase 2
data-prework pattern of a re-runnable script rather than a live pipeline):

```
data/scripts/provider_ingest/
  fetch_nppes.py            # NPI Registry API pull, paginated, per state
  fetch_nucc_taxonomy.py    # NUCC CSV download + parse into taxonomy_reference rows
  fetch_zcta_centroids.py   # Census Gazetteer ZCTA file → zip_centroids rows
  run_ingestion.py          # orchestrates the above, writes directly to Postgres
```

**Correction from the first draft (M3):** §1's architecture diagram always showed the
ETL writing directly to Postgres; this section's prose contradicted it, saying
`run_ingestion.py` "calls provider-registry-service upsert API." That API was never
specified anywhere else in this doc and would exist for exactly one caller — the same
"don't build a shared client for a single caller" reasoning §9 already applies to
`client/clinical` applies here too. Resolved in favor of the diagram: `run_ingestion.py`
writes directly to Postgres via `psycopg`, no HTTP layer. `provider-registry-service`
gains no write endpoints from this milestone.

`run_ingestion.py --states NC,CA,MT` (the curated set decided in PRD §9 — density contrast, not
demo-data alignment) is what `provider-curation-agent` invokes
and then narrates. Re-running is idempotent: `upsert_golden_record` keys on NPI, and an
`ingestion_runs` row is written per invocation so lineage always shows which run last
touched a record.

**Real-world gotcha found in M3, not assumed:** the live NPPES Read API rejects a
`state`-only query — `state=NC` alone returns `{"errors":[{"description":"Field state
requires additional search criteria", ...}]}`. `fetch_nppes.py` works around this by
iterating a curated list of `taxonomy_description` values combined with `state`,
deduping results by NPI — which also means a "curated by geography" pull is, in
practice, always curated by geography *and* whichever taxonomy terms the query list
covers. Widening taxonomy coverage later is just growing that list, not a schema change.

**Real-world gotcha on deactivation status:** every sampled live-API query during M3
returned `basic.status: "A"` (active) — never anything else, across hundreds of sampled
records. The live Read API appears not to surface deactivated NPIs at all; CMS's
deactivation-date/reason fields are documented for the **bulk dissemination file**, not
confirmed present on this endpoint. Consequence: this ingestion path sets
`npi_status = 'active'` for everything it writes — §4.1's `npi_status` column and
default-exclusion policy are real, tested infrastructure (M2), just not yet exercised by
live data, since the live API gives us no deactivated records to exercise it with. Not
a blocker — the bulk file remains explicitly out of scope this phase (PRD §7) — but
worth being honest that "provider deactivation, verified end-to-end against real data"
isn't yet true, only "the schema and filter are ready for when it is."

**Where incremental/CDC would fit later:** NPPES publishes weekly deactivation/update
files in addition to the monthly full file — a later initiative could poll those and run
`run_ingestion.py` on a schedule (Cloud Scheduler → Cloud Run job), replacing "manual
re-run" with "weekly refresh," without changing the ingestion functions themselves.

## 7. Authoritative data sources

| Source | Provides | Access | Cadence | Key gotchas |
|---|---|---|---|---|
| **NPPES NPI Registry** (CMS) | NPI, entity type, name/org name, practice + mailing address, up to 15 taxonomy codes (one primary), phone, enumeration/update dates | **Verified live, M3:** `https://npiregistry.cms.hhs.gov/api/?version=2.1` — no key, JSON, 200 results/page + `skip` pagination. **A bare `state` filter is rejected** ("Field state requires additional search criteria") — must be paired with `taxonomy_description`, `city`, `postal_code`, `first_name`/`last_name`, or `organization_name`; `fetch_nppes.py` pairs `state` with a curated `taxonomy_description` list (§6). (Full bulk CSV also exists, ~9GB — not used this phase per the curated-subset decision.) | API reflects near-real-time registry; bulk file refreshes monthly + weekly incremental | **No "accepting new patients" field** — ships as `unknown` this build rather than guessing (§15). **`basic.status` observed as `"A"` on every sampled record (M3, hundreds sampled) — never anything else**; deactivated NPIs don't appear to surface via this endpoint at all (§6). Org-type (entity_type=2) addresses may be a facility, not an individual's practice — both types are ingested but tagged so callers can distinguish. Address quality varies (PO boxes, billing addresses); not solvable from NPPES fields alone. |
| **NUCC Health Care Provider Taxonomy** | Hierarchical code set: Grouping → Classification → Specialization, 10-char code, definition | **Verified live, M3:** CSV at `https://www.nucc.org/images/stories/CSV/nucc_taxonomy_260.csv` (current version **26.0**, 883 codes, 529KB) — free, no auth, no license click-through needed for this kind of read/redistribution use (the license-request form on nucc.org is for vendors embedding the code set in commercial products). Columns: `Code, Grouping, Classification, Specialization, Definition, Notes, Display Name, Section`. | ~2 releases/year (annual + mid-year) | Version drift — codes are occasionally deprecated/split between releases; `taxonomy_reference.nucc_version` pins which release a row came from. |
| **Census Bureau Gazetteer ZCTA file** | ZIP Code Tabulation Area centroid (`INTPTLAT`/`INTPTLONG`) | **Verified live, M3:** `https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_zcta_national.zip` — free, public domain, tab-delimited text inside the zip. | Refreshed with each decennial + intercensal release (2024 vintage confirmed current at M3) | ZCTA ≠ USPS ZIP exactly (Census-drawn approximation of ZIP delivery areas) — acceptable for a proximity *stub*, documented as an approximation. |
| **US Census Geocoder API** | Full street-address → lat/long geocoding | Free, no key | Live | Not needed for MVP (ZIP centroid suffices per the PRD's simplicity requirement) — noted as the natural future upgrade for precise address-level input instead of ZIP-centroid approximation. |
| **HL7 Da Vinci PDex Plan-Net IG** | *Not a data source* — the real published FHIR standard (Practitioner/PractitionerRole/Organization/Location/HealthcareService) for provider-directory interoperability | N/A | N/A | Registry uses a custom schema, not FHIR resources, this phase (see §9) — Plan-Net is the natural alignment point if the registry becomes FHIR-native later. Flagging for awareness, not adopting now. |

**Open, unresolved: `accepting_new_patients`.** NPPES does not carry this field. CMS's
Care Compare / Medicare Physician & Other Practitioners public dataset *may* have partial,
Medicare-specific coverage, but I have not verified current availability, schema, or NPI
coverage — marking this **to verify** rather than assuming. Until verified, the schema
and API keep the field nullable/`unknown` (§4.1, §4.3) rather than guessing a source.

## 8. MCP server — component, contracts, transport, wiring

**This is the actual protocol boundary the phase exists to build.** Python, official
`mcp` SDK, stdio transport (local process, zero cost, matches the NFR exactly — "stdio is
fine, HTTP/SSE optional").

### 8.1 Server side (`provider-mcp-server`)

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

server = Server("provider-search")

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(name="resolve_specialty", description="...", inputSchema=RESOLVE_SPECIALTY_SCHEMA),
        types.Tool(name="search_providers_near", description="...", inputSchema=SEARCH_SCHEMA),
        types.Tool(name="get_provider", description="...", inputSchema=GET_PROVIDER_SCHEMA),
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    result = await registry_client.dispatch(name, arguments)   # httpx call to provider-registry-service
    return [types.TextContent(type="text", text=json.dumps(result))]

async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())
```

`registry_client.dispatch` is a thin httpx wrapper calling
`provider-registry-service`'s internal HTTP API — the same "call the deterministic
service over HTTP, don't import it" pattern `mcp-agent` already uses for
`triage-service`. This keeps the MCP server stateless and focused purely on protocol
translation. `RESOLVE_SPECIALTY_SCHEMA`/`SEARCH_SCHEMA`/`GET_PROVIDER_SCHEMA` above are
concrete JSON Schema objects, not placeholders — see §8.3 for their actual contents.

### 8.2 Client/host side (`provider-search-agent`)

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

params = StdioServerParameters(command="python", args=["-m", "provider_mcp"])

async with stdio_client(params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()                     # MCP handshake
        tools = await session.list_tools()               # tools/list — real discovery, not a hardcoded list
        # tools are fed to Claude as tool definitions; the Anthropic tool-use loop
        # decides which to call based on the NL request
        result = await session.call_tool("search_providers_near", args)   # tools/call
```

The agent spawns the MCP server as a child process over stdio and does real discovery —
it does not hardcode `TOOL_DEFINITIONS` the way `mcp-agent/src/agent/tools.py` does
today. That hardcoded-vs-discovered distinction *is* the protocol boundary this phase
is meant to prove out.

### 8.3 Tool contracts

The first draft left these as prose sketches with placeholder schema constants
(`RESOLVE_SPECIALTY_SCHEMA`, etc.) — not implementation-ready, and noticeably less rigorous
than Phase 2's R17.7 "canonical schemas with committed example payloads." Fixed here: concrete
JSON Schema for every tool's input, and a concrete example response for every tool.

**Contract versioning.** MCP has no first-class endpoint-versioning concept the way a REST
path does — the tool *name* is the stable contract identifier. Rule for this build: a
backward-compatible change (new optional field, widened enum) edits the schema in place; a
breaking change (removed/renamed/re-typed field, narrowed enum) ships as a new tool name with
a numeric suffix (e.g. `search_providers_near_v2`) rather than silently changing the existing
one — so an already-registered MCP client never has a tool's behavior change out from under it
between calls to `tools/list`. `provider-registry-service`'s internal HTTP routes are prefixed
`/v1/...` for the same reason, even though `triage-service` today doesn't version its routes —
a deliberate, small improvement for a new service, not a retrofit demanded of existing ones.

**`resolve_specialty`**

```jsonc
// input schema
{ "type": "object", "required": ["query"], "additionalProperties": false,
  "properties": { "query": { "type": "string", "minLength": 1, "maxLength": 200 } } }

// example call
{ "query": "endocrinologist" }

// example response (success — see §8.4 for the ambiguous/no-match cases)
{ "query": "endocrinologist", "matches": [
    { "code": "207RE0101X", "grouping": "Allopathic & Osteopathic Physicians",
      "classification": "Endocrinology, Diabetes & Metabolism", "specialization": null,
      "score": 0.94, "nucc_version": "24.1" } ] }
```

**`search_providers_near`**

**Corrected in M6, not as originally sketched here.** The first draft's `location` schema
used `oneOf` (zip-branch vs. lat/lon-branch) to express "exactly one of these two shapes."
Real testing against live Claude found this made the model send `location` as a **JSON-
encoded string** (`'{"zip": "27514"}'`) instead of a native object, on every single attempt
across two independent bugfix tries (first adding an explicit top-level `"type": "object"`
hint alongside the `oneOf` — no change; the model kept stringifying it) — a real, reproducible
LLM tool-calling quirk with `oneOf`-typed nested-object parameters, not a hypothetical
concern. Fixed by flattening `location` to a plain object with three optional fields and
moving the "exactly one of zip, or (lat and lon)" rule to `provider-registry-service`'s
existing Pydantic validator (`LocationInput`'s `model_validator`, §4 — which already enforced
this independently of the MCP-level schema) rather than re-adding it at the JSON-Schema
level. Verified the cross-field rule still rejects malformed input end-to-end after the
change (`{}` and `{zip + lat + lon together}` both still return `400 validation_error`).

```jsonc
// input schema
{ "type": "object", "required": ["location", "taxonomy_codes"], "additionalProperties": false,
  "properties": {
    "location": { "type": "object", "additionalProperties": false,
        "properties": { "zip": { "type": "string", "pattern": "^[0-9]{5}$" },
          "lat": { "type": "number", "minimum": -90, "maximum": 90 },
          "lon": { "type": "number", "minimum": -180, "maximum": 180 } } },
    "taxonomy_codes": { "type": "array", "items": { "type": "string" }, "minItems": 1, "maxItems": 10 },
    "radius_miles": { "type": "number", "exclusiveMinimum": 0, "maximum": 200, "default": 25 },
    "limit": { "type": "integer", "minimum": 1, "maximum": 50, "default": 10 },
    "accepting_new_patients": { "type": ["boolean", "null"], "default": null },
    "entity_type": { "type": ["string", "null"], "enum": ["individual", "organization", null], "default": null } } }

// example call
{ "location": { "zip": "27514" }, "taxonomy_codes": ["207RE0101X"], "radius_miles": 15,
  "limit": 10, "accepting_new_patients": true, "entity_type": "individual" }

// example response (success)
{ "origin": { "lat": 35.9, "lon": -79.05, "resolved_from": "zip:27514" },
  "count": 1,
  "results": [ { "npi": "1234567890", "name": "Jane Doe, MD", "entity_type": 1,
      "npi_status": "active",
      "taxonomy_code": "207RE0101X", "taxonomy_description": "Endocrinology, Diabetes & Metabolism",
      "address": { "address_1": "100 Main St", "city": "Chapel Hill", "state": "NC", "zip5": "27514" },
      "distance_miles": 4.2,
      "accepting_new_patients": "unknown",
      "lineage": { "source": "NPPES", "source_pulled_at": "2026-08-01T00:00:00Z", "ingestion_run_id": "..." } } ] }
```

**`get_provider`**

```jsonc
// input schema
{ "type": "object", "required": ["npi"], "additionalProperties": false,
  "properties": { "npi": { "type": "string", "pattern": "^[0-9]{10}$" } } }

// example call
{ "npi": "1234567890" }

// example response (success)
{ "npi": "1234567890", "entity_type": 1, "name": "Jane Doe, MD", "npi_status": "active",
  "addresses": [ {...} ], "taxonomies": [ {...} ],
  "lineage": { "source": "NPPES", "source_pulled_at": "...", "ingestion_run_id": "..." } }
```

### 8.4 Error taxonomy

The first draft's FR9 said the agent "surfaces [failures] plainly," without defining what a
tool actually returns when something goes wrong — no equivalent of Phase 2's R17.6. Fixed here
with the same shape Phase 2 used (disjoint response classes, each with a fixed
status/persisted-or-not rule), adapted from a decisioning domain to a search domain:

| Class | When | MCP tool result | Registry-service HTTP | Notes |
|---|---|---|---|---|
| **Success — results found** | Valid request, ≥1 match | Normal result, `isError` absent/false | `200` | §8.3 examples above |
| **Success — no results** | Valid request, 0 matches | Normal result, `count: 0, results: []` — **not an error** | `200` | Distinguishing "found nothing real" from "something broke" is the whole point of FR9 — an empty result must never be dressed up as, or confused with, a failure the agent should paper over |
| **Ambiguous input** | `resolve_specialty` has no confidently-dominant match, or a ZIP has no centroid | Normal result, `status: "ambiguous"` + candidates/reason — **not an error** | `200` | This is a legitimate outcome the agent must resolve by asking the clinician (FR9), not a system fault — same reasoning as the row above |
| **Validation error** | Malformed input (bad ZIP pattern, radius out of range, unknown taxonomy code format) | `isError: true`, `error_type: "validation_error"`, `field`, `message` | `400` | No query executed |
| **Not found** | `get_provider` called with an NPI absent from the registry | `isError: true`, `error_type: "not_found"` | `404` | Distinct from "no results" above — a bad/stale NPI is a different signal than a legitimate empty search |
| **Upstream unavailable** | `provider-registry-service` unreachable or Postgres down | `isError: true`, `error_type: "upstream_unavailable"` | `502`/`503` | Agent must say so plainly and stop (existing guardrail, §3.1) — never silently retries into a fabricated answer |

## 9. Integration with the existing platform

- **Kong:** no new edge route. `provider-registry-service` and `provider-mcp-server`
  join the internal plane, following the `rxclaim-emulator` precedent exactly.
- **FHIR/HAPI:** not used to store provider data this phase. The registry is a
  purpose-built schema, not FHIR `Practitioner`/`Organization`/`Location` resources —
  NPPES data doesn't need to round-trip through HAPI to support proximity search, and
  building FHIR-native resources is real extra engineering for a feature that's mostly
  SQL-based geo filtering. **Open question:** if a FHIR-shaped provider directory is
  wanted later (e.g. to expose via the existing FHIR-facing gateway route), the natural
  standard to align to is **HL7's Da Vinci PDex Plan-Net IG** — the real, published
  standard for exactly this — flagged for awareness, not adopted now.
- **client/clinical:** not extended this phase. It's scoped to wrapping HAPI FHIR
  resources (`fhir_client.py`); the provider registry isn't a FHIR resource. Rather than
  overload its contract or spin up a new shared client package for a single caller,
  `provider-mcp-server` calls `provider-registry-service` directly via httpx — the
  simplest option given only one caller exists. **Open question, flagged not assumed:**
  revisit if a second internal caller of the registry API appears.
- **GKE / Cloud Run:** `provider-registry-service` and `provider-mcp-server` deploy to
  Cloud Run, `ingress: internal`, matching Phase 2's hybrid pattern (GKE untouched for
  Phase 1). Local/demo runs both via a `docker-compose` profile, matching the
  Phase 1/2 pattern, and via direct local execution (stdio MCP transport is inherently
  a local-process boundary — see the NFR's cloud-transport non-goal in the PRD).

## 10. Patterns applied

- **Façade** — `provider-registry-service` is a façade over Postgres + the
  taxonomy/location modules, giving the MCP server (and any future caller) one clean
  internal contract, same role `claims-service` plays in Phase 2.
- **Anti-Corruption Layer** — the ingestion pipeline's `normalize_taxonomy` /
  `fetch_nppes_state` parsing functions are a lightweight ACL translating NPPES's field
  names/shapes into the canonical schema; no legacy wire format to translate this time
  (unlike `rxclaim-emulator`'s fixed-width records), so it's a lighter-weight instance of
  the pattern than Phase 2's.
- **Strangler-Fig** — not applicable; this is net-new, not a legacy replacement. Would
  become relevant if a later initiative migrates the platform off a paid provider-directory
  vendor elsewhere in the org.
- **Contract-first** — the three MCP tool schemas are defined explicitly up front (MCP
  requires `inputSchema` anyway) and mirrored in the registry service's Pydantic models
  so the two don't drift. Being honest that `triage-service` today doesn't practice
  formal contract-first beyond FastAPI's auto-generated docs — Phase 3 raises the bar
  where MCP forces it to, without introducing a new OpenAPI-generation toolchain the
  rest of the platform doesn't have yet.

## 11. Observability / SLOs

- Structured logs: never log a raw patient ZIP/coordinate in plaintext — log a
  state/region bucket instead, or a truncated/hashed form, consistent with PHI-safe
  handling of the search *input* (provider *output* data is public). Enforced via the
  shared `sanitize_location()` helper named in §12.1, not left as an unenforced convention.
- Groundedness check (automated, not manual): every NPI appearing in a
  `provider-search-agent` transcript must resolve via `get_provider` — a referential
  smoke test, same spirit as Phase 2's idempotency verification.

**SLIs defined now; SLO/error-budget deferred — named explicitly rather than left as one
latency KPI plus "no formal SLO."** No production traffic exists yet to set a real budget
against, but the *indicators* a future SLO would be built on are specified now so
instrumentation lands correctly from M2, not retrofitted later:

| SLI | Definition | Measured from |
|---|---|---|
| Availability | % of `search_providers_near` / `resolve_specialty` / `get_provider` calls completing as a defined success or no-result response (§8.4) — validation/not-found errors on well-formed test traffic count against it, upstream-unavailable errors always do | MCP `tools/call` receipt → response, rolling 5-minute window |
| Latency | p50/p95/p99 histogram, `tools/call` receipt → response | Same window |
| Zero-result rate | % of successful `search_providers_near` calls returning `count: 0` | Same window — a leading indicator of curated-data coverage gaps, not itself a failure |
| MCP conformance | % of agent sessions completing `initialize → tools/list → tools/call` without a protocol-level error | Per session |
| Ingestion coverage | % of pulled NPPES records per run resolving a coordinate + ≥1 taxonomy code | Per `ingestion_runs` row (PRD §8 KPI) |

An SLO (a target on Availability/Latency) and an error budget are **not set this build** —
consistent with Phase 2's own posture for pre-launch internal services — but the table above
is what a future SLO would reference, so setting one later is a target-setting exercise, not
new instrumentation work.

## 12. Security / compliance

- No PHI is stored in the registry — provider data is CMS public record. The only
  sensitive datum in the request path is the patient's search location; it's never
  persisted beyond the request (no raw-search log table).
- East–west auth between `provider-mcp-server` and `provider-registry-service`: **none,
  verified against the actual Phase 2 code rather than assumed.** `claims-service`'s HTTP
  clients to `rxclaim-emulator`, `triage-service`, and `fhir-service` send no API
  key/bearer/shared-secret header (`HttpTriageClient.java:50-55`,
  `HttpLegacyClient.java:23-29`, `HapiFhirClient.java:24-31`); trust is network-isolation
  only (`ingress=internal` + IAM invoker + VPC connector, `docs/phase2/plan.md:36-40,167-170`).
  Phase 3 follows the same pattern — no application-layer auth to build or maintain.
- Agent API key handling follows the existing `ANTHROPIC_API_KEY`/`CLAUDE_API_KEY`
  convention, never logged.
- Agent guardrails recap: never fabricate a provider fact; always carry lineage; surface
  "unknown" rather than guessing (§3.1).

### 12.1 Threat model for the internal boundary

The first draft copied Phase 2's "no app-layer auth, network isolation only" decision without
justifying it for Phase 3's specific data flow — reused the mechanism without restating why
it's still sufficient here. Phase 2's internal payload is a claim; Phase 3's is a patient's
approximate location tied to a clinical need, which is a materially different sensitivity
profile even though the *auth mechanism* carries over unchanged. Reasoning, explicit:

- **What's actually protected.** Not the provider data (public record). Two things: (1) the
  search **input** — a patient's location — per the existing PHI-safe handling rule (PRD §6);
  (2) secondarily, the **aggregate query pattern** (which ZIPs, which specialties, what volume,
  over time) — even without any single request containing PHI, a scraped time series of a
  clinic's referral searches is itself a signal about that clinic's patient population, and
  isn't defended by "the response body is public data."
- **Trust boundary assumption, named rather than implied.** No-app-layer-auth is only as safe
  as the Cloud Run `ingress=internal` + IAM invoker + VPC connector configuration actually
  restricting callers to specifically-authorized services. That configuration lives in
  Terraform, not in this repo's Python/Java code — it's an **operational dependency**, and
  Phase 3b's Terraform apply must get it right for this decision to hold. Named as an explicit
  Phase 3b acceptance criterion in §13.1, not assumed to fall out of "internal-only" as a label.
- **Abuse cases considered:**
  - *Compromised or over-permissioned internal caller* (another Cloud Run service in the same
    VPC that shouldn't have registry access but does, due to an overly broad IAM binding or
    VPC connector scope) — mitigated only by correct IAM scoping at deploy time (Phase 3b), not
    by anything in this codebase. Accepted risk for an internal-only prototype; would need
    per-service IAM service accounts (not a shared one) before this goes beyond prototype scope.
  - *Query-volume scraping* — nothing in this design rate-limits `provider-registry-service`
    internally (Kong's rate-limiting is edge-only and this service isn't on the edge). A
    compromised or buggy internal caller could hammer it unboundedly. **Cheap, concrete
    mitigation added to M2** (not deferred to a doc note): a coarse per-caller rate limit via
    FastAPI middleware on `provider-registry-service` — defense-in-depth, not a substitute for
    correct IAM scoping.
  - *Replay* — no auth token exists to replay; a captured request is just a repeatable read
    against public data. Not a meaningful risk given nothing PHI is returned or stored.
  - *Log/telemetry leakage of the raw search location* — the "never log in plaintext" rule
    (PRD §6) is currently just a sentence with no enforcement mechanism named. Fixed here: it's
    enforced the way this codebase already enforces PHI-safe logging elsewhere — a shared
    `sanitize_location()` helper used in `provider-registry-service`'s request-logging
    middleware (state/region bucket only, per §11), not a policy left to individual call sites
    to remember.

## 13. Milestone plan

Internal work is tracked as milestones, not sub-phases — no "Phase 3.x" labels anywhere below.
Following Phase 2's *intent* (design + stub the cloud posture at every milestone; defer the
live `terraform apply` to its own follow-on phase), every milestone that adds a deployable
component also produces a **cloud-readiness stub** — a Dockerfile and a per-service Terraform
module sketch, validated with `terraform validate`/`plan` but never applied.

> ### ⚠️ Do not read "cloud-readiness stub" as "Phase 3b is just `terraform apply`"
>
> The first draft of this doc claimed exactly that — "Phase 3b is a deploy of already-proven
> config, not a redesign" — and that claim was wrong on its own evidence: Phase 2 said the
> identical thing (`decisions.md` D8: "cloud IaC/stubs/tests ship from each milestone") and
> then had to publicly retract it. `docs/phase2/plan.md`'s own "Cloud-delivery gap" callout
> found that per-service Cloud Run stubs shipping on schedule (M2, M3 did ship theirs) still
> left **no root Terraform module** wiring them together (Cloud SQL/Neon, Secret Manager,
> Artifact Registry, VPC connector, IAM), **no deploy script**, and **no executed cloud smoke
> test in CI** — and concluded "Phase 2b is not 'terraform apply, not new construction'... Real
> authoring work remains."
>
> Phase 3 did not repeat that specific gap — **M7 actually built all three**, not just named
> them as future milestone-tracked items:
> 1. **A root Terraform module** (`infra/terraform/main.tf`) that actually composes the
>    per-service stubs (`module` blocks referencing M2/M3/M5's directories) plus the pieces
>    Phase 2's gap analysis named as missing — Artifact Registry, a Secret Manager secret —
>    with the wiring between them (one shared image repo, not one per service). `terraform
>    validate` passed for real. Two things named as deliberately excluded rather than silently
>    omitted: no Cloud SQL resource (Postgres is Neon, matching how fhir-service already
>    handles it — checked, not assumed, that no `.tf` file anywhere in this repo provisions a
>    database directly); no VPC connector (Neon's public endpoint + TLS doesn't need one).
> 2. **`deploy-phase3.sh`** — a real, complete script (terraform apply → build/push the three
>    images → re-apply so Cloud Run picks up the digests), `bash -n` and `shellcheck` clean
>    (zero issues, same bar as the existing `deploy.sh`). Not executed — Phase 3b hasn't
>    started — but it's the script Phase 2 never wrote, not a placeholder for one.
> 3. **An executed cloud smoke test in CI**, not just "a stub exists": `.github/workflows/
>    tests.yml` gained a `phase3-terraform` job running `terraform validate` (matrix across
>    all four Phase 3 Terraform directories) on every push/PR — deliberately `validate`, not
>    `plan`: `plan` needs live GCP provider credentials this project doesn't provision, so
>    `validate` is the real, zero-cost, credential-free check that's actually achievable, named
>    as such rather than overclaiming a `plan` this CI job can't actually do for free
>    (decisions.md). A `phase3-python` job also runs the full Phase 3 test suite against a
>    real Postgres service container in CI — not just locally, and not self-skipping there.
>
> Even with those three built, **Phase 3b is still real authoring work**, not a single command
> — `terraform apply`, `deploy-phase3.sh`, and a live GCP project have never actually been
> exercised together end-to-end (only `validate`, never `plan`/`apply`, per point 3 above). The
> honest claim is "the design, per-service config, and composition are real and validated," not
> "nothing is left to build." Treat every "Cloud-readiness stub" cell below as a **design
> commitment**, and check the repo before citing one as a delivered artifact — the same caution
> Phase 2's own
> docs now carry.

| Milestone | Status | Scope | Cloud-readiness stub |
|---|---|---|---|
| M1 | ✅ Done (PR #40) | This PRD + design doc, committed locally (docs-first, matches Phase 2) | n/a — docs only |
| M2 | ✅ Done (PR #41) | `provider-registry-service`: schema/migrations, `LocationSearchPort` + `HaversineSqlLocationSearch`, taxonomy resolve endpoint, coarse per-caller rate-limit middleware (§12.1 defense-in-depth), unit tests against a small hand-written fixture (not real data yet) | Dockerfile + Terraform Cloud Run module sketch, `ingress = "internal"` — `terraform validate` passed |
| M3 | ✅ Done | Ingestion scripts (deterministic): NPPES pull for the pilot state (NC), NUCC load, ZCTA load, upsert — verified against real data | Terraform sketch for a manually-triggered Cloud Run Job (matches the one-time-seed decision, PRD §6) — `terraform validate` passed, not applied |
| M4 | ✅ Done (PR #43) | `provider-curation-agent`: wraps M3 with an AI run-summary; expand ingestion to the full curated set (NC, CA, MT) | n/a — CLI tool, no new deployable surface |
| M5 | ✅ Done (PR #44) | `provider-mcp-server`: real MCP server (stdio), wired to the registry service; integration test proving the actual `initialize`/`tools-list`/`tools-call` handshake | Dockerfile + Terraform packaging stub (Artifact Registry only, deliberately **not** a Cloud Run Service resource — see §13.1: stdio doesn't cross a network boundary, so a Cloud Run Service resource here would validate cleanly while being undeployable) — `terraform validate` passed |
| M6 | ✅ Done (PR #45) | `provider-search-agent`: real MCP client/host, Anthropic tool-use loop, groundedness eval suite | n/a — CLI tool; spawns the MCP server as a local child process |
| M7 | ✅ Done (PR #46) | `docker-compose` demo profile bundling all four new components; end-to-end local verification | **Root Terraform module** (`infra/terraform/`) composing the M2/M3/M5 per-service stubs + `deploy-phase3.sh` + an executed cloud smoke test wired into CI (stub-target, no live spend) — the three items the callout above names explicitly, not left implied, and all three actually built this time (Phase 2 named the same three and built none of them). `terraform validate` across everything (still not applied) — `terraform plan` deliberately excluded from the CI smoke test; see the decisions.md entry for why. |

**Verified, per milestone** (updated as each lands — see each PR for the full command output,
not just the claim):

- **M2** (PR #41): full root `pytest` — 147 passed (all pre-existing suites + 34 new), run
  against a locally installed Postgres 16, not mocked. DB-free tests (validation/taxonomy/
  rate-limit) independently confirmed to pass with no `DATABASE_URL` set at all. DB-backed
  tests independently confirmed to skip cleanly (not error) when Postgres is unreachable.
  `terraform validate` passed. `docker compose config` confirmed the default (no-profile)
  stack unchanged and the new `phase3` profile correctly scoped.
- **M3** (PR #42): full root `pytest` — **159 passed** (147 from M2 + 12 new: `fetch_nppes` record-
  parsing/pagination/dedup/wrong-state-filter tests, `fetch_nucc_taxonomy` and
  `fetch_zcta_centroids` parsing/join tests — all mocked HTTP, no network — plus 2 DB-backed
  `run_ingestion` idempotency tests, self-skip confirmed when Postgres is unreachable). Real
  ingestion run against local Postgres 16, NC pilot state: **5,040 unique real providers**
  ingested (3,371 individual / 1,669 organization, spanning 348 distinct NUCC taxonomy codes),
  **883/883** NUCC codes loaded, **3,025** ZIP centroids loaded (NC/CA/MT). Re-run confirmed
  idempotent (0 added, 5,040 updated on the second pass). End-to-end verified live through
  `provider-registry-service`'s actual HTTP API (not just the DB layer) — a real search near
  ZIP 27514 returned real UNC Chapel Hill endocrinologists with correct lineage. Coordinate
  resolution: **94.2%** (4,747/5,040) — below the PRD's original assumed ≥99%, revised to a
  measured ≥90% target (decisions.md P12). `terraform validate` passed for the ingestion Cloud
  Run Job stub.
- **M4** (PR #43): full root `pytest` — **172 passed** (159 from M3 + 13 new: 6 deterministic
  `summarize.render_summary` tests, no DB needed; 7 `IngestionClient`/`execute_tool` tests, 5
  mocked-subprocess/no-DB + 2 DB-backed with self-skip confirmed). **Real bug found and fixed
  while running this milestone's own tests**: `provider-curation-agent/tests/test_tools.py`
  silently collided with `claims-agent/tests/test_tools.py` under `--import-mode=importlib` —
  both `tests/` packages resolve to the identical dotted module name `tests.test_tools`, so
  Python's `sys.modules` cache served claims-agent's already-imported module for both,
  meaning 4 of claims-agent's tests silently ran *twice* under two different reported paths
  while all 7 of this milestone's real tests never ran at all — with no error, no warning, a
  passing exit code throughout. Confirmed via a `find`-based repo-wide filename-collision
  check (only this one pair existed) and fixed by renaming to `test_ingestion_tools.py` — the
  general lesson (test filenames must be repo-unique, not just per-package-unique, given this
  pytest.ini's `--import-mode=importlib` + per-package `tests/__init__.py` setup) is worth
  keeping in mind for future milestones' test files. Real agent run (deterministic path):
  ingested **12,582 total providers** across NC/CA/MT (5,040 NC + 5,519 CA + 2,023 MT — CA and
  MT freshly fetched live from NPPES this run), 396 anomalies flagged (all `missing_coordinate`,
  consistent with M3's measured ZCTA-gap rate). Idempotency reconfirmed: a second real run
  (this time with the actual Anthropic API via `CLAUDE_API_KEY`, not `--no-llm`) reported 0
  added / 12,582 updated and correctly narrated the real anomaly breakdown without inventing
  any counts.
- **M5** (PR #44): full root `pytest` — **186 passed** (172 from M4 + 14 new: 7 `registry_client`
  tests, mocked HTTP, no network; 7 real MCP-handshake integration tests). Checked for the
  test-filename collision from M4 before trusting the count this time
  (`find . -name "test_*.py" | ... | uniq -c` — none found). Self-skip confirmed for the
  DB-backed handshake tests (155 passed, 31 skipped when Postgres unreachable). **The real MCP
  protocol handshake verified end-to-end, not simulated**: `provider-mcp-server` spawned as a
  genuine subprocess over stdio, `provider-registry-service` spawned as a genuine subprocess
  over HTTP, a real `mcp` SDK `ClientSession` driving `initialize` → `tools/list` → `tools/call`
  against both — including the SDK's own automatic JSON-Schema input validation rejecting a
  malformed NPI (`isError: true`) and a real `not_found` (§8.4) path, both exercised for real,
  not asserted from documentation. Separately verified by hand against the full **12,582-real-
  provider** dataset (all three curated states): a live `search_providers_near` call for a Los
  Angeles ZIP returned three real Family Medicine physicians through the actual MCP protocol.
  `terraform validate` passed for the packaging stub (deliberately not a Cloud Run Service
  resource — see the milestone table's Cloud-readiness cell). Confirmed live (not assumed) that
  the installed `mcp` SDK already ships `sse`/`streamable_http`/`websocket` transport modules
  alongside `stdio` — Phase 3b's transport decision (§13.1) has real SDK support to build on.
- **M6** (PR #45): full root `pytest` — **196 passed** (186 from M5 + 10 new: 7 tool-use-loop
  unit tests with the Anthropic client and MCP session both mocked; 3 real groundedness-eval
  tests making genuine, billed Claude API calls). Checked for filename collisions before
  trusting the count (none). Self-skip confirmed for both prerequisites independently — no DB
  and no LLM key both produce clean skips (162 passed, 34 skipped together). **The groundedness
  eval is real, not simulated**: scripted NL queries run through the full real stack (real
  Claude, real `provider-search-agent` tool-use loop, real `provider-mcp-server` subprocess,
  real `provider-registry-service` subprocess, real Postgres), then every NPI the agent's final
  answer mentions is independently re-fetched via `get_provider` and asserted real — including
  a query with zero real matches, asserted to produce zero fabricated NPIs.
  **Two real bugs found and fixed by actually running live queries, not just the scripted
  eval set**: (1) Claude reliably serialized the `oneOf`-typed `location` parameter as a JSON
  string instead of a native object on 12/12 consecutive attempts — fixed by flattening the
  schema (decisions.md P17, §14 Risks). (2) Claude once transcribed `207RE0101X` as
  `207RE0101` (dropped the trailing "X") copying a code between tool calls, which silently
  produced a misleading zero-result response instead of an error — fixed by adding a
  `^[0-9A-Z]{9}X$` pattern verified against all 883 real NUCC codes (decisions.md P19,
  §14 Risks). Both confirmed fixed by re-running the exact real query that exposed them.
  Manually verified end-to-end against the full 12,582-provider dataset: a real Montana query
  correctly and honestly flagged the known `accepting_new_patients` data gap (never guessed);
  a real Los Angeles query returned 10 real endocrinologists with correct lineage after the
  taxonomy-code fix.
- **M7** (PR #46): full root `pytest` — **196 passed** (unchanged from M6 — M7 added no new
  Python packages/tests, only infra/Docker/CI). Self-skip reconfirmed (162 passed, 34 skipped
  with neither DB nor LLM key available). `terraform validate` passed for the new root module
  (`infra/terraform/`) and all three composed per-service modules; `deploy-phase3.sh` is
  `bash -n` and `shellcheck` clean. **All four Phase 3 Docker images actually built and run
  together for the first time this milestone** (previously each service was only verified via
  direct Python invocation, never through its own shipped Dockerfile): `docker compose build`
  succeeded for all four; `provider-curation-agent`'s real container ingested all three states
  (7,542 added + 5,040 updated = 12,582 total, matching M3/M4's numbers exactly) against a
  fresh `docker-compose` Postgres; `provider-search-agent`'s real container — which spawns
  `provider-mcp-server` as an internal child process, the most integration-heavy of the four
  images — correctly resolved "cardiologist" (retrying to "cardiovascular disease" after an
  initial weak match) and returned 10 real, correctly-grounded, correctly-sourced Los Angeles
  cardiologists over the real Docker network (`provider-search-agent` → spawned
  `provider-mcp-server` → HTTP → `provider-registry` → Postgres). One environment-specific
  finding, not a code bug: `docker compose run` silently swallowed stdout in this sandbox
  without the `-T` flag (disables pseudo-TTY allocation) — worth remembering for anyone
  scripting `docker compose run` non-interactively here, confirmed by isolating the exact same
  commands via `docker run -d` + `docker logs`, which reliably showed the real output `docker
  compose run` had been swallowing. `docker compose config` reconfirmed the default profile
  unchanged and `phase3` profile correctly scoped throughout.

### 13.1 Phase 3b — GCP cloud deployment (future, out of scope here)

Same intent as Phase 2b — but stated with the correction the callout above makes: this is
**real authoring work landing on top of M2–M7's stubs**, not a single command. Scope, once
started:

- `terraform apply` using M7's root module (`infra/terraform/main.tf`) — the module that
  actually composes `provider-registry-service`, `provider-mcp-server`, and the ingestion
  Cloud Run Job's per-service stubs, plus the shared Artifact Registry repo and Secret
  Manager secret — not the per-service stubs in isolation, which is exactly what Phase 2 had
  at this stage and found insufficient. **Corrected from the first draft**, which speculated
  a Cloud SQL instance and a VPC connector before the root module existed: neither is in the
  real module. Postgres is Neon (external SaaS, matching how fhir-service already handles it
  in Phase 1/2 — no Terraform-managed database anywhere in this repo); no VPC connector is
  needed since Neon is reached over its public endpoint with TLS, not a private network path.
  Setting the Secret Manager secret's actual value (the Neon connection string) is a manual,
  out-of-band step — `deploy-phase3.sh` prints the exact command, never runs it itself.
- Correctly scope IAM invoker bindings so the network-isolation-only trust assumption in
  §12.1 actually holds — an explicit acceptance criterion for this milestone, not an assumed
  side-effect of "ingress=internal" as a label.
- Actually run `terraform plan`/`apply` against a live GCP project — M7's CI smoke test
  deliberately only runs `validate` (no live credentials provisioned for CI), so `plan` and
  `apply` remain genuinely untested until Phase 3b, not just formally "left for later."
- **No new application-layer auth** — matches the verified Phase 2 pattern (PRD §9): internal
  calls carry no API key/bearer/shared-secret header; isolation is enforced entirely by Cloud Run
  ingress + IAM, not by the application.
- **Resolve the MCP transport question for real.** stdio only works when the client spawns the
  server as a local child process — it cannot cross a network hop. Two options, to be decided
  *in* Phase 3b, not here:
  (a) keep `provider-search-agent` CLI-only/local even after Phase 3b (simplest — mirrors
  `claims-agent`, which also isn't cloud-deployed) and let it reach the now-cloud-hosted
  `provider-mcp-server` only for local dev/demo, or
  (b) implement MCP's SSE/HTTP transport if a server-hosted agent becomes a real requirement.
  Default recommendation: (a), until something concrete forces (b). **Verified in M5, not
  assumed:** option (b) isn't blocked on SDK support — the installed `mcp` package (v1.28.1)
  already ships `mcp.server.sse`, `mcp.server.streamable_http`, and `mcp.server.websocket`
  alongside `mcp.server.stdio`. Whichever way Phase 3b decides is an application-code and
  deployment decision, not a missing-feature one.
- Live smoke tests against the deployed services, matching Phase 2b's verification bar.

## 14. Risks

- **`oneOf`-typed nested-object tool parameters are unreliable with live LLM tool-calling** —
  found real in M6, not hypothetical: Claude serialized a `oneOf`-typed `location` parameter
  as a JSON string instead of a native object on 12/12 consecutive attempts, even after adding
  an explicit `"type": "object"` hint. Fixed by flattening to optional fields + downstream
  cross-field validation (decisions.md P17). Worth remembering for any future tool schema in
  this project that's tempted to reach for `oneOf`/`anyOf` at the parameter level — prefer a
  flat object with validation pushed to the deterministic service behind the tool.
- **Unconstrained free-text-derived parameters can silently produce false negatives, not just
  fabrication** — found real in M6's manual verification: Claude transcribed a taxonomy code
  from one tool result into the next tool call with one character dropped
  (`207RE0101X` → `207RE0101`). With no format constraint on `taxonomy_codes`, this didn't
  error — it silently matched zero rows, and the agent correctly-but-misleadingly reported "no
  providers found" for a specialty with 10 real matches at that location. Not a grounding
  failure (nothing was fabricated), but a real usability/correctness gap worth naming
  separately from the `oneOf` finding above. Fixed by adding a verified `^[0-9A-Z]{9}X$`
  pattern (decisions.md P19) so a mistranscribed code becomes an explicit `validation_error`
  the model can see and retry from. General lesson: any tool parameter the model fills in by
  copying a value out of a prior tool result (not by reasoning from the user's request) is a
  transcription-error risk — constrain its format wherever the real data has one.
- **Test filenames must be repo-unique, not just per-package-unique** — found real in M4:
  `--import-mode=importlib` plus per-package `tests/__init__.py` means two identically-named
  test files in different packages (`claims-agent/tests/test_tools.py` and
  `provider-curation-agent/tests/test_tools.py`) resolve to the same dotted module name and
  silently collide via Python's `sys.modules` cache — one package's tests run twice under two
  reported paths, the other's never run, with no error and a passing exit code. Watch for this
  on every future milestone that adds a `tests/` directory; `find . -name "test_*.py" | xargs
  -n1 basename | sort | uniq -c | awk '$1>1'` catches it before it's silent.
- **`accepting_new_patients` data gap** — the single biggest open risk; may need to ship
  without it (always `unknown`) if no usable source is confirmed.
- **Provider staleness/deactivation between ingestion runs** (gap identified in review,
  closed at the schema/policy level in §4.1) — because ingestion is a manually re-run,
  one-time-per-state seed, a provider that becomes deactivated after a run won't be caught
  until the next manual re-run. `npi_status` filtering prevents an *already-known*
  deactivated provider from surfacing, but doesn't shrink the detection lag itself — only a
  scheduled refresh (explicitly out of scope this build, §6) would.
- **NPPES public API rate limits** — verified empirically in M3: ~30 requests over ~10s at a
  0.2s inter-request pacing hit no throttling (5,770 raw records across 10 taxonomy terms × 3
  pages). Still undocumented officially — the pacing is precautionary, not proven necessary.
- **ZCTA-vs-ZIP mismatch** — confirmed real in M3, not just theoretical: **94.2%** coordinate-
  resolution on the real NC pull (4,747/5,040), with a confirmed concrete example (Duke
  University Medical Center's ZIP 27710 has no ZCTA at all — a large institutional ZIP, exactly
  the case this risk predicted). PRD §8's KPI revised from an assumed ≥99% to a measured ≥90%
  (decisions.md P12) rather than leaving a KPI real data had already disproven.
- **Taxonomy synonym coverage** is inherently incomplete for a deterministic (non-LLM)
  matcher — confirmed real in M3: `resolve_specialty("endocrinologist")` against the full
  883-code set returns `status: "ambiguous"` (a nursing-taxonomy specialization scores above
  the intended physician code). Accepted trade-off for traceability; flagged as a real
  tuning opportunity for a future milestone (decisions.md P13), not fixed in M3.
- **Internal-boundary trust depends on correct IAM/VPC scoping at deploy time** (§12.1) —
  the no-app-layer-auth decision is only as sound as Phase 3b's Terraform gets that
  scoping right; named as an explicit Phase 3b acceptance criterion, not just a doc note.

## 15. Decisions (resolving the first draft's open questions)

Resolved using best judgement so build work isn't blocked. Each is reversible — flag any of
these if you want a different call before M2 starts. Full rationale for the first three lives in
PRD §9; restated briefly here for design-doc completeness.

1. **Curated states: North Carolina, California, Montana** — chosen for density contrast
   (moderate/mixed, dense urban, sparse rural), not for alignment with existing demo data (none
   was found to align to).
2. **`accepting_new_patients` ships permanently `unknown`.** No second source integrated this
   build; CMS Care Compare remains an unverified future candidate, non-blocking.
3. **`provider-search-agent` stays CLI-only**, matching `claims-agent` — no new HTTP entrypoint,
   no new Kong route, this build.
4. **No new shared `client/` package.** `provider-mcp-server` calls
   `provider-registry-service` directly via httpx — the only caller, so a shared client library
   would be premature abstraction.
5. **East–west auth: none, verified (not guessed).** See §12 — checked Phase 2's actual code;
   internal calls carry no application-layer auth, isolation is Cloud-Run-ingress-only. Phase 3
   follows the same pattern.
