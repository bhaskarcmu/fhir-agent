# Phase 7 PRD — Medication Reconciliation

**Status:** DRAFT — scope expanded a second time with the repo owner (agentic clinical
experience, human-override + audit trail, immutable record-keeping, provenance) after the initial
deterministic-core planning pass. `design.md`, `decisions.md`, `milestone-plan.md` all updated to
match. No code written yet.
**Companion doc:** [`design.md`](./design.md) — architecture, component breakdown, the agent tool
contract, the audit-ledger and Composition-record sketches, precedence-policy and RxNorm-matching
sketches, and the reconciled-line data model.
**Milestone plan:** [`milestone-plan.md`](./milestone-plan.md) — M1–M12, kept as its own document,
same convention Phase 6 used (`phase6/decisions.md` H23).
**Decision index:** [`decisions.md`](./decisions.md) — `R1`–`R23`.
**Extends:** Phase 1 (`fhir-service`, `triage-service`, `client/clinical`), Phase 4
(`epic-emulator`, extended — §6), Phase 6 (`agent-platform` — the new conversational agent is
built on it, not a reinvention, R23). Builds out `athena-emulator`, reserved as an empty
placeholder since Phase 2.
**Owner:** TBD

---

## 1. Problem statement

*(Unchanged from the first planning pass — restated for context.)* Of the national
transitions-of-care indicators, medication reconciliation is the only one that is genuinely a
data-merge problem. NCQA and The Joint Commission both define it as comparing the medications
ordered at discharge against the outpatient record and resolving discrepancies — omissions,
duplications, changes, and unclear information. The Joint Commission's own language ("a good
faith effort... will be considered as meeting the intent" when complete information can't be
obtained) is this platform's existing fail-closed doctrine, restated as a regulatory standard.

**What changed in this pass.** The first planning round scoped a deterministic reconciliation
core (M1–M7 in the original plan). Working through what a clinician would actually touch surfaced
a real question with a wrong-by-default answer: *should any of this be conversational?* The
answer, worked out across this conversation, is layered rather than all-or-nothing:

- **Yes** for the front door (Trigger B intake) and for explaining results — both are pure
  orchestration over deterministic tools, the same shape `mcp-agent`/`claims-agent` already use
  elsewhere in this repo.
- **Yes, carefully** for letting a human override a computed classification — real clinicians
  catch things automation gets wrong, but the override has to be an attributed, permanent,
  additive fact, never a silent correction.
- **No** for the fail-closed gate itself. A chat interface is exactly the surface that makes
  waving away an `INCOMPLETE_SOURCES` result feel easy and low-stakes, which is precisely the
  failure mode the gate exists to prevent. The Joint Commission's own "good faith effort" language
  points at the correct alternative: a formal, persisted, queryable record of what was attempted —
  not a conversational shortcut to relabeling the outcome.

This PRD now scopes both halves: the deterministic reconciliation core, and the agentic/audit
layer built carefully around its edges — never inside its safety-critical center.

## 2. Decisions already made (via brainstorm — see `decisions.md`)

| Topic | Decision |
|---|---|
| Epic-side source | `epic-emulator` only. |
| Athena-side source | Build `athena-emulator` for real, this phase. |
| Drug normalization | Abstraction layer, live RxNav first. |
| Identity/encounter resolution | New minimal resolver, human-confirmed. |
| Epic "Outside Record" distinction | Modeled in `epic-emulator` this phase. |
| MedicationDispense | In scope, both emulators. |
| Match-classification rigor | Real structured dose/route/frequency comparison. |
| Repo shape (deterministic core) | One new service, `med-reconciliation-service/`. |
| **Conversational Trigger-B intake** | **New this pass** — a new agent, `med-reconciliation-agent/`, mirrors `mcp-agent`'s tool-use shape: extracts demographics, calls the resolver's tools, relays explicit human confirmation. Never resolves ambiguity itself. |
| **Result explanation** | **New this pass** — the same agent narrates the reconciled view/discrepancies in plain language, grounded only in the deterministic output it's given — same non-authoritative pattern `claims-agent` uses for adjudication decisions. |
| **Classification/discrepancy override** | **New this pass** — a human can submit an explicit, attributed override of a computed RxNorm classification or discrepancy type through the agent. The override is appended to an audit ledger; the original computed value is never deleted, hidden, or silently replaced. |
| **Fail-closed gate stays out of agent reach** | **New this pass, explicitly reaffirmed** — no tool exists for changing `RECONCILED`/`DISCREPANCIES_FOUND`/`INCOMPLETE_SOURCES`. The safeguard is the *absence* of a corresponding tool, not a runtime check the agent could route around. |
| **Formal, immutable record** | **New this pass** — every run (any outcome) generates a FHIR `Composition` ("Medication Reconciliation Record") with a per-source attempt log, the reconciled lines, and the gate outcome. This is the mechanism satisfying the Joint Commission's "good faith effort" standard — not a chat conversation. |
| **Good-faith-effort narrative is templated, not LLM-generated** | **New this pass** — the attempt log's text is built from a fixed template populated with real telemetry (timestamps, retries, durations). A compliance-relevant document must not risk hallucinated facts. |
| **Manual-verification follow-up** | **New this pass** — captured as a new, appended `Provenance` entry (who, when, method, outcome) on the same Composition. Never overwrites the original computed record or the gate value. |
| **Agent built on `agent-platform`** | **New this pass** — `med-reconciliation-agent` reuses Phase 6's memory/session, observability, provider-abstraction, and output-gate *pattern* (a distinct, agent-turn-scoped enum — not the clinical `ReconciliationOutcome` gate) rather than reinventing agent infrastructure. |

