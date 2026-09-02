# Phase 7 PRD — Medication Reconciliation

**Status:** DRAFT — scope and methods brainstormed with the repo owner; planning pass complete
(this PRD, `design.md`, `decisions.md`, `milestone-plan.md` all exist). No code written yet.
**Companion doc:** [`design.md`](./design.md) — architecture, component breakdown, the
precedence-policy and RxNorm-matching sketches, and the reconciled-line data model.
**Milestone plan:** [`milestone-plan.md`](./milestone-plan.md) — M1–M8, kept as its own document
rather than folded into `design.md`, same convention Phase 6 used (`phase6/decisions.md` H23).
**Decision index:** [`decisions.md`](./decisions.md) tracks every decision below with a status,
same convention as Phase 2/3/4/6 (`R1`–`R14` so far).
**Extends:** Phase 1 (`fhir-service`, `triage-service`, `client/clinical`), Phase 4
(`epic-emulator`, extended in this phase — see §6). Builds out `athena-emulator`, reserved as an
empty placeholder since Phase 2 (`docs/phase2/plan.md` §16, deviation D2) and left untouched
through Phase 4.
**Owner:** TBD
**Terminology note:** following Phase 3/4/6 convention, internal work here will be tracked as
milestones (M1, M2, …) once a milestone plan exists — not written yet, per explicit instruction
from the repo owner while scope is still being brainstormed.

---

## 1. Problem statement

Of the national transitions-of-care quality indicators, medication reconciliation is the only one
that is genuinely a data-merge problem rather than a "did someone do a thing and log it" checkbox.
NCQA defines it as comparing the medications ordered at discharge against the most recent
medication list in the outpatient record and resolving the differences. The Joint Commission's
medication safety goal (effective January 2026) specifies the same shape: obtain the current
medication list (name, dose, route, frequency, duration, purpose), compare it against what was
ordered, and resolve **discrepancies**, which it defines as exactly four types — omissions,
duplications, contraindications (change/conflict), and unclear information. The regulation also
states that "a good faith effort... will be considered as meeting the intent" when complete
information can't be obtained — i.e., an incomplete-but-documented outcome is compliant, not a
failure. That is the same fail-closed doctrine already built into this platform
(`agent-platform/src/agent_platform/output_gate.py`, `fail_closed.py`), applied to a new problem.

The problem is real and heavily documented: studies report unintentional medication discrepancies
in roughly half of care transitions, with the discharge point being the worst of the three
transition types measured.

This platform has an unusual amount of the scaffolding this needs already built:
- `epic-emulator` (Phase 4) is a working, tested Epic-shaped proxy over `fhir-service`, already
  handling MedicationRequest and AllergyIntolerance with Epic-style extensions and quirks.
- `athena-emulator` was reserved back in Phase 2 specifically because "one emulator proves
  nothing" — a two-source problem is the first workload in this repo that actually needs it.
- `triage-service` already fetches medications/allergies and returns a `RiskAssessment` with a
  `basis` reference list — a proven precedent for "here's the decision, and here's exactly what
  data it's based on," which is most of what a reconciled view needs to expose per line.
- `claims-service` already emits FHIR `Provenance` resources, establishing the pattern (if not
  reusable code — see §6) for "which system said this, and when."
- The fail-closed enum-gate pattern (`output_gate.py`/`fail_closed.py`) is a direct precedent for
  this phase's own gate (§6, §9).

## 2. Decisions already made (via brainstorm — see §11)

These were explicitly discussed with the repo owner and are treated as settled inputs to this
PRD, not open questions:

