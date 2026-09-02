# Phase 7 Milestone Plan — Medication Reconciliation

M1–M12. All **planned, none started**. Expanded from the original M1–M8 after a second scope pass
added the agentic/audit layer (`prd.md` §2, §10). M1–M7 are unchanged in substance; M8 (formerly
the end-to-end acceptance case) is now M12, and M8–M11 are new.

Sequencing logic, updated: build the two real sources first (M1–M2), then the client-side
plumbing (M3), then split into parallel tracks — identity resolution (M4) and the
normalizer/matcher (M5) don't depend on each other — converge into reconciliation + policy (M6),
then provenance + the deterministic gate (M7). From there, the **audit/record layer (M8–M9)** and
the **agent layer (M10–M11)** are themselves a second parallel split: the record/audit mechanism
doesn't need the agent to exist, and the agent's intake/explanation functions don't need the audit
ledger to exist — only M11 (override/verification *tools*) needs both. Everything converges in
M12.

---

### M1 — `athena-emulator`: proxy, auth, quirks

**Short story:** Build the second edge. Same shape as `epic-emulator`, deliberately divergent
quirks.

**Long story:** A Spring Boot proxy in front of `fhir-service`, gated by an Athena-flavored auth
handshake, with 2–3 named quirks chosen to differ from `epic-emulator`'s (pagination behavior,
required-parameter combination, error envelope shape). Resource surface: MedicationRequest and
AllergyIntolerance to start; MedicationDispense and Outside-Record variants land in M2.

**Deliverable:** `athena-emulator/` is a real, tested module, runnable alongside `epic-emulator`.

**Depends on:** nothing new.

---

### M2 — Resource-surface parity: MedicationDispense + Outside-Record variants

**Short story:** Both emulators gain fill/dispense data; `epic-emulator` gains Epic's
Outside-Record endpoint distinction.

**Long story:** `epic-emulator` gets `(Outside Record)` variants for
Medication/MedicationRequest/MedicationDispense (tracked here, not a reopened Phase 4 milestone —
`decisions.md` R9). `athena-emulator` gains MedicationDispense support; it has no native
"Outside Record" concept to emulate (Athena's real API doesn't document that split), an
intentional asymmetry, not an oversight — correctable cheaply if real Athena documentation later
says otherwise.

**Deliverable:** Both emulators respond to MedicationDispense queries; `epic-emulator` responds to
Outside-Record variants. Tested per-quirk, mirroring Phase 4's test style.

**Depends on:** M1.

---

### M3 — `client/clinical` extension (backward-compatible)

**Short story:** Broaden the existing medication client without breaking `triage-service`.