## 3. Goals

**Deterministic core (unchanged from first pass):**

- **G1–G10** — independent multi-source retrieval, drug concept normalization, five-tier match
  classification, four-category discrepancy labeling, field-level provenance/freshness, a
  precedence *reference* policy (never an auto-merge), the fail-closed reconciliation gate, the
  two triggers converging on one core pipeline, a real second edge (`athena-emulator`), and Epic's
  Outside-Record distinction modeled in `epic-emulator`. Full detail unchanged — see prior
  revision, preserved in git history; restated compactly here since this section now also covers
  the agentic layer.

**Agentic and audit layer (new this pass):**

- **G11 — Conversational Trigger-B intake.** A new agent (`med-reconciliation-agent`) accepts a
  natural-language request, extracts demographics, and calls the identity/encounter resolver's
  tools (M4) — never deciding a match itself.
- **G12 — Grounded explanation.** The same agent narrates a reconciled view — discrepancy types,
  classifications, the gate outcome, unresolved count — in plain language, with every claim
  traceable to the deterministic data it's summarizing. It introduces no fact not already present
  in that data.
- **G13 — Audited human override.** A clinician can explicitly override a computed RxNorm
  classification or discrepancy type through the agent. Every override is attributed to a specific
  human, timestamped, reasoned, and appended — never a silent correction, never a deletion of the
  original computed value.
- **G14 — The gate is structurally unreachable from the agent.** No tool, prompt path, or
  conversational flow can change `RECONCILED`/`DISCREPANCIES_FOUND`/`INCOMPLETE_SOURCES`. This is
  enforced by not building the tool that would do it — an architectural absence, not a runtime
  guard that could be bypassed or misconfigured.
- **G15 — A formal, immutable Medication Reconciliation Record.** A FHIR `Composition` is
  generated and persisted at the end of every run, any outcome, containing the per-source attempt
  log, the reconciled lines, the unresolved count, and the gate outcome.
- **G16 — Templated, not generated, compliance narrative.** The attempt log's text — the thing
  that satisfies "a good faith effort... documented" — is built from a fixed template and real
  telemetry, never free-form LLM prose, so the compliance-relevant facts in the record cannot be a
  hallucination.
- **G17 — Append-only manual-verification capture.** A human's out-of-band follow-up (e.g., a
  phone call confirming a source's data) becomes a new `Provenance` entry on the existing
  Composition — attributed, timestamped, describing method and outcome — and never mutates the
  original computed record.