| Topic | Decision |
|---|---|
| Epic-side source | `epic-emulator` only (not a live Epic sandbox) — deterministic, free, already built. |
| Athena-side source | Build `athena-emulator` for real, this phase — the "second edge" that proves the portability claim Phase 4 left open. Quirks deliberately different from Epic's. |
| Drug normalization | An abstraction layer, live RxNav calls first, with room for a cached/local fallback implementation later — mirrors the provider-abstraction shape from Phase 6 M5. |
| Patient/encounter identity resolution | A new, narrowly-scoped resolver built this phase — not a full MPI product, not delegated entirely to each source's native matching, not deferred. |
| Epic "Outside Record" endpoint distinction | Modeled explicitly in `epic-emulator` this phase (see §6), not left as a documentation-only talking point. |
| MedicationDispense (fill status) | In scope, as a third per-medication signal alongside each source's MedicationRequest — both emulators need it. |
| Match-classification rigor | Real structured comparison of dose/route/frequency (parsed from `dosageInstruction`), not RxNorm-concept-id matching alone. |
| Repo shape | One new top-level service, tentatively `med-reconciliation-service/` (name not final — see §10), following `triage-service`'s "deterministic core service" shape. The five/six capability areas (normalizer, recon engine, precedence policy, provenance, gate) live inside it as internal modules — same monolith-first reasoning Phase 4 used for `epic-emulator`, not five new packages guessing at boundaries that don't exist yet. |

## 3. Goals

- **G1 — Independent multi-source retrieval.** Retrieve the medication list from each connected
  source (at minimum `epic-emulator` and the new `athena-emulator`) independently. One source's
  failure, timeout, or slowness never blocks, delays past a bound, or silently empties another
  source's contribution.
- **G2 — Drug concept normalization.** Resolve every medication entry to a standard drug concept
  (RxNorm), recording which term type was reached (ingredient, clinical drug, or branded) — not
  just an ingredient-level match.
- **G3 — Five-tier match classification.** Classify each cross-source pairing as identical,
  equivalent, same-ingredient-different-product, ingredient-level-only, or unresolved, using a
  real structured comparison of dose, route, and frequency — not string matching, not RxNorm
  concept ID alone.
- **G4 — Four-category discrepancy labeling.** Label every reconciled line using the Joint
  Commission's own vocabulary: omission, addition/duplication, change, or unclear — each carrying
  which source(s) contributed which side.
- **G5 — Field-level provenance and freshness.** Every field in the reconciled view carries its
  source system, that source's response time, and the age of the underlying record. A source that
  did not respond is reported as unreachable, explicitly and distinctly from a source that
  responded with zero medications.
- **G6 — A precedence *reference* policy, not an auto-merge.** A config file (YAML, not code)
  states which source is generally more trustworthy for which *kind* of question (what was
  prescribed vs. what the patient is actually taking vs. whether a drug was ever obtained), with
  written reasons — read by a human alongside the reconciled view. It informs display and framing.
  It must not cause the system to silently pick one source's value and discard the other's (see
  Non-goals) — that distinction is worth stating explicitly because it is easy to build wrong.
- **G7 — Fail-closed reconciliation outcome.** Every run resolves to exactly one of `RECONCILED`,
  `DISCREPANCIES_FOUND`, or `INCOMPLETE_SOURCES` — mirroring `output_gate.py`'s enum-gate pattern.
  Any single unreachable source forces `INCOMPLETE_SOURCES`; there is no code path that produces
  `RECONCILED` with a source missing.
- **G8 — Two triggers, one core.** A facility admission/discharge notification (event) and a
  clinician-initiated on-demand lookup both resolve to the same patient+encounter → retrieve →
  normalize → reconcile → gate pipeline; only the entry point and identity-confirmation
  requirements differ (§5).
- **G9 — Athena as a real second edge.** `athena-emulator` is built out as a working proxy +
  auth flavor + quirks module, deliberately divergent from `epic-emulator`'s quirks (different
  pagination behavior, different required parameters, different error envelope), so that
  source-specific behavior cannot hide inside code shared between the two.
- **G10 — Epic's "Outside Record" distinction, modeled.** `epic-emulator` gains the
  `(Outside Record)` endpoint variants for Medication/MedicationRequest/MedicationDispense, so the
  emulator itself carries the same source-provenance distinction Epic's real API does, rather than
  that idea existing only in this PRD's prose.

## 4. Non-goals (this phase)

- **A single merged medication list.** The reconciled view preserves every source's contribution
  line-by-line; it never collapses sources into one authoritative list. G6's precedence policy is
  explicitly a labeling aid, not a merge mechanism — see G6.
