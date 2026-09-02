# Phase 7 Milestone Plan — Medication Reconciliation

M1–M8. All **planned, none started**. Kept as its own document rather than folded into
`design.md`, same convention Phase 6 used (`decisions.md` H23) — this phase touches enough
components that a reviewer should be able to see the build order without reading full
architecture first.

Sequencing logic: build the two real sources first (M1–M2), then the client-side plumbing to read
them richly (M3), then identity resolution (M4) in parallel with the normalizer/matcher (M5) since
neither depends on the other, then reconciliation + policy (M6), then provenance + the gate (M7),
then wire both triggers end-to-end and prove it live (M8) — mirroring Phase 4's M1–M5 shape
(build → extend → verify live) but with two new external-shaped sources instead of one.

---

### M1 — `athena-emulator`: proxy, auth, quirks

**Short story:** Build the second edge. Same shape as `epic-emulator` (Phase 4 M1–M4 combined:
pass-through proxy, its own auth flavor, its own named quirks), deliberately divergent from
Epic's quirks.

**Long story:** `athena-emulator` has been an empty placeholder since Phase 2. This milestone
makes it real: a Spring Boot proxy in front of `fhir-service`, gated by an Athena-flavored auth
handshake (need not be identical in mechanism to Epic's SMART Backend Services flow — divergence
here is itself evidence for the "portability isn't provable with one edge" thesis), and at least
two to three named quirks chosen to differ from `epic-emulator`'s (different pagination behavior,
different required-parameter combination, different error envelope shape). Resource surface:
MedicationRequest and AllergyIntolerance to start (MedicationDispense and Outside-Record-style
variants land in M2, alongside `epic-emulator`'s equivalent extension, so both sources gain the
same new surface together rather than drifting).

**Deliverable:** `athena-emulator/` is a real, tested Spring Boot module, runnable alongside
`epic-emulator`, both proxying the same `fhir-service` data with genuinely different quirks.

**Depends on:** nothing new (mirrors already-proven `epic-emulator` patterns).

---

### M2 — Resource-surface parity: MedicationDispense + Outside-Record variants

**Short story:** Both emulators gain fill/dispense data and Epic's Outside-Record endpoint
distinction (R5, R6).

**Long story:** `epic-emulator` gets `(Outside Record)` endpoint variants for
Medication/MedicationRequest/MedicationDispense (R5, R9 — tracked here, not a reopened Phase 4
milestone). `athena-emulator` gains MedicationDispense support as part of its own resource
surface (it has no native "Outside Record" concept to emulate — Athena's real API doesn't
document that same split — so this is an intentional asymmetry between the two emulators, not an
oversight; if that turns out to be wrong once real Athena documentation is checked, it's a cheap
correction here). This milestone is why M1 and M3 are sequenced around it: nothing downstream
needs Outside-Record/dispense data until the normalizer/matcher (M5) and precedence policy (M6).

**Deliverable:** Both emulators respond to MedicationDispense queries; `epic-emulator` responds to
Outside-Record endpoint variants. Tests confirm both, mirroring Phase 4's per-quirk test style.

**Depends on:** M1 (`athena-emulator` must exist first).

---

### M3 — `client/clinical` extension (backward-compatible)

**Short story:** Broaden the existing medication client so Phase 7 can use it without bypassing
it or breaking `triage-service`.

**Long story:** `get_medications()` today hardcodes `status=active` and flattens dosage to a text
string (`fhir_client.py:354-382`). This milestone adds an optional status filter (defaulting to
today's `active`-only behavior, so `triage-service`'s existing call sites are unaffected),
structured dose/route/frequency fields on the `Medication` dataclass alongside the existing
`dosage_text`, and a new `get_medication_dispenses()` method. This is the one milestone that
touches a package outside `med-reconciliation-service`/the emulators — kept small and
purely additive on purpose (FR3, non-goals: "modifying `triage-service`'s existing behavior" is
explicitly out of scope).

**Deliverable:** `client/clinical` supports both emulators' full resource surface (post-M2);
`triage-service`'s existing test suite passes unmodified, proving backward compatibility.

