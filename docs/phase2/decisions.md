# Decision Index (ADR-style)

Every architectural decision on this project, in one auditable list: what was decided, its
status, what superseded it, and where the full rationale lives.

**This page is an index, not a rewrite.** Each decision's reasoning already exists in a
normative document; duplicating it here would create two versions that drift. Follow the link
for the *why*. Read this page for *what was decided, and whether it still holds*.

Two families:

- **D1–D8 — Deviations from the source PRD.** Where what we agreed to build differs from the
  DRAFT PRD. Full table: [`requirements.md` → Deviations](./requirements.md#deviations-from-the-prd).
- **C1–C5 — Cloud, security & scalability decisions.** Made during design, before build. Full
  table: [`README.md`](./README.md).

Status values: **Accepted** (in force) · **Superseded** (replaced — successor named) ·
**Partially delivered** (accepted, but the repo does not yet match — the gap is named).

---

## D — Deviations from the PRD

| # | Decision | Status | Notes / supersession |
|---|---|---|---|
| **D1** | **Hybrid rules stack** — new adjudication rules in Java; **reuse** the Python `triage-service` for drug-allergy + duplicate-therapy rather than rebuilding in Java | ✅ Accepted | In force and load-bearing. Reuse boundary is the triage HTTP contract; see [`plan.md` §2](./plan.md#2-components). Later refined by the fail-closed decision (below), which changed how an *unavailable* triage is interpreted — not the reuse boundary itself. |
| **D2** | `rxclaim-emulator` is its **own top-level module**, a *sibling* to the EHR emulators, not a member | ✅ Accepted | Enforced in the tree and restated in [`epic-emulator`](../../epic-emulator/README.md) / [`athena-emulator`](../../athena-emulator/README.md) non-goals. |
| **D3** | A **separate `claims-agent`**, not an extension of the Phase 1 `mcp-agent` | ✅ Accepted | Protects R9. The two agents share only non-clinical plumbing. |
| **D4** | **Edge Kong** fronting claims+fhir+triage; emulator strictly private; **opt-in** DB-less Kong compose profile; **hybrid gateway** with a strangler migration | ✅ Accepted | Operational detail now consolidated in the [gateway runbook](../gateway-runbook.md). Refined by **C2**, which chose the DB-less dialect as canonical. |
| **D5** | **Canonical scope:** 15–20 rules / ~8 domains; **4–5 paths** exercised end-to-end | ✅ Accepted | Resolved three conflicting PRD numbers. The demo now exercises **6** paths (a clinical-safety path was added), still within "4–5" in spirit — the extra path exists because nothing else proved triage was consulted. |
| **D6** | **Generic FHIR R4**, structured to *nod to* Da Vinci PAS/CRD; **no PAS conformance** | ✅ Accepted | Deliberate scope limit; unchanged. |
| **D7** | **Curated fixtures** rather than full RxNorm/ICD loads; check-existing-first | ✅ Accepted | Also avoids CPT/AMA licensing risk on a public repo. Governed by R19. |
| **D8** | **Hybrid cloud, designed & tested throughout, deployed late:** Phase 1 stays on GKE; Phase 2 targets Cloud Run; cloud IaC/stubs/tests ship **from each milestone**; live deploy is Phase 2b | ⚠️ **Partially delivered** | **Supersedes** the earlier "cloud-deferred" framing. The *decision* stands; the *practice* was not followed. Per-service Cloud Run stubs shipped for the two Java services (M2, M3); the top-level root module, `deploy-phase2.sh`, `claims-agent`'s config, and the cloud smoke test never did. See the [cloud-delivery gap](./plan.md#6-workstreams--milestones) and [§16 item 9](./plan.md#16-future-work). |

## C — Cloud, security & scalability

| # | Area | Decision | Status | Notes / supersession |
|---|---|---|---|---|
| **C1** | Compute | **Hybrid: GKE for Phase 1 (untouched) + Cloud Run for new Phase 2 services**; HAPI always-on | ⚠️ **Partially delivered** | Design in force and reflected in the per-service stubs. Nothing deployed — same gap as D8. Cold starts remain an unverified risk ([`plan.md` §5](./plan.md#5-cloud-architecture--compute-data-security-observability-scalability)). |
| **C2** | Gateway | **DB-less Kong** as the canonical Phase 2 gateway — one declarative dialect, local + cloud; Phase 1 KIC untouched, unified later via the gateway-strangler | ⚠️ **Partially delivered** | **Supersedes** the config-dialect drift risk originally flagged in [`plan.md` §3](./plan.md#3-gateway--localcloud-parity), and refines **D4**. The local half runs today; the cloud half is undeployed. **Filename caveat:** the committed artifact is `kong.tmpl.yml` (a template); `kong.yml` is generated at startup — see the [gateway runbook](../gateway-runbook.md). |
| **C3** | Rules data | **Postgres behind a repository interface** now; Bigtable/Firestore is the documented scale swap | ⚠️ **Partially delivered** | The *seam* exists and is honoured (`PayerKb` + `FilePayerKb`). The **Postgres implementation does not** — storage is file-backed. The swap is therefore an untested hypothesis; [§16 item 5](./plan.md#16-future-work). |
| **C4** | Audit | **FHIR `Provenance`** now (with R18 invariants); BigQuery analytics plane deferred to Phase 2b | ✅ Accepted | `Provenance` is built and persisted per decision. BigQuery deliberately deferred; [§16 item 11](./plan.md#16-future-work). |
| **C5** | Observability | **OpenTelemetry tracing + Micrometer/Prometheus metrics** (R15), designed to run per-claim/per-stage in `claims-service` and `rxclaim-emulator` | ⚠️ **Partially delivered** | Design documented ([`plan.md` §5](./plan.md#5-cloud-architecture--compute-data-security-observability-scalability)); the milestone table marked M3/M4's touchpoints "OTel tracing wired" / "Managed-Prometheus metric names," but no `opentelemetry`/`micrometer` dependency or trace/correlation-ID code exists in either service. Found post-hoc (2026-08); same gap class as D8, just previously uncaught. See the [cloud-delivery & observability gap](./plan.md#6-workstreams--milestones). |

## Later decisions (post-design, made during build)

Decisions taken after the D/C sets were locked, recorded where they are normative:

| Decision | Status | Where |
|---|---|---|
| **Clinical safety fails closed.** `RiskLevel.UNKNOWN` ("check could not complete") is distinct from `LOW` ("checked, safe") and maps to **PEND**, never approve. A hard DENY still outranks it. | ✅ Accepted | [`requirements.md` R17.5](./requirements.md) — includes the rationale and the accepted consequence (a member with no clinical record pends). Implementation: [`claims-service/README.md`](../../claims-service/README.md). |
| **Member→Patient resolution by `read Patient/member-{id}`**, not identifier search | ✅ Accepted (prototype affordance) | Reads are immediately consistent; search is index-lagged. Explicitly temporary — [§16 item 6](./plan.md#16-future-work). |
| **Claim validation bounds mirror the legacy fixed-width record.** Mandatory = anything a decision depends on; sizes = what the ACL can carry without truncating. | ✅ Accepted | Implements R17.6's validation class. The ACL right-pads and truncates, so the boundary refuses what the ACL would silently corrupt. Field table: [`claims-service/README.md`](../../claims-service/README.md). |

## Conventions

- **A decision is never edited to look right in hindsight.** If reality diverges, the status
  changes to *Partially delivered* and the gap is named. If a decision is replaced, it is marked
  *Superseded* and the successor is named — the original stays.
- **Rationale lives in the normative doc, not here.** This index links; it does not restate.
- **New architectural decisions get a row here** and their rationale in `requirements.md` (if
  normative) or `plan.md` (if design). A decision that exists only in a PR description or a chat
  log is not recorded.