- **Auto-resolving ambiguous patient identity.** Any ambiguous match returns a candidate set with
  match evidence; a human confirms. No automatic best-candidate selection, ever (§5, Trigger B).
- **Drug-interaction assessment.** Out of scope entirely — and deliberately not stubbed as a
  component that could be misread as "checked, no interactions found." NLM discontinued the free
  RxNav drug-drug interaction API in January 2024; if this platform ever adds interaction
  checking, it depends on licensed content and belongs behind an interface whose gate returns
  "cannot assess," never a silent empty result.
- **Extending to the nursing-facility transition.** Scope is strictly hospital-to-clinic, where
  both sources are real, standards-based APIs (even if emulated). No nursing-facility API sandbox
  exists to build or test against honestly; a hospital-to-nursing-facility gap is a data-access
  problem for facility-side systems of record, not something this phase's pattern extends to.
- **Modifying `triage-service`'s existing drug-allergy-conflict behavior.** `client/clinical`
  extensions this phase (§6) must be additive/backward-compatible — existing `get_medications()`
  call sites and their default behavior are unchanged.
- **Production/cloud deployment.** Local-run only this phase, same posture Phase 4 took for
  `epic-emulator` before any Phase 4b.
- **A full enterprise master-patient-index product.** The identity/encounter resolver (G8, §5) is
  scoped to this workflow's two triggers, not a general-purpose MPI.

## 5. Triggers & users

**Primary user:** a clinician or care-transitions staff member reviewing a patient's medications
across a hospital discharge and an outpatient record.

- **Trigger A — event.** A facility admission or discharge notification supplies the patient
  identity and the encounter context (which facility, admission/discharge timestamps) directly.
  Retrieval proceeds without additional human confirmation, because the notification already
  carries a scoped, specific encounter.
- **Trigger B — on demand.** A clinician supplies demographics (not a resolved identifier). The
  system resolves candidate patients (with match evidence, not a single guess), and — once a
  patient is confirmed — resolves candidate encounters for that patient and requires the human to
  confirm the specific encounter too, not just the patient. Trigger B is strictly harder than
  Trigger A: Trigger A arrives with encounter context already attached; Trigger B has to establish
  it. The two triggers must not be presented as symmetric inputs to the same operation — they
  differ in exactly this respect, and the acceptance criteria (§9) require both patient *and*
  encounter confirmation for Trigger B specifically.

Both triggers converge on one core pipeline: resolve patient + encounter → retrieve independently
per source → normalize → classify/reconcile → gate. Only the front door and the
identity-confirmation requirement differ.

## 6. Functional requirements