**Depends on:** M2 (needs both emulators' full surface to build/test against).

---

### M4 — Identity + encounter resolver

**Short story:** Both triggers get a real patient/encounter resolution path — Trigger A passes
context through, Trigger B requires human confirmation of both.

**Long story:** Builds `identity.py` (design.md §2): for Trigger A, accept a notification's
patient identity + encounter context directly. For Trigger B, accept clinician-supplied
demographics, search both sources, return scored candidates (never a single silent best guess),
require explicit confirmation, then repeat the same candidate/confirm pattern for encounter
selection once the patient is confirmed. No merge/auto-resolution logic — ambiguous results are a
terminal state requiring a human decision, not a retry loop.

**Deliverable:** Both trigger paths produce a confirmed `(patient_id, encounter_id)` pair (or an
explicit unresolved/pending state) that the rest of the pipeline (M5–M8) can take as input.
Testable independently of the normalizer/matcher — can run against M3's client with hand-seeded
ambiguous-patient fixtures.

**Depends on:** M3 (`client/clinical`'s search capability against both sources).

---

### M5 — `med-normalizer`: RxNorm concept resolution + five-tier match classification

**Short story:** The honest hard part — resolve each entry to an RxNorm concept, then classify
cross-source pairs using real structured dose/route/frequency comparison.

**Long story:** Implements `normalizer.py` and `match.py` per `design.md` §3. Integrates live
RxNav calls (`findRxcuiByString`, relationship/TTY lookups) behind the R3 abstraction interface.
This is where `design.md` §3's sketch gets validated against real RxNav behavior — rate limits,
approximate-match quality, and whether the relationship API actually supports walking from a
clinical-drug TTY back to its ingredient reliably. If it doesn't, that gets documented as a
decision here, not assumed away. The "unresolved" count (FR9) is a first-class output of this
milestone, not an afterthought.

**Deliverable:** Given two sources' medication lists for a test patient (including at least one
genuine same-ingredient-different-product case, e.g. metoprolol tartrate vs. succinate), produces
correct five-tier classifications, with the unresolved count reported explicitly.

**Depends on:** M2 (needs both sources' full resource surface, including dispense data for
matching against the precedence policy that lands in M6).

---

### M6 — `recon-engine` + precedence-policy config

**Short story:** Turn match results into the four Joint-Commission discrepancy types, with the
precedence-policy YAML attached as a reference label.

**Long story:** Implements `recon.py` and `precedence.py` per `design.md` §4. Unpaired entries
(present in one source, absent in the other) become `omission`; same-therapeutic-class duplicates
(reusing `triage-service`'s existing duplicate-class rule as prior art, not as shared code) become
`addition_duplication`; differing dose/route/frequency on an otherwise-matched pair become
`change`; anything unresolved or irreconcilably conflicting becomes `unclear`. `precedence.py`
loads `precedence-policy.yaml` and attaches an advisory label per line — verified in this
milestone's tests to never cause a line's source data to be dropped or overwritten (the
non-goal this whole design is built around).

**Deliverable:** A `ReconciledLine[]` for a test patient, each line labeled with exactly one
discrepancy type, every source's contribution still present, precedence labels attached and
provably non-destructive.

**Depends on:** M5 (needs match classifications as input) and M4 is not a hard dependency (can run
against hand-supplied patient/encounter IDs until M4 and M6 are wired together in M8).

---

### M7 — Provenance + fail-closed gate

**Short story:** Every field gets source/time/age; the run resolves to
`RECONCILED`/`DISCREPANCIES_FOUND`/`INCOMPLETE_SOURCES`, mirroring `output_gate.py`'s pattern.

**Long story:** Implements `provenance.py` and `gate.py` per `design.md` §6. Unreachable-source
handling is the acceptance-critical part: a source that times out or errors must produce a
distinct, explicit "unreachable as of `<time>`" state per field it would have contributed —
verified with a test that kills a source mid-run and confirms the output is never
indistinguishable from "this source had zero medications." The gate's `INCOMPLETE_SOURCES` case
is tested to win over `RECONCILED`/`DISCREPANCIES_FOUND` unconditionally whenever any source is
unreachable — this is the single most important test in the milestone (acceptance criteria,
`prd.md` §9).

**Deliverable:** Given M6's `ReconciledLine[]s` plus per-source reachability, produces the correct
outcome enum in all combinations, including partial-reachability edge cases.

**Depends on:** M6.

---

### M8 — End-to-end wiring, acceptance case, and demo

**Short story:** Wire both triggers through M1–M7, prove it live against two real (emulated)
sources, and build the demo CLI — including the "kill a source mid-demo" moment.

**Long story:** Mirrors Phase 4's M5: an acceptance case run against real running services, not
just unit tests. One seeded patient with genuine cross-source discrepancies (at least one of each
discrepancy type, plus a metoprolol-style same-ingredient-different-product case) is run through
both Trigger A (simulated notification) and Trigger B (simulated clinician demographic lookup +
confirmation) end-to-end against live `epic-emulator` and `athena-emulator` instances. Builds
`cli.py` (`design.md` §7): the three-panel terminal view, then a scripted run that stops
`athena-emulator` partway through and re-runs to show the `INCOMPLETE_SOURCES` degrade live —
the actual "ninety-second demo" from the original brainstorm doc, verified working, not just
described.

**Deliverable:** `e2e/test_med_reconciliation_acceptance.py` (or similarly named, matching the
existing `e2e/test_epic_emulator_acceptance.py` convention) passes against real running services;
`cli.py` demo runs and visibly degrades to `INCOMPLETE_SOURCES` when a source is killed.

**Depends on:** M4, M7.

---

## What's explicitly not a milestone here

Per `prd.md` §8/§10: a real Epic/Athena sandbox cross-check, a third connected source, production/
cloud deployment, and the nursing-facility extension. None of these get a milestone number; adding
one later is a new decision, not an oversight in this plan.
