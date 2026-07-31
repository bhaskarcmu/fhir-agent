# Decision Index (ADR-style)

Every architectural decision for Epic Emulator, in one auditable list: what was decided, its
status, and where the full rationale lives. Modeled directly on
[`docs/phase3/decisions.md`](../phase3/decisions.md) — same status vocabulary, same convention.

**This page is an index, not a rewrite.** Each decision's reasoning already exists in
[`prd.md`](./prd.md) or [`design.md`](./design.md); duplicating it here would create two versions
that drift. Follow the link for the *why*. Read this page for *what was decided, and whether it
still holds*.

Status values: **Accepted** (in force) · **Superseded** (replaced — successor named) ·
**Partially delivered** (accepted, but the repo does not yet match — the gap is named).

**M1 is built** (see [`README.md`](./README.md)'s canonical status); E1–E5, E7, E8 are now
verified against real, tested code (E2's proxy architecture, E3's directory, E7's read-time
approach hasn't been exercised until M3 but the write-pass-through half is already true today).
E9 is a documentation-format decision, not code. **E10 remains genuinely open** — the Epic
documentation version and the exact quirk/extension values are still not pinned, tracked as
**Partially delivered** rather than guessed at just to fill the table.

---

## E — Epic Emulator decisions

| # | Decision | Status | Notes / supersession |
|---|---|---|---|
| **E1** | One monolith — auth emulation, extension handling, and quirk simulation ship as **one Spring Boot process**, not three services, because their internal boundaries aren't known yet | ✅ Accepted | Monolith-first per Fowler; boundaries deferred to Phase 5, evidence-based on what M1–M5 actually reveal. Rationale: [`prd.md` §1](./prd.md#1-problem-statement). |
| **E2** | `epic-emulator` is a **proxy in front of `fhir-service`**, not a standalone service with its own embedded FHIR store | ✅ Accepted | Chosen over the standalone alternative to keep `fhir-service`'s already-seeded data as the single source of truth — no duplicate fixture pipeline. Accepted tradeoff: both services must run together for any real test. Rationale: [`prd.md` §9](./prd.md#9-decisions-resolving-open-questions-using-best-judgement), [`design.md` §1](./design.md#1-target-architecture). |
| **E3** | New **top-level `epic-emulator/` directory**, own Maven build — not a submodule of `fhir-service` | ✅ Accepted | Matches this repo's existing per-service layout; follows the same shape as the same-repo `rxclaim-emulator` precedent (internal-only Spring Boot service emulating a real system's contract). Rationale: [`prd.md` §9](./prd.md#9-decisions-resolving-open-questions-using-best-judgement). |
| **E4** | Extension emulation is **closed to Medication and AllergyIntolerance only**, tied to the existing prescription-refill-risk-triage reference workflow — not "any Epic extension" | ✅ Accepted | Bounds the module's scope to a concrete, testable slice instead of an open-ended surface. Rationale: [`prd.md` §1/§3](./prd.md#1-problem-statement). |
| **E5** | Quirk emulation is **closed to exactly three named quirks** — pagination/`_count` behavior, a required search-parameter combination, and `OperationOutcome` error-shape deviations — no open "quirks" backlog | ✅ Accepted | The three were chosen to sample different layers of API interaction (getting results back / what you're allowed to ask for / how errors are reported), not three variations on one theme. This is the concrete mechanism keeping Phase 4 sized in days, not weeks. Rationale: [`prd.md` §1](./prd.md#1-problem-statement), [`design.md` §6](./design.md#6-quirks--concrete-pinned-choices-starting-design-pending-validation). |
| **E6** | `triage-service` and `claims-service` decision logic is **explicitly excluded** from `epic-emulator` — the acceptance case (FR9) *exercises* `triage-service` through the proxy, it does not absorb or duplicate either service's rules | ✅ Accepted | Rejects an earlier proposal to bundle both services' functionality into the same monolith as the three capability areas. Both are already independently built and validated (Phase 1/Phase 2); Epic emulation is a protocol/format concern, not a clinical or claims-decision concern, and duplicating that logic would create a second, driftable copy. Rationale: [`prd.md` §3/§9](./prd.md#3-non-goals-this-phase). |
| **E7** | Extensions round-trip via **read-time backfill only** — reads inject a default Epic extension when one isn't already present; writes pass through unchanged, since `fhir-service` already stores arbitrary extensions with no special handling needed | ✅ Accepted | Satisfies "no new fixture pipeline" (PRD G4) with the least new code. Rationale: [`design.md` §5/§14](./design.md#5-extension-handling--concrete-approach). |
| **E8** | Auth-client registration is **dev-simple** — a config-file/in-memory JWK registration, no approval workflow or real vendor procurement process | ✅ Accepted | Matches the PRD's instruction to assume easy developer access; mirrors the *shape* of Epic's real backend-services flow (a client presents a public key) without the real-world overhead. Rationale: [`design.md` §4/§14](./design.md#4-auth-flow--concrete-contract). |
| **E9** | **No separate `plan.md`** — the milestone plan lives inside `design.md` (§12) | ✅ Accepted | Follows Phase 3's consolidation (Phase 2 had kept `requirements.md`/`plan.md` separate; Phase 3 folded that split into `prd.md`/`design.md`). Rationale: [`design.md` §14](./design.md#14-decisions-resolving-open-questions-using-best-judgement). |
| **E10** | The specific Epic documentation version to target for conformance, and the exact real values behind each quirk/extension (§6's table), are **not yet pinned** | 🟡 Partially delivered | Deliberately left open rather than guessed: asserting a specific Epic doc version or exact quirk values without having actually registered for access would be an unverified claim. Named as the first concrete task of M2. The gap: `design.md` §6's quirk table is "structurally representative," not yet "confirmed against a real source." Rationale: [`design.md` §7](./design.md#7-authoritative-documentation--the-one-open-action-item). |

## Conventions

- **A decision is never edited to look right in hindsight.** If reality diverges once a milestone
  lands, the status changes to *Partially delivered* and the gap is named — same discipline as
  Phase 2/Phase 3. If a decision is replaced, it is marked *Superseded* and the successor is named
  — the original stays.
- **Rationale lives in the normative doc, not here.** This index links; it does not restate.
- **New architectural decisions get a row here** and their rationale in `prd.md` (if normative) or
  `design.md` (if design). A decision that exists only in a PR description or a chat log is not
  recorded.
