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

```
providers
  npi                 char(10) PK
  entity_type         smallint        -- 1=individual, 2=organization
  first_name          text NULL
  last_name           text NULL
  organization_name   text NULL
  phone               text NULL
  is_sole_proprietor  boolean NULL
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
  fetch_nppes.py        # NPI Registry API pull, paginated, per state
  fetch_nucc_taxonomy.py    # NUCC CSV download + parse into taxonomy_reference rows
  fetch_zcta_centroids.py   # Census Gazetteer ZCTA file → zip_centroids rows
  run_ingestion.py          # orchestrates the above, calls provider-registry-service upsert API
```

`run_ingestion.py --states NC,CA,MT` (the curated set decided in PRD §9 — density contrast, not
demo-data alignment) is what `provider-curation-agent` invokes
and then narrates. Re-running is idempotent: `upsert_golden_record` keys on NPI, and an
`ingestion_runs` row is written per invocation so lineage always shows which run last
touched a record.

**Where incremental/CDC would fit later:** NPPES publishes weekly deactivation/update
files in addition to the monthly full file — a later initiative could poll those and run
`run_ingestion.py` on a schedule (Cloud Scheduler → Cloud Run job), replacing "manual
re-run" with "weekly refresh," without changing the ingestion functions themselves.

## 7. Authoritative data sources

| Source | Provides | Access | Cadence | Key gotchas |
|---|---|---|---|---|
| **NPPES NPI Registry** (CMS) | NPI, entity type, name/org name, practice + mailing address, up to 15 taxonomy codes (one primary), phone, enumeration/update dates | Public API `npiregistry.cms.hhs.gov/api` — no key, filterable by `state`/`city`/`postal_code`/`taxonomy_description`, 200 results/page + pagination. (Full bulk CSV also exists, ~9GB — not used this phase per the curated-subset decision.) | API reflects near-real-time registry; bulk file refreshes monthly + weekly incremental | **No "accepting new patients" field** — ships as `unknown` this build rather than guessing (§15). Org-type (entity_type=2) addresses may be a facility, not an individual's practice — both types are ingested but tagged so callers can distinguish. Address quality varies (PO boxes, billing addresses); not solvable from NPPES fields alone. |
| **NUCC Health Care Provider Taxonomy** | Hierarchical code set: Grouping → Classification → Specialization, 10-char code, definition | Free CSV/PDF from nucc.org, no API | ~2 releases/year (annual + mid-year) | Version drift — codes are occasionally deprecated/split between releases; `taxonomy_reference.nucc_version` pins which release a row came from. |
| **Census Bureau Gazetteer ZCTA file** | ZIP Code Tabulation Area centroid (`INTPTLAT`/`INTPTLONG`) | Free, public domain, bulk download from census.gov | Refreshed with each decennial + intercensal release | ZCTA ≠ USPS ZIP exactly (Census-drawn approximation of ZIP delivery areas) — acceptable for a proximity *stub*, should be documented as an approximation. *To verify: current-year file URL/format at implementation time.* |
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
translation.

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

### 8.3 Tool contracts (sketch)

```jsonc
// resolve_specialty
{ "query": "string, free text" }
→ { "query": "...", "matches": [
      { "code": "207RE0101X", "grouping": "...", "classification": "Endocrinology, Diabetes & Metabolism",
        "specialization": null, "score": 0.94 } ] }

// search_providers_near
{ "location": { "zip": "27514" } | { "lat": 35.9, "lon": -79.05 },
  "taxonomy_codes": ["207RE0101X"],
  "radius_miles": 15, "limit": 10,
  "accepting_new_patients": true | false | null }
→ { "origin": { "lat": 35.9, "lon": -79.05, "resolved_from": "zip:27514" },
    "count": 3,
    "results": [ { "npi": "1234567890", "name": "...", "entity_type": 1,
        "taxonomy_code": "207RE0101X", "taxonomy_description": "...",
        "address": {...}, "distance_miles": 4.2,
        "accepting_new_patients": "unknown",
        "lineage": { "source": "NPPES", "source_pulled_at": "...", "ingestion_run_id": "..." } } ] }

// get_provider
{ "npi": "1234567890" }
→ full record: all addresses, all taxonomies, lineage
```

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
  handling of the search *input* (provider *output* data is public).