- **G18 — Agent infrastructure is reused, not reinvented.** `med-reconciliation-agent` is built on
  `agent-platform` (Phase 6): its memory/session store, observability instrumentation, provider
  abstraction (so it isn't hardcoded to one LLM vendor), and the output-gate *pattern* — applied to
  a new, agent-turn-scoped enum, distinct from and with no authority over the clinical
  `ReconciliationOutcome` gate (G14).

## 4. Non-goals

**Unchanged from first pass:** a single merged medication list; auto-resolving ambiguous patient
identity; drug-interaction assessment; extending to the nursing-facility transition; modifying
`triage-service`'s existing behavior; production/cloud deployment; a general-purpose MPI product.

**New this pass:**

- **The agent never computes or infers a clinical fact from its own reasoning.** Identity matches,
  RxNorm concepts, match tiers, discrepancy types, and the gate outcome are always produced by
  deterministic code (M4–M7); the agent only orchestrates calls to that code and relays explicit
  human input. This is the same non-negotiable boundary this repo already holds for `mcp-agent`
  and `claims-agent` (CLAUDE.md: "the agent orchestrates but holds no clinical logic"), applied
  here.
- **No conversational or tool-based path can alter the fail-closed gate.** Not "discouraged" —
  structurally absent. See G14.
- **No LLM-generated prose in the compliance-relevant portion of the record, this phase.** A
  cosmetic narrative-polish layer over the templated facts is a plausible later addition, not
  built now — the risk of a document that has to satisfy a real regulatory standard containing
  even slightly hallucinated wording isn't worth the readability gain yet.
- **Overrides and manual-verification entries are never destructive.** No mechanism in this phase
  deletes, hides, or replaces an original computed value — every correction is an addition to the
  record, visible alongside what it corrects.

## 5. Triggers & users

**Primary user:** a clinician or care-transitions staff member — now joined by whoever performs
manual-verification follow-up and classification review, who may be the same person or a
different role (pharmacist, care coordinator) depending on deployment; this phase doesn't assume
which.

- **Trigger A — event.** Unchanged: a facility admission/discharge notification supplies patient
  identity and encounter context; retrieval proceeds without additional human confirmation.
- **Trigger B — on demand, two entry points converging on one resolver (M4):**
  - **Structured.** Demographics supplied directly (a form, an API call) — the original scope.
  - **Conversational (new).** A clinician talks to `med-reconciliation-agent` in natural language
    ("reconcile meds for the patient in bed 4"); the agent extracts demographics and calls the
    same resolver tools the structured path uses. Both entry points hit identical candidate
    resolution and identical human-confirmation requirements (patient, then encounter) — the
    agent changes how the request arrives, not what's required before retrieval proceeds.
- **Post-retrieval, agent-mediated (new).** Once a reconciled view exists, the same agent can: (a)
  explain it in plain language (G12), (b) accept an explicit override of a classification or
  discrepancy type (G13), and (c) accept a manual-verification follow-up report (G17) — all
  logged, none capable of touching the gate outcome (G14).

## 6. Functional requirements

**Deterministic core — FR1–FR17, unchanged from the first pass** (independent per-source
retrieval; `client/clinical` reuse and backward-compatible extension; `athena-emulator` build-out;
MedicationDispense + Outside-Record support on both emulators; RxNorm normalization with recorded
term type; five-tier structured match classification; headline unresolved count; four-type
discrepancy labeling with per-side source citation; reference-only precedence policy; per-field
source/response-time/age; explicit unreachable-source rendering; the three-outcome fail-closed
gate with `INCOMPLETE_SOURCES` always winning; both triggers' human-confirmation requirements; no
interaction-checking, stubbed or otherwise). Full text preserved in git history; unchanged in
substance in this revision.

**Agentic and audit layer — new this pass:**

| # | Requirement |
|---|---|
| FR18 | `med-reconciliation-agent` accepts a natural-language Trigger-B request, extracts demographics, and calls the identity/encounter resolver's tools (M4); it never resolves ambiguity itself — any uncertain match is presented to the human exactly as the structured path would present it. |
| FR19 | The agent explains a reconciled view — discrepancy types, match classifications, the gate outcome, the unresolved count — in plain language, with every stated fact traceable to the specific deterministic field it summarizes. It never introduces a claim absent from that data. |
| FR20 | A human can submit an explicit override of a computed RxNorm classification or discrepancy type through the agent. The override is captured as a new, attributed (specific human identity), timestamped, reasoned entry in the audit ledger (M9) — the original computed value is retained and remains visible alongside it, never deleted or replaced in place. |
| FR21 | The agent exposes no tool, command, or conversational path capable of changing the fail-closed gate's outcome. `gate.py`'s computation is the only writer of that value, in every build; this is verified by the absence of a corresponding tool definition, not by a runtime permission check alone. |
| FR22 | At the end of every pipeline run — `RECONCILED`, `DISCREPANCIES_FOUND`, or `INCOMPLETE_SOURCES` alike — a FHIR `Composition` ("Medication Reconciliation Record") is generated and persisted, containing the per-source attempt log, the reconciled lines (or a reference to them), the unresolved count, and the gate outcome. |
| FR23 | The per-source attempt log's narrative text is produced from a fixed template populated with real telemetry (query timestamps, retry counts, durations, failure reasons) — never free-form LLM-generated text. This is the artifact that satisfies the Joint Commission's "good faith effort... documented" standard for an `INCOMPLETE_SOURCES` outcome. |
| FR24 | A human's manual-verification follow-up (e.g., confirming a source's data by phone) is captured as a new `Provenance` entry appended to the existing Composition — attributed to the specific human, timestamped, naming the method and outcome — and never overwrites, edits, or is merged into the original computed record or gate value. |
| FR25 | Every override (FR20) and every manual-verification entry (FR24) is independently queryable and rendered in full alongside the original computed values when the record is later reviewed — no later action hides or supersedes an earlier one in the stored record. |

