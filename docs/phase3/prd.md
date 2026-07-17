# Phase 3 PRD — Provider Search & Referral

**Status:** Draft — committed locally for review, not yet opened as a PR. Open questions from
the first draft are resolved in §9 using best judgement; flagged where you may want to override.
**Extends:** Phase 1 (refill-triage) and Phase 2 (claims adjudication), both unmodified
**Owner:** TBD
**Terminology note:** internal work within Phase 3 is tracked as **milestones** (M1, M2, ...),
never as "Phase 3.x" — "Phase" is reserved for top-level platform phases only: Phase 1, Phase 2,
Phase 3 (this doc), and **Phase 3b** — the future GCP cloud-deployment phase that mirrors Phase
2's live-deploy milestone (Phase 2b). Every Phase 3 milestone prepares a cloud-readiness stub,
but — having checked what Phase 2b actually turned out to need — that stub is necessary and not
sufficient; see the explicit gap-avoidance callout in design doc §13 before assuming Phase 3b is
"just a deploy."
**Decision index:** [`decisions.md`](./decisions.md) tracks every architectural decision below
with a status (Accepted / Partially delivered / Superseded), same convention as Phase 2's.

---

## 1. Problem statement

The platform can assess clinical risk (Phase 1) and adjudicate a claim (Phase 2), but it has no way
to answer the next question a clinician or care coordinator actually asks after a triage or denial:
*"who can this patient actually see?"* Today that means a phone tree, a payer portal, or a paid
directory API — none of which the platform owns, none of which are inspectable, and none of which
prove a returned provider is real.

Phase 3 builds a first-party Provider Search capability: given a patient's location and a clinical
need, return a ranked, explained list of real, traceable providers. The point is not just the
feature — it's proving that a first-party service built on authoritative public data (NPPES) can
do what a commercial provider-directory API does, with full lineage back to source records.

This phase is also this project's first genuine **Model Context Protocol** integration — up to now,
"agent tools" have been in-process Python function dispatch (see `mcp-agent/src/agent/tools.py`).
Provider Search is where the platform gets a real MCP server and a real MCP client/host, wired
through the actual protocol handshake, not a simulation of it.

## 2. Goals

- G1: Given a location (ZIP or coordinate) and a specialty (free text or taxonomy code), return a
  ranked list of nearest matching providers, each traceable to a real NPPES record.
- G2: Normalize free-text clinical need to real NUCC taxonomy codes.
- G3: Stand up a real, hand-built MCP server exposing the deterministic search tools, and a real
  MCP client/host (the Provider Search agent) that discovers and invokes them over the actual
  protocol — no in-process bypass.
- G4: Build an ingestion pipeline that pulls real NPPES data for a curated set of states into a
  canonical provider registry, with lineage from every record back to its source pull.
- G5: Prove agent groundedness — the Provider Search agent must never fabricate a provider; every
  result must resolve to a real registry record with a real NPI.
- G6: Keep the geospatial layer intentionally simple (haversine over a small preloaded table)
  behind an interface that a real geospatial engine can later replace without touching callers.

## 3. Non-goals (this phase)

- **Eligibility / network determination.** Whether a provider is in-network for a given plan is a
  **separate future initiative**, distinct from Phase 3b (which is only the cloud deployment of
  what Phase 3 builds). Phase 3 answers "who is nearby and qualified," not "who is covered."
- **Commercial/payer network data.** No plan-affiliation data is ingested this phase (see §7,
  Out of scope).
- **National-scale data.** The registry is seeded from a curated multi-state subset, not the full
  ~8M-record NPPES bulk file.
- **Production-grade geospatial.** No PostGIS, no Elasticsearch geo, no geohashing. A haversine
  scan over a small table is correct and sufficient for this phase.
- **Scheduled/incremental refresh.** Ingestion is a manually re-run, one-time-per-run script, not a
  live pipeline. (Design doc §6 notes where CDC/scheduling would plug in later.)
- **Cloud-hosted MCP transport.** The MCP server uses stdio (local process boundary) per the
  learning requirement. A network-reachable MCP transport (SSE/HTTP) is only needed if Phase 3b
  hosts the agent itself in the cloud rather than running it as a local CLI — that transport
  decision is explicitly deferred to Phase 3b (design doc §13), not resolved here.
- **Polyglot persistence.** One relational store (Postgres) now, behind a repository interface. No
  document/search store, no Neo4j, this phase — see ADR-equivalent decision in the design doc.

## 4. Users & use cases

**Primary user:** a clinician or care coordinator, interacting through the same kind of
natural-language interface the platform already uses for triage.

- **UC1 — Referral after triage.** A refill-risk triage flags a conflict; the clinician asks
  "find an allergist near this patient who's taking new patients" and gets a ranked, explained list.
- **UC2 — Direct specialty search.** "Find an endocrinologist within 15 miles of 27514" with no
  prior triage context.
