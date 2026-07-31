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

**M1, M2, and M3 are built** (see [`README.md`](./README.md)'s canonical status); E1–E9 and E11–E12
are now verified against real, tested code (E2's proxy architecture, E3's directory, E7's
read-time backfill approach — both halves now exercised by M3's tests). E9 is a
documentation-format decision, not code. **E10 remains genuinely partial** — M2 made one real,
verifiable attempt (§7/design.md) and confirmed the Epic documentation site is real and public at
a shell level, but the Epic-specific technical parameters were not retrievable that way; M2's auth
flow was built against the public base SMART Backend Services spec instead, which is a legitimate
source in its own right, not a workaround. E11 records the RS384-only scoping choice found while
building M2; E12 (new) records that M3's concrete resource-type scoping is `MedicationRequest`,
not the PRD's more generic "Medication" — found by checking what the reference workflow actually
reads, not assumed.

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
| **E10** | The specific Epic documentation version to target for conformance, and the exact real values behind each quirk/extension (§6's table), are **not yet pinned** | 🟡 Partially delivered | M2 made one real attempt: `fhir.epic.com/Documentation?docId=oauth2` is genuinely public (no login), dated "Last updated: October 31, 2025," with a menu entry for backend OAuth 2.0 — but the specific technical parameters (JWT claim details, scope format, rate limits) are rendered behind interactive navigation, not retrievable by a plain page fetch. No account registration was attempted (an inherently human step). M2's auth flow was instead built directly against the public, normative **SMART Backend Services** spec (HL7/SMART Health IT) — a legitimate independent source, not a stand-in. The gap: Epic's own specific parameter values, and `design.md` §6's quirk table, remain "structurally representative," not "confirmed against Epic's own docs." Rationale: [`design.md` §7](./design.md#7-authoritative-documentation--the-one-open-action-item). |
| **E11** | Client-assertion signing supports **RS384 only** — the spec's other allowed algorithm, ES384 (EC keys), is not implemented | ✅ Accepted | Found while building M2: supporting EC keys too would add a second key-handling path in `ClientAssertionValidator` for marginal value at this stage. Documented as a known simplification, not a silent gap — worth revisiting only if a real Epic sandbox test ever requires ES384. Rationale: [`design.md` §4/§14](./design.md#4-auth-flow--concrete-contract). |
| **E12** | Extension emulation concretely targets **`MedicationRequest`**, not the generic "Medication" the PRD names | ✅ Accepted | Found while building M3: checked what the reference workflow actually reads rather than assuming — `triage-service`/`client/clinical` query `GET /MedicationRequest?patient=...&status=active`, never the `Medication` catalog resource. The PRD's "Medication" stays as higher-level category language; `design.md` §5 now pins the concrete resource type, same pattern as §6 pinning concrete quirk specifics. Rationale: [`design.md` §5](./design.md#5-extension-handling--concrete-approach). |

## Conventions

- **A decision is never edited to look right in hindsight.** If reality diverges once a milestone
  lands, the status changes to *Partially delivered* and the gap is named — same discipline as
  Phase 2/Phase 3. If a decision is replaced, it is marked *Superseded* and the successor is named
  — the original stays.
- **Rationale lives in the normative doc, not here.** This index links; it does not restate.
- **New architectural decisions get a row here** and their rationale in `prd.md` (if normative) or
  `design.md` (if design). A decision that exists only in a PR description or a chat log is not
  recorded.