| # | Requirement |
|---|---|
| FR1 | Medication data is retrieved independently from each connected source (minimum: `epic-emulator`, `athena-emulator`); a slow or failed source is bounded (timeout) and does not block or corrupt another source's result. |
| FR2 | `client/clinical`'s `FHIRClient` is reused for connectivity to both sources (it already accepts an arbitrary FHIR base URL — no new client is written from scratch for this). |
| FR3 | `client/clinical` is extended, not bypassed, to support what this phase needs beyond the existing triage use case: a status filter broader than the current hardcoded `status=active` (reconciliation needs the full order history, not just active orders), structured dose/route/frequency fields on the `Medication` dataclass (not only the current flattened `dosage_text`), and a new method to fetch MedicationDispense records. All additions are backward-compatible — existing call sites (`triage-service`) keep their current default behavior unchanged. |
| FR4 | `athena-emulator` is built as a proxy in front of `fhir-service`, with its own auth flavor and its own set of quirks (pagination behavior, required parameters, error envelope), each deliberately different from `epic-emulator`'s equivalents (G9). |
| FR5 | `athena-emulator` supports MedicationRequest, AllergyIntolerance, and MedicationDispense — the same resource surface `epic-emulator` needs for this phase (FR6). |
| FR6 | `epic-emulator` is extended with `(Outside Record)` endpoint variants for Medication, MedicationRequest, and MedicationDispense (G10), modeling Epic's real distinction between data that originated inside vs. outside the organization. |
| FR7 | Every retrieved medication entry is normalized to an RxNorm concept via a normalizer abstraction (live RxNav `findRxcuiByString`/approximate-match calls to start, with an interface that allows a cached/local implementation later — no hard dependency on which implementation is live). The term type reached (ingredient / clinical drug / branded) is recorded per entry. |
| FR8 | Cross-source pairings are classified into exactly five tiers (identical, equivalent, same-ingredient-different-product, ingredient-level-only, unresolved), using structured dose/route/frequency comparison (from FR3's structured fields) in addition to the RxNorm concept/term type — not RxNorm matching alone. |
| FR9 | The count of entries in the "unresolved" tier is surfaced as a headline number on the reconciled view, not buried in a log or a secondary detail panel. |
| FR10 | Each reconciled line is labeled with exactly one of the four Joint-Commission discrepancy types (omission, addition/duplication, change, unclear), citing which source contributed which side of the comparison. |
| FR11 | A precedence-policy config file (YAML) states, per field/question type, which source is generally more trustworthy and why — read and surfaced alongside the reconciled view, never consumed to silently overwrite or discard a source's contribution (G6, non-goals). |
| FR12 | Every field in the reconciled view carries: its source system, that source's response/query time, and the age of the underlying record at that source. |
| FR13 | A source that does not respond (timeout, connection failure, error) is rendered explicitly as "unreachable as of `<time>`" — structurally distinct from, and never rendered identically to, a source that responded with zero medications. |
| FR14 | The overall outcome is exactly one of `RECONCILED`, `DISCREPANCIES_FOUND`, `INCOMPLETE_SOURCES`, following the existing fail-closed enum-gate pattern (`output_gate.py`/`fail_closed.py`). Any single unreachable source forces `INCOMPLETE_SOURCES` — there is no code path from "one source missing" to `RECONCILED`. |
| FR15 | Trigger A (event) accepts a facility admission/discharge notification carrying patient identity and encounter context, and proceeds directly to retrieval — no additional human confirmation step. |
| FR16 | Trigger B (on demand) accepts clinician-supplied demographics, resolves candidate patients with match evidence (never a single silent best guess), and — after patient confirmation — resolves and requires human confirmation of a specific encounter before retrieval proceeds. |
| FR17 | No component in this phase performs or exposes drug-interaction checking, including as a stub that could be misread as "no interactions found" (non-goals). |

## 7. Non-functional requirements

- **Toolchain (assumed, not yet confirmed with the repo owner).** Python, matching
  `triage-service`'s stack and `client/clinical`'s existing library — the new service is a
  deterministic core service in the same shape as `triage-service`, not a new language/runtime.
  `athena-emulator` follows `epic-emulator`'s precedent: Java 21 / Spring Boot.
- **External dependencies.** RxNav (free, no API key) is a genuine runtime dependency for
  normalization (FR7); its own unreachability must be handled the same way an EHR source's
  unreachability is (FR13/FR14) — a normalization failure is not the same as "could not code," and
  the two must not be conflated in what's reported.
- **Scope of "connected sources."** Minimum two (Epic-shaped, Athena-shaped) via the two
  emulators. The original capability statement leaves room for "any additional capabilities the
  environment provides" — no third source is committed in this PRD; if one is added later, it
  must satisfy the same independent-retrieval, per-field-provenance, and unreachable-is-never-empty
  requirements as the first two (FR1, FR12, FR13).
- **Data.** No new fixture/seed pipeline beyond what's needed to exercise reconciliation
  end-to-end (at least one patient with genuine cross-source discrepancies) — reuses
  `fhir-service`'s existing Synthea-seeded data where possible, same convention Phase 4 followed.
- **Security/PHI.** No real PHI. No production credentials. Same posture as `epic-emulator`'s
  emulated auth (dummy keys only).
- **Scope discipline.** Hospital-to-clinic only (non-goals). The nursing-facility extension is
  explicitly named as a *known* future gap, not silently absent.

## 8. Out of scope / deferred (explicit)

| Deferred | Why it's safe to defer now |
|---|---|
| Drug-interaction checking, in any form | Licensed-content dependency; the free NLM API for this was discontinued Jan 2024 — building or stubbing it now would be dishonest about what's actually checked |
| Single merged medication list | Contradicts the deliverable — the discrepancies *are* the output |
| Nursing-facility transition | No real API sandbox exists to build or test against honestly |
| Automatic identity resolution (no human confirmation) | Real-world patient matching has a documented, high false-positive cost; both triggers require a human in the loop for anything ambiguous |
| A real (non-emulated) Epic or Athena sandbox connection | Deterministic, free, already-built emulators are the source of truth this phase; a live-sandbox cross-check is a possible later validation step, not a build dependency (mirrors Phase 4's own access-assumption stance) |
| Production/cloud deployment, Kong routes, K8s manifests | Local-run only, same posture Phase 4 took before any "Phase 4b" |
| A general-purpose master patient index product | The resolver is scoped to this workflow's two triggers only |

## 9. Acceptance criteria

- Every returned line carries its source, that source's response time, and its match confidence.
- Any source that did not respond is reported as unreachable, never as empty.
- Entries that could not be coded are counted and surfaced, never dropped.
- A single unreachable source yields an `INCOMPLETE_SOURCES` outcome, never a `RECONCILED` one.
- Trigger B requires explicit human confirmation of both the patient and the specific encounter
  before retrieval proceeds — confirming the patient alone is not sufficient.

## 10. Open questions

Resolved during this planning pass (decision IDs in [`decisions.md`](./decisions.md); detail in
[`design.md`](./design.md)):

- **Repo module name and shape** — finalized as `med-reconciliation-service/`, one Spring-of-
  Python-style deterministic service (monolith-first, matching `triage-service`/Phase 4's
  reasoning), internal modules per component. `R8`.
- **Where the `epic-emulator` Outside-Record work (FR6) lands procedurally** — tracked as Phase 7
  work in this phase's own `decisions.md`, not a reopened Phase 4 milestone, even though it edits
  a Phase 4 module. `R9`.
- **Precedence-policy schema** — sketched in `design.md` §4 (a table keyed by *question type*, not
  by field). `R10`.
- **RxNorm term-type detection mechanics** — approach sketched in `design.md` §3 (RxNav TTY
  attribute + relationship walk); real validation is M5's job, not settled by the sketch alone.
  `R11`.
- **Real Epic/Athena sandbox as a validation cross-check** — explicitly deferred, no milestone
  allocated this phase; §8 already rules it out as a build dependency. `R12`.
- **Demo/consumer surface** — a CLI script (terminal three-panel view: hospital list / outpatient
  list / reconciled view), same shape as the existing e2e acceptance-test scripts — not a new HTTP
  API or UI this phase. `R13`.

Still genuinely open (deliberately, not an oversight):

- **Whether a third connected source (beyond Epic/Athena-shaped) is added this phase or deferred**
  — the original capability statement's "more to be clarified later" stays open; no milestone
  commits to it. `R14` records the deferral, not a resolution.

## 11. Provenance

This PRD synthesizes a detailed brainstorm document (external research grounding: NCQA/Joint
Commission definitions and discrepancy taxonomy, Epic on FHIR and athenahealth sandbox
documentation, RxNorm/RxNav API behavior including the January 2024 interaction-API discontinuation,
US Core MedicationRequest requirements, HL7 Patient `$match` and the US Identity Matching IG)
provided by the repo owner, reconciled against a direct codebase audit (`epic-emulator`,
`client/clinical`, `triage-service`, `claims-service`'s Provenance usage, `agent-platform`'s
fail-closed gate pattern, and confirmation that `athena-emulator` is still an empty placeholder),
followed by two rounds of scope-clarification questions posed directly to the repo owner (§2).
Several claims in the original brainstorm document were verified or corrected against the actual
codebase during that audit — notably that `client/clinical`'s medication fetch is scoped to the
triage use case only (active-status filter, flattened dosage text, no dispense support) and would
need extension, not just reuse, and that no "Outside Record" concept exists anywhere in the repo
today. This document should be treated as a working draft: several open questions (§10) remain,
and no milestone plan, design doc, or decisions index exists yet.