- **UC3 — Provider lookup by NPI.** A downstream system or clinician already has an NPI and wants
  the full registry record with lineage (e.g., to populate a referral document).
- **UC4 — Registry curation run.** A data engineer (or the curation agent, agent-assisted) runs the
  ingestion pipeline for a new state, reviews the anomaly/summary report, and confirms the batch.

## 5. Functional requirements

| # | Requirement |
|---|---|
| FR1 | Resolve a free-text clinical need to one or more ranked NUCC taxonomy codes. |
| FR2 | Resolve an input location — ZIP code or explicit lat/long — to a coordinate. |
| FR3 | Given a coordinate, radius, and one or more taxonomy codes, return the nearest N matching providers from the registry, sorted by distance ascending. |
| FR4 | Support an optional `accepting_new_patients` filter; treat unknown as "don't exclude" rather than a hard false (see §6, PHI/PII and the data-gap note in the design doc). |
| FR5 | Fetch a single provider's full registry record by NPI, including source lineage (which ingestion run, which source, when). |
| FR6 | Every tool above is exposed as a real MCP tool (`tools/list` discoverable, `tools/call` invokable) by a hand-built MCP server. |
| FR7 | The Provider Search agent acts as a genuine MCP client/host: it performs the MCP `initialize` handshake, discovers tools via `tools/list`, and invokes them via `tools/call` — never by importing or calling the underlying service functions directly. |
| FR8 | The Provider Search agent decomposes a natural-language request into the structured tool calls above and returns a ranked result set with a plain-language rationale (e.g., "nearest 3 endocrinologists accepting new patients within 15 miles"). |
| FR9 | If specialty resolution or location resolution is ambiguous or fails, the agent surfaces that plainly and asks for clarification rather than guessing. |
| FR10 | The ingestion pipeline pulls NPPES data for a curated set of states, normalizes taxonomy codes, joins ZIP centroids for coordinates, and upserts golden records keyed by NPI. |
| FR11 | The ingestion pipeline (agent-assisted) produces a human-readable run summary: records added/updated, records flagged (missing taxonomy, missing/ambiguous address, stale relative to prior run). |
| FR12 | Every registry record carries lineage: source system, source pull timestamp, ingestion run ID. |
| FR13 | Every tool response conforms to a defined error taxonomy — success-with-results, success-no-results, ambiguous, validation error, not-found, upstream-unavailable — each a distinct, disjoint response shape (design doc §8.4), not an ad-hoc error string. |
| FR14 | The registry tracks each provider's active/deactivated status (from NPPES's deactivation signal) and `search_providers_near` excludes deactivated providers by default; `get_provider` still returns a deactivated record explicitly, so an existing caller can see why it's stale rather than getting an unexplained not-found (design doc §4.1). |
| FR15 | `search_providers_near` supports an optional `entity_type` filter (individual/organization) so a request for an individual practitioner isn't silently mixed with organization-level NPIs that happen to carry a matching taxonomy code (design doc §4.3). |

## 6. Non-functional requirements

- **Scale.** Registry seeded from three states — North Carolina, California, Montana (§9) —
  chosen for density contrast. Expect low-tens-of-thousands to low-hundreds-of-thousands of
  provider records — comfortably within a single Postgres instance with no partitioning.
- **Latency.** `search_providers_near` p95 target: **< 300ms** at curated-subset scale, measured
  from MCP `tools/call` receipt to response. This is achievable with a state-scoped full scan; no
  spatial index is required at this data volume.
- **Freshness.** One-time seed per curated state, manually re-run on demand. No SLA on data
  staleness this phase; the run timestamp is always visible in lineage.
- **Availability.** Internal-only services (registry, taxonomy, MCP server); not on a
  customer-facing critical path this phase. Standard dev/demo reliability expectations. SLIs
  (availability, latency, zero-result rate, MCP conformance, ingestion coverage) are defined
  now so instrumentation lands correctly from M2; no SLO/error-budget target is set against them
  this build, since there's no production traffic yet to set one against — see design doc §11.
- **PHI/PII handling.** Provider data itself is CMS public record, not PHI. However, the **input**
  to a search — a patient's ZIP/coordinate — is potentially sensitive (it discloses a patient's
  approximate location tied to a clinical need) and must be treated PHI-safe-by-default: never
  logged in plaintext (enforced via a shared sanitizing helper, not left as an unenforced
  convention), never included in error messages verbatim, consistent with the platform's
  existing posture (see [[secret-values-never-print]] convention already applied to secrets).
  The internal-only, no-app-layer-auth trust boundary this relies on is justified for Phase 3's
  specific data flow — not just reused from Phase 2 — in design doc §12.1, including the abuse
  cases considered (compromised internal caller, query-volume scraping, log leakage).
- **Compliance posture.** NPPES data is explicitly CMS public-use data with no HIPAA restriction on
  redistribution. No BAA or PHI-handling agreement is implicated by the registry itself.
