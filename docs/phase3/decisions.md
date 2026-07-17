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

## Conventions

- **A decision is never edited to look right in hindsight.** If reality diverges once a
  milestone lands, the status changes to *Partially delivered* and the gap is named — the same
  discipline Phase 2's **D8**/**C1** rows model. If a decision is replaced, it is marked
  *Superseded* and the successor is named — the original stays.
- **Rationale lives in the normative doc, not here.** This index links; it does not restate.
- **New architectural decisions get a row here** and their rationale in `prd.md` (if normative)
  or `design.md` (if design). A decision that exists only in a PR description or a chat log is
  not recorded.
