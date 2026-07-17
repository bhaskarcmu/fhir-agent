# Decision Index (ADR-style)

Every architectural decision for Provider Search, in one auditable list: what was decided, its
status, and where the full rationale lives. Modeled directly on
[`docs/phase2/decisions.md`](../phase2/decisions.md) — same status vocabulary, same convention.

**This page is an index, not a rewrite.** Each decision's reasoning already exists in
[`prd.md`](./prd.md) or [`design.md`](./design.md); duplicating it here would create two
versions that drift. Follow the link for the *why*. Read this page for *what was decided, and
whether it still holds*.

Status values: **Accepted** (in force) · **Superseded** (replaced — successor named) ·
**Partially delivered** (accepted, but the repo does not yet match — the gap is named).
Nothing in Phase 3 is built yet, so every row below is currently either Accepted-as-design-intent
or explicitly flagged as a commitment still to be verified once M2 starts — not yet capable of
being "Partially delivered" in the way Phase 2's rows are, since there's no code yet to diverge
from the design. That will change as milestones land; this page will be updated then, not
rewritten to look right in hindsight (see Conventions below).

---

## P — Provider Search decisions

| # | Decision | Status | Notes / supersession |
|---|---|---|---|
| **P1** | Two **new standalone packages** (`provider-search-agent`, `provider-curation-agent`), not extensions of `mcp-agent` | ✅ Accepted | Mirrors Phase 2's **D3**. Rationale: [`design.md` §2](./design.md#2-package-layout-new). |
| **P2** | A **real, hand-built MCP server** (`provider-mcp-server`, Python `mcp` SDK, stdio transport) is the actual protocol boundary — not in-process tool dispatch like `mcp-agent/src/agent/tools.py` | ✅ Accepted | The learning requirement driving this whole phase. Rationale: [`prd.md` §2](./prd.md#2-goals) G3, [`design.md` §8](./design.md#8-mcp-server--component-contracts-transport-wiring). |
| **P3** | **Postgres-only** persistence behind `LocationSearchPort` + a repository interface; polyglot (document store, Neo4j) deferred | ✅ Accepted | Mirrors Phase 2's **C3** pattern (repository interface now, scale swap later documented not built). Rationale: [`design.md` §5](./design.md#5-persistence-decision). |
| **P4** | **No application-layer internal auth** between `provider-mcp-server` and `provider-registry-service` — network isolation only | ✅ Accepted | Verified against Phase 2's actual code (not assumed) — `HttpTriageClient.java:50-55`, `HttpLegacyClient.java:23-29`, `HapiFhirClient.java:24-31` send no auth header. **Not a blank reuse of the mechanism** — justified for Phase 3's specific data flow (location-sensitive input, not just internal claims) in [`design.md` §12.1](./design.md#121-threat-model-for-the-internal-boundary), added after review flagged the first draft copied the mechanism without the justification. |
| **P5** | Curated ingestion set: **North Carolina, California, Montana**; ingestion is a **manually re-run, one-time-per-state seed** — no CDC/scheduling this build | ✅ Accepted | States chosen for density contrast, not demo-data alignment. Rationale: [`prd.md` §9](./prd.md#9-decisions-resolving-the-first-drafts-open-questions). |
| **P6** | `accepting_new_patients` ships **permanently `unknown`** this build — no second data source integrated | ✅ Accepted | NPPES has no such field; CMS Care Compare remains an unverified future candidate. Rationale: [`prd.md` §9](./prd.md#9-decisions-resolving-the-first-drafts-open-questions). |
| **P7** | Registry gains explicit **`npi_status`/deactivation tracking** and a hard filter excluding deactivated providers from search by default; `search_providers_near` gains an optional **`entity_type`** filter | ✅ Accepted | Both closed gaps identified in review (first draft had neither). Rationale: [`design.md` §4.1](./design.md#41-data-model-postgres-single-instance--see-5-for-the-persistence-decision), [§4.3](./design.md#43-ranking-approach). |
| **P8** | Cloud-readiness stubs ship **per milestone** (M2–M7); Phase 3b delivers the **root Terraform module, deploy script, and an executed CI cloud smoke test as their own named milestone-tracked items** — not assumed to exist because per-service stubs do | ✅ Accepted | **Deliberately not repeating Phase 2's D8/C1 gap**: Phase 2 committed to the same per-milestone cloud posture, then had to publicly retract "Phase 2b is terraform apply, not new construction" once the root module/deploy script/smoke test turned out never to have shipped (`docs/phase2/plan.md`'s "Cloud-delivery gap" callout). Rationale and the full callout: [`design.md` §13](./design.md#13-milestone-plan). |
| **P9** | Explicit **error taxonomy** (5 disjoint response classes: success-with-results, success-no-results, ambiguous, validation error, not-found, upstream-unavailable) for all three MCP tools, plus concrete JSON Schemas replacing the first draft's placeholder schema constants | ✅ Accepted | Modeled on Phase 2's **R17.6** error taxonomy. Closes a rigor gap identified in review. Rationale: [`design.md` §8.4](./design.md#84-error-taxonomy). |
| **P10** | Ingestion (`run_ingestion.py`) writes **directly to Postgres**, not through a `provider-registry-service` upsert HTTP API | ✅ Accepted | **Supersedes** a self-contradiction in the first draft: §1's diagram always showed direct-to-DB; §6's prose said "calls provider-registry-service upsert API" instead. Resolved in favor of the diagram during M3 — same "no shared surface for a single caller" reasoning already applied to `client/clinical` (§9). `provider-registry-service` gains no write endpoints. Rationale: [`design.md` §6](./design.md#6-ingestion-pipeline). |
| **P11** | NUCC taxonomy CSV and Census ZCTA Gazetteer sources **verified live during M3**, not assumed from the first draft's "to verify" flags | ✅ Accepted | NUCC: `nucc.org/images/stories/CSV/nucc_taxonomy_260.csv` (v26.0, 883 codes). Census: `www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_zcta_national.zip`. Also found two real API gotchas not in the first draft: NPPES rejects a bare `state` filter, and the live Read API only ever returned `status: "A"` across hundreds of sampled records (deactivated NPIs may not surface via this endpoint at all). Rationale: [`design.md` §6](./design.md#6-ingestion-pipeline), [§7](./design.md#7-authoritative-data-sources). |
| **P12** | Ingestion-coverage KPI **revised from ≥99% (assumed) to ≥90% (measured)** | ✅ Accepted | M3's real NC pull measured 94.2% (4,747/5,040) coordinate-resolution — the ≥99% figure in the first draft was written before any real data existed and was never re-checked. Gap is explained: ZCTA-vs-ZIP approximation drops unique/institutional ZIPs with no ZCTA (confirmed real example: Duke University Medical Center's 27710). Rationale: [`prd.md` §8](./prd.md#8-success-metrics--kpis). |
| **P13** | Taxonomy-matcher quality gap (real ambiguity on common lay queries) **flagged, not fixed, in M3** | ✅ Accepted (deferred) | M3 found `resolve_specialty("endocrinologist")` returns `status: "ambiguous"` against the real 883-code set — a nursing-taxonomy specialization ("Reproductive Endocrinology/Infertility") scores above the intended physician code. This is the error taxonomy (P9) working as designed on real data (M2's tiny 2-code test fixture couldn't have surfaced this), not a defect — but it's a real quality gap worth a future tuning pass. Explicitly out of M3's scope (ingestion, not matching-algorithm tuning). Rationale: [`design.md` §14 Risks](./design.md#14-risks). |
| **P14** | `provider-curation-agent` mirrors `claims-agent`'s exact structure (`agent.py`/`tools.py`/`format.py` + a deterministic renderer, LLM-optional via `ANTHROPIC_API_KEY`/`CLAUDE_API_KEY`, `--no-llm` fallback) | ✅ Accepted | Deliberate reuse of an established, working pattern rather than inventing a new agent shape. The one structural difference: this agent's tool shells out to `data/scripts/provider_ingest/*.py` as subprocesses and reads the authoritative result back from Postgres directly, rather than making one HTTP call — ingestion has no service to call (P10). Rationale: [`design.md` §3.2](./design.md#32-provider-curation-agent-ingestioncuration). |
| **P15** | Test filenames must be **repo-unique**, not just per-package-unique, given this repo's `--import-mode=importlib` + per-package `tests/__init__.py` setup | ✅ Accepted | Found real in M4: `provider-curation-agent/tests/test_tools.py` silently collided with `claims-agent/tests/test_tools.py` (identical dotted module name `tests.test_tools`) — one package's tests ran twice under two reported paths, the other's never ran, no error, passing exit code. Fixed by renaming to `test_ingestion_tools.py`; a repo-wide `find`-based check confirmed no other collisions exist. Rationale: [`design.md` §14 Risks](./design.md#14-risks). |

## Conventions

- **A decision is never edited to look right in hindsight.** If reality diverges once a
  milestone lands, the status changes to *Partially delivered* and the gap is named — the same
  discipline Phase 2's **D8**/**C1** rows model. If a decision is replaced, it is marked
  *Superseded* and the successor is named — the original stays.
- **Rationale lives in the normative doc, not here.** This index links; it does not restate.
- **New architectural decisions get a row here** and their rationale in `prd.md` (if normative)
  or `design.md` (if design). A decision that exists only in a PR description or a chat log is
  not recorded.