- **Real-MCP-server learning requirement (NFR, must-have).** The MCP server must implement the
  actual MCP lifecycle (`initialize`, `tools/list`, `tools/call`) using the official Python MCP
  SDK, runnable locally over stdio, at zero cost, such that it could be registered with any
  MCP-compliant client (Claude Desktop, an IDE, this platform's own agent). This is a hard
  constraint on *how* the feature is built, not just *what* it does.

## 7. Out of scope (explicit)

- Eligibility/network determination — a **separate future initiative**, not Phase 3b.
- Commercial/payer network-affiliation data — not ingested this phase; no schema placeholder added
  either (avoids a field with no authoritative source behind it).
- Full national NPPES bulk ingestion.
- Any geospatial engine beyond haversine-over-preloaded-table.
- Scheduled or CDC-based refresh.
- Cloud-reachable MCP transport (SSE/HTTP) — stdio only, this phase.
- Multi-source entity resolution / fuzzy golden-record merge — the identity key is NPI (already
  unique and authoritative from a single source); the merge-rule seam is built but only lightly
  exercised until a second source is added, which is out of scope for both Phase 3 and Phase 3b.
- Provider ratings, reviews, or quality scores.
- Write-back to NPPES or any source system — this is a read/normalize/serve registry, not a
  provider data-management tool.

## 8. Success metrics / KPIs

- **Groundedness:** 0 fabricated NPIs across an eval set of scripted search scenarios — every
  returned provider resolves via `get_provider` to a real ingested record.
- **MCP conformance:** agent completes `initialize → tools/list → tools/call` against the real
  server in an automated integration test (not mocked).
- **Search quality:** ≥ 95% of eval scenarios with a known-answerable specialty+location return at
  least one correctly-specialty-matched result within the requested radius.
- **Latency:** p95 `search_providers_near` < 300ms at curated-subset scale (measured, not assumed).
- **Ingestion coverage:** ≥ 90% of pulled NPPES records for the curated states successfully resolve
  a coordinate (ZIP centroid join) and at least one taxonomy code. **Revised down from an assumed
  ≥99% after M3's real pull measured 94.2%** (4,747/5,040 real NC records) — the gap is fully
  explained by the known ZCTA-vs-ZIP approximation limitation (design doc §7), including a
  confirmed real example (Duke University Medical Center's ZIP 27710 has no ZCTA at all). ≥99%
  was never measured against real data when it was first written; ≥90% is the honest bar based on
  what M3 actually observed, not a re-guess.
- **Data gap transparency:** 100% of records missing `accepting_new_patients` are surfaced as
  `unknown`, never silently coerced to `false`.
- **Staleness safety:** 0 deactivated NPIs (per §4.1's `npi_status`) appear in a default
  `search_providers_near` response across the eval set.

## 9. Decisions (resolving the first draft's open questions)

These were left open in the first draft. Resolved here using best judgement so the build isn't
blocked; each is a reversible call, not an irreversible one — flag if you want any of them
changed before M2 starts.

- **Curated states: North Carolina, California, Montana.** Chosen for density contrast, not for
  any tie to existing demo data (no evidence was found that Synthea's patient data is regionally
  concentrated — checked, found none). NC gives a moderate urban/rural mix, CA stress-tests dense
  clustering (many results within a small radius), MT stress-tests the sparse/zero-result edge
  (large radius, few or no matches). This also happens to reuse ZIP `27514` (Chapel Hill, NC),
  already used as the worked example in the design doc's tool-contract sketch.
- **`accepting_new_patients`: ships permanently `unknown` this build.** No second data source is
  integrated to populate it. CMS Care Compare remains a candidate worth verifying, but that
  verification is non-blocking and deferred to a later milestone rather than gating M2–M7.
- **Provider Curation agent: narrow scope, confirmed.** Run-summary/anomaly-reporting over
  deterministic ETL output, per §7 — not a fuzzy multi-source merge engine. Revisit when a second
  ingestion source is actually added.
- **`provider-search-agent` entrypoint: CLI-only, matching `claims-agent`.** No new HTTP surface,
  no new Kong route, this phase. A UI-facing wrapper is a separate future decision, not assumed
  here.
- **No new shared `client/` package.** `provider-mcp-server` calls `provider-registry-service`
  directly over httpx — it's the only caller, so a shared client library would be premature
  abstraction.
- **Internal service-to-service auth: none, matching the verified Phase 2 pattern.** Checked
  Phase 2's actual code rather than assuming: `claims-service`'s clients to `rxclaim-emulator`,
  `triage-service`, and `fhir-service` send no API key/bearer/shared-secret header at all — trust
  is network-isolation only (`ingress=internal` + IAM invoker + VPC connector, `docs/phase2/plan.md:36-40,167-170`).
  `provider-mcp-server` → `provider-registry-service` follows the same pattern: no
  application-layer auth, isolation enforced at the Cloud Run ingress level in Phase 3b.