## 7. Non-functional requirements

**Unchanged:** toolchain assumptions (Python for the deterministic core, matching
`triage-service`; Java/Spring Boot for `athena-emulator`, matching `epic-emulator`), RxNav as a
genuine runtime dependency with its own unreachability handling, minimum two connected sources,
no new fixture pipeline beyond what exercises reconciliation end-to-end, no real PHI/production
credentials, hospital-to-clinic scope only.

**New this pass:**

- **Agent tier toolchain.** `med-reconciliation-agent` is Python, built directly on
  `agent-platform` (Phase 6) — its session/memory store, OTel instrumentation, and multi-provider
  seam are reused, not reimplemented. Its own turn-safety enum (governing what the agent is
  allowed to say/do in a given turn) is a **new, agent-scoped enum**, structurally distinct from
  and with zero write access to the clinical `ReconciliationOutcome` gate (G14) — these are two
  different gates guarding two different things, and conflating them would be the exact mistake
  this design is built to avoid.
- **Record persistence.** The `Composition` and its `Provenance` entries are written to
  `fhir-service` directly from `med-reconciliation-service`, following `claims-service`'s
  `FhirArtifactBuilder` as a pattern precedent — not shared code, since claims-service's builder is
  claims-specific.
- **Auditability.** The audit ledger (overrides + manual-verification entries) must support
  reconstructing, for any record, exactly what was computed, what was overridden, by whom, when,
  and why, without losing any prior state — append-only storage, not update-in-place.

## 8. Out of scope / deferred (explicit)

**Unchanged:** drug-interaction checking; a single merged medication list; the nursing-facility
transition; automatic identity resolution; a real (non-emulated) Epic/Athena sandbox connection as
a build dependency; production/cloud deployment; a general-purpose MPI product.

**New this pass:**

| Deferred | Why it's safe to defer now |
|---|---|
| LLM-generated (even lightly polished) compliance narrative | The templated version (FR23) already satisfies the regulatory standard; adding generated prose is a readability nicety with real hallucination risk in a document meant to prove a good-faith effort |
| Role/permissions model for who may submit an override or manual-verification entry | Real design work (pharmacist vs. clinician vs. care coordinator) not yet scoped — this phase captures *that* an override happened and *who* did it, not an authorization policy for *who's allowed to* |
| A UI for reviewing the audit ledger | The ledger and Composition are queryable FHIR data this phase; a dedicated review screen is a future phase's problem, same posture as the rest of this PRD's UI deferrals |

## 9. Acceptance criteria

**Unchanged:** every line carries source, response time, and match confidence; an unreachable
source is reported as unreachable, never empty; uncoded entries are counted and surfaced, never
dropped; a single unreachable source yields `INCOMPLETE_SOURCES`, never `RECONCILED`; Trigger B
requires explicit human confirmation of both patient and encounter.

**New this pass:**

- No conversational path, tool, or agent output can change the fail-closed gate's outcome — this
  is verified by the absence of a corresponding tool in the agent's tool set, not only by a
  runtime check.
- Every override and every manual-verification entry is independently visible in the persisted
  record; none suppresses, hides, or replaces the original computed value.
- Every `INCOMPLETE_SOURCES` outcome has a corresponding, persisted, queryable "good faith effort"
  attempt log — satisfying Joint Commission intent as a fact about the record, not as something
  asserted only in conversation.

## 10. Open questions

Resolved this pass (see `decisions.md` `R15`–`R23`; detail in `design.md`): conversational
Trigger-B intake, grounded explanation, audited override capability, the gate's structural
unreachability from the agent, the formal Composition record, templated (non-LLM) compliance
narrative, append-only manual-verification capture, and building the agent on `agent-platform`.

Still open:

- **Composition resource shape** — plain FHIR `Composition` vs. a custom profile. Real design
  work for `design.md`, not resolved here.
- **Role/permissions model** for override and manual-verification submission (§8 — deliberately
  deferred, not decided).
- **Whether a cosmetic narrative-polish layer is ever added** over the templated attempt log
  (§8/G16) — left open, not committed either way.
- **Whether a third connected source is added this phase or deferred** — still open from the
  first pass (`R14`).

## 11. Provenance

This PRD reflects two brainstorming passes with the repo owner. The first scoped a deterministic
reconciliation core against a direct codebase audit. The second worked through, in conversation,
whether and where an agentic interface belongs — landing on a layered answer (conversational
intake and explanation: yes; audited override: yes, carefully; the fail-closed gate itself: no)
and, once the gate was ruled out for chat, the formal-record alternative that satisfies the same
regulatory "good faith effort" language without a conversational shortcut. Both passes' reasoning
is preserved in this repo's own working history; this document is the synthesis, not the source.