- Metrics: `search_providers_near` latency histogram, zero-result rate, MCP tool-call
  counts by tool name, ingestion run record/flag counts.
- Groundedness check (automated, not manual): every NPI appearing in a
  `provider-search-agent` transcript must resolve via `get_provider` — a referential
  smoke test, same spirit as Phase 2's idempotency verification.
- No formal SLO this phase (internal-only, no production traffic) — instrumentation is
  prep work for one, consistent with Phase 2's "designed + stubbed, live deploy later"
  posture.

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

## 13. Milestone plan

Internal work is tracked as milestones, not sub-phases — no "Phase 3.x" labels anywhere below.
Following Phase 2's actual pattern (design + stub the cloud posture at every milestone; defer the
live `terraform apply` to its own follow-on phase), every milestone that adds a deployable
component also produces a **cloud-readiness stub** — a Dockerfile and a Terraform module sketch,
validated with `terraform validate`/`plan` but never applied. That makes **Phase 3b** a deploy of
already-proven config, not a redesign.

| Milestone | Scope | Cloud-readiness stub |
|---|---|---|
| M1 | This PRD + design doc, committed locally (docs-first, matches Phase 2) | n/a — docs only |
| M2 | `provider-registry-service`: schema/migrations, `LocationSearchPort` + `HaversineSqlLocationSearch`, taxonomy resolve endpoint, unit tests against a small hand-written fixture (not real data yet) | Dockerfile + Terraform Cloud Run module sketch, `ingress = "internal"` (not applied) |
| M3 | Ingestion scripts (deterministic): NPPES pull for the pilot state (NC), NUCC load, ZCTA load, upsert — verified against real data | Terraform sketch for a manually-triggered Cloud Run Job (matches the one-time-seed decision, PRD §6) — not applied |
| M4 | `provider-curation-agent`: wraps M3 with an AI run-summary; expand ingestion to the full curated set (NC, CA, MT) | n/a — CLI tool, no new deployable surface |
| M5 | `provider-mcp-server`: real MCP server (stdio), wired to the registry service; integration test proving the actual `initialize`/`tools-list`/`tools-call` handshake | Dockerfile + Terraform Cloud Run sketch — flagged with the caveat in §13.1 below: stdio doesn't cross a network boundary, so this stub alone doesn't make the server cloud-*callable*, only cloud-*runnable* |
| M6 | `provider-search-agent`: real MCP client/host, Anthropic tool-use loop, groundedness eval suite | n/a — CLI tool; spawns the MCP server as a local child process |
| M7 | `docker-compose` demo profile bundling all four new components; end-to-end local verification | Final cloud-readiness pass: `terraform validate`/`plan` across every module added in M2–M6 (still not applied) |

### 13.1 Phase 3b — GCP cloud deployment (future, out of scope here)

Mirrors Phase 2b exactly: Phase 2 was "designed + stubbed + tested throughout; live deploy is
Phase 2b" (project history, M8/C1). Phase 3b's scope, once started:

- `terraform apply` for `provider-registry-service` and `provider-mcp-server` on Cloud Run,
  `ingress = internal`, IAM invoker + VPC connector — using the M2–M7 stubs as-is.
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
  Default recommendation: (a), until something concrete forces (b).
- Live smoke tests against the deployed services, matching Phase 2b's verification bar.

## 14. Risks

- **`accepting_new_patients` data gap** — the single biggest open risk; may need to ship
  without it (always `unknown`) if no usable source is confirmed.
- **NPPES public API rate limits** at ingestion time are undocumented/unverified —
  build in basic backoff, verify empirically during M3.
- **ZCTA-vs-ZIP mismatch** can misplace a small number of centroids (non-residential
  ZIPs have no ZCTA) — acceptable for a stub, called out rather than hidden.
- **Taxonomy synonym coverage** is inherently incomplete for a deterministic (non-LLM)
  matcher — an accepted trade-off for traceability, worth a follow-up eval once real
  usage patterns exist.

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