**Long story:** `get_medications()` today hardcodes `status=active` and flattens dosage to text.
This milestone adds an optional status filter (defaulting to today's behavior), structured
dose/route/frequency fields alongside `dosage_text`, and a new `get_medication_dispenses()`
method. Purely additive — `triage-service`'s existing test suite must pass unmodified.

**Deliverable:** `client/clinical` supports both emulators' full resource surface;
`triage-service` unaffected.

**Depends on:** M2.

---

### M4 — Identity + encounter resolver

**Short story:** Both triggers get a real, human-confirmed patient/encounter resolution path.

**Long story:** `identity.py`: Trigger A passes notification context through directly; Trigger B
(structured) accepts demographics, searches both sources, returns scored candidates, requires
explicit confirmation of patient then encounter. No auto-resolution — ambiguity is a terminal
state requiring a human decision.

**Deliverable:** Both trigger paths produce a confirmed `(patient_id, encounter_id)` pair or an
explicit unresolved/pending state.

**Depends on:** M3.

---

### M5 — `med-normalizer`: RxNorm concept resolution + five-tier match classification

**Short story:** The honest hard part — RxNorm resolution plus real structured
dose/route/frequency comparison.

**Long story:** `normalizer.py` and `match.py`. Integrates live RxNav calls behind the R3
abstraction. Validates the term-type/relationship-walk sketch (`design.md`) against real RxNav
behavior — rate limits, approximate-match quality, whether the relationship API supports walking
from a clinical-drug TTY back to its ingredient. Reports the unresolved count as a first-class
output.

**Deliverable:** Correct five-tier classification for a test patient with a genuine
same-ingredient-different-product case, unresolved count reported explicitly.

**Depends on:** M2. (Runs in parallel with M4 — neither needs the other's output.)

---

### M6 — `recon-engine` + precedence-policy config

**Short story:** Turn match results into the four Joint-Commission discrepancy types, with the
precedence policy attached as a reference label.

**Long story:** `recon.py` and `precedence.py`. Unpaired entries → `omission`; duplicate
therapeutic class → `addition_duplication`; differing dose/route/frequency on a matched pair →
`change`; unresolved/irreconcilable → `unclear`. `precedence.py` loads
`precedence-policy.yaml` and attaches an advisory label — tested to never cause a line's source
data to be dropped or overwritten.

**Deliverable:** A `ReconciledLine[]` for a test patient, every source's contribution intact,
precedence labels attached non-destructively.

**Depends on:** M5.

---

### M7 — Provenance + fail-closed gate

**Short story:** Every field gets source/time/age; the run resolves to one of three outcomes.

**Long story:** `provenance.py` and `gate.py`. A source that times out or errors produces a
distinct, explicit "unreachable as of `<time>`" state — verified with a test that kills a source
mid-run. `INCOMPLETE_SOURCES` is tested to win over the other two outcomes unconditionally
whenever any source is unreachable — the single most important test in the milestone.

**Deliverable:** Correct outcome enum for all reachability/discrepancy combinations.

**Depends on:** M6.

---

### M8 — The Medication Reconciliation Record

**Short story:** Every run — any outcome — generates a persisted, immutable FHIR `Composition`.

**Long story:** `composition.py` (`design.md` §4). Builds the per-source attempt log from real
telemetry (query timestamps, retries, durations, failure reasons) via a fixed template — never
generated text (`decisions.md` R20). Persists the Composition to `fhir-service`, referencing the
`ReconciledLine[]` and the gate outcome. This is the artifact that turns "a good faith effort was
made" from an assertion into a queryable fact — the concrete alternative to a chat-based override
that this whole sub-scope exists to provide.

**Deliverable:** A Composition exists in `fhir-service` for every M7 run, correctly reflecting the
attempt log and outcome, for both a fully-reachable run and a run with a killed source.

**Depends on:** M7.

---

### M9 — Audit ledger (overrides + manual verification)

**Short story:** One append-only mechanism, reused for classification/discrepancy overrides and
for manual-verification follow-up.

**Long story:** `audit.py` (`design.md` §5). `AuditEntry`s are written as `Provenance` resources
targeting an existing Composition. Storage-layer guarantee, not just convention: nothing overwrites
or replaces prior state — reading a record's full history means reading the Composition plus every
`AuditEntry` targeting it. This milestone builds the ledger itself; wiring it to the agent's tools
is M11.

**Deliverable:** Given an existing Composition, an override and a manual-verification entry can
both be submitted (via direct calls, no agent yet) and both are independently retrievable
afterward, with the original computed values still intact and visible.

**Depends on:** M8.

---

### M10 — `med-reconciliation-agent`: conversational intake + explanation

**Short story:** A new agent, built on `agent-platform`, handles conversational Trigger-B intake
and narrates results — no override/verification capability yet.

**Long story:** `agent.py` and `explain.py` (`design.md` §3). Reuses Phase 6's session/memory
store, observability instrumentation, and multi-provider seam rather than reinventing agent
infrastructure (`decisions.md` R23). Calls `search_patients`/`search_encounters`/
`confirm_patient`/`confirm_encounter`/`get_reconciled_view` — the read/orchestration half of the
tool contract (`design.md` §3). `explain.py`'s system prompt constrains it to state only facts
present in the data it's given, same grounding discipline as Phase 6 M6's knowledge-base
citations. `turn_gate.py` (the agent's own turn-safety enum) is built here too — structurally
separate from, and with no access to, `gate.py`'s clinical outcome.

**Deliverable:** A clinician can complete Trigger B end-to-end in natural language (ambiguous
patient → candidates → explicit confirmation → encounter confirmation → retrieval), and ask the
agent to explain the resulting reconciled view, with every explained fact traceable to real data.

**Depends on:** M4 (resolver tools), M7 (something to retrieve and explain).

---

### M11 — Agent-mediated override and manual-verification submission

**Short story:** Extend the M10 agent with the write half of the tool contract —
`submit_classification_override` and `submit_manual_verification` — and confirm the gate stays
unreachable.

**Long story:** Wires `audit.py` (M9) behind two new tools. This milestone's actual test target is
negative: confirm there is no tool, prompt injection path, or conversational sequence that reaches
`gate.py`'s output — the tool contract table in `design.md` §3 is the specification, and this
milestone is where it gets adversarially tested, not just documented. A submitted override or
verification must appear in the record alongside the original computed value, never replacing it.

**Deliverable:** A clinician can submit an override or a manual-verification report through the
agent; both are correctly stored via M9; a documented adversarial test suite confirms no
conversational path can alter the gate's outcome.

**Depends on:** M9, M10.

---

### M12 — End-to-end wiring, acceptance case, and demo

**Short story:** Everything, live, against two real (emulated) sources — three demo beats instead
of one.

**Long story:** Mirrors Phase 4's M5: a live acceptance case, not just unit tests. One seeded
patient with genuine cross-source discrepancies, run through both triggers end-to-end. Three demo
beats (`design.md` §7): (1) the original three-panel reconciled view, with a source killed
mid-demo showing the `INCOMPLETE_SOURCES` degrade; (2) a conversational Trigger-B request
resolving an ambiguous candidate with explicit confirmation; (3) a classification override
submitted through the agent, followed by pulling up the record and showing the original computed
value and the override side by side, neither hidden by the other.

**Deliverable:** `e2e/test_med_reconciliation_acceptance.py` passes against real running services;
both CLI demos (`cli.py` structured, `med-reconciliation-agent`'s conversational mode) run and
demonstrate all three beats.

**Depends on:** M11.

---

## What's explicitly not a milestone here

Per `prd.md` §8/§10: a real Epic/Athena sandbox cross-check, a third connected source,
production/cloud deployment, the nursing-facility extension, an LLM-generated (even lightly
polished) compliance narrative, a role/permissions model for who may submit overrides, and a
dedicated audit-ledger review UI. None of these get a milestone number; adding one later is a new
decision, not an oversight in this plan.
