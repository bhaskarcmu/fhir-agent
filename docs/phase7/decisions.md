# Phase 7 — Decisions

ADR-style index, same convention as Phase 2 (`D`/`C`), Phase 3 (`P`), Phase 4 (`E`), Phase 6
(`H`). `R` here stands for **R**econciliation. Each entry: status, one-line rationale, and where
the full reasoning lives (this repo's chat-driven planning process — captured in `prd.md` §2/§10
and `design.md` — rather than a separate meeting doc).

| ID | Decision | Status | Rationale / where it lives |
|---|---|---|---|
| R1 | Epic-side source is `epic-emulator` only, not a live Epic sandbox | Accepted | Deterministic, free, already built (Phase 4). A live sandbox is a possible later cross-check, never a build dependency — see R12. `prd.md` §2, §8. |
| R2 | `athena-emulator` is built out for real this phase, not stubbed or replaced with a live sandbox | Accepted | The reserved-since-Phase-2 "second edge" — proves the portability claim Phase 4 left open. Quirks deliberately diverge from Epic's (`prd.md` G9). |
| R3 | Drug normalization uses an abstraction layer — live RxNav calls first, room for a cached/local implementation later | Accepted | Mirrors the provider-abstraction shape from Phase 6 M5 (`agent-platform` provider seam). Keeps the normalizer swappable without keeping the free live API as a permanent hard dependency. `prd.md` FR7. |
| R4 | Patient + encounter identity resolution gets a new, narrowly-scoped resolver this phase | Accepted | Not delegated entirely to each source's native matching (loses a unified confirmation UX), not deferred (both triggers need it — Trigger B especially), not a full MPI product. `prd.md` §5. |
| R5 | `epic-emulator` is extended with `(Outside Record)` endpoint variants (Medication/MedicationRequest/MedicationDispense) | Accepted | Models Epic's real source-provenance distinction directly in the emulator, not only in this PRD's prose — strengthens the "independently arrived at the same design" claim from the original brainstorm. `prd.md` G10, FR6. |
| R6 | MedicationDispense (fill status) is in scope, on both emulators | Accepted | A third per-medication signal ("was it ever obtained") the precedence policy (R10) explicitly needs. Real added build cost, accepted deliberately rather than discovered late. `prd.md` FR5. |
| R7 | Match classification uses real structured dose/route/frequency comparison, not RxNorm-concept-ID matching alone | Accepted | The five-tier classification (identical/equivalent/same-ingredient-different-product/ingredient-level-only/unresolved) is the actual hard problem this build exists to solve; a weaker classification would produce a demo, not a defensible tool. `prd.md` G3, FR8. |
| R8 | New capability lives in one new top-level service, `med-reconciliation-service/` | Accepted | Monolith-first, same reasoning Phase 4 used for `epic-emulator`: component boundaries (normalizer, recon-engine, precedence-policy, gate) aren't proven yet; splitting into separate packages now would guess at a cut with no evidence. Name not load-bearing — cheap to rename before any code exists. |
| R9 | `epic-emulator`'s Outside-Record work (R5) is tracked in *this* phase's decisions/milestones, not a reopened Phase 4 milestone | Accepted | Phase 4 is closed (all milestones merged); this work is driven by Phase 7 requirements, not a Phase 4 gap. Precedent: Phase 6 M2 closed a Phase 2 gap (R15) while being tracked as Phase 6's own work. Phase 4's own docs are left untouched by this decision. |
| R10 | Precedence-policy schema is keyed by **question type** (what was prescribed / what the patient is actually taking / whether the drug was ever obtained), not by individual field | Accepted | Matches the brainstorm doc's own framing exactly (discharge orders win on "prescribed," outpatient list may win on "actually taking," fill data wins on "obtained"). A per-field schema would be harder to write reasons for and harder for a reviewer to audit. `design.md` §4. |
| R11 | RxNorm term-type detection walks RxNav's TTY (term-type) attribute and ingredient/clinical-drug/branded relationships, rather than string-matching alone | Accepted, unvalidated | Sketch only — real API behavior needs to be confirmed live during M5, not assumed correct from documentation. `design.md` §3. |
| R12 | A real Epic/Athena sandbox is not used as a build dependency, and no milestone is allocated for it this phase | Accepted | Matches Phase 4's own access-assumption stance: public documentation/emulator is sufficient to build against; a live cross-check is a nice-to-have for a later phase, not this one. |
| R13 | The demo/consumer surface is a CLI script producing a terminal three-panel view, not a new HTTP API or UI | Accepted | Matches this repo's existing acceptance-test-as-demo convention (e.g. `e2e/test_epic_emulator_acceptance.py`); the demo's payoff (the mid-demo source-kill degrading to `INCOMPLETE_SOURCES`) doesn't need a UI to land. `milestone-plan.md` M8. |
| R14 | Whether a third connected source is added this phase stays explicitly open | Deferred, not resolved | Recorded as a deliberate non-decision, not an oversight — see `prd.md` §10. Revisit after M1–M8 ship with two sources. |

## Supersession notes

None yet — this is the first decisions pass. Future entries that revise one of the above will
say so explicitly here, same convention as Phase 4 (`decisions.md` E-series) and Phase 6
(`decisions.md` H-series).
