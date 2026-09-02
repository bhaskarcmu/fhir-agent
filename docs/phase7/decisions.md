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

## Second pass — agentic clinical experience, overrides, audit, and formal records

Added after working through, in conversation with the repo owner, whether and where an agentic
interface belongs in this phase. Landed on a layered answer rather than all-or-nothing: yes for
intake and explanation, yes-with-an-audit-trail for overrides, and explicitly no for the
fail-closed gate — with a formal-record mechanism built specifically to replace what a chat-based
override would otherwise be asked to do.

| ID | Decision | Status | Rationale / where it lives |
|---|---|---|---|
| R15 | A new agent, `med-reconciliation-agent`, handles conversational Trigger-B intake | Accepted | Mirrors `mcp-agent`'s existing tool-use shape: extracts demographics, calls the deterministic resolver's tools, relays explicit human confirmation. Never resolves ambiguity itself. `prd.md` G11, FR18. |
| R16 | The same agent narrates the reconciled view in plain language, grounded only in the deterministic data it's given | Accepted | Same non-authoritative explanation pattern `claims-agent` already uses for adjudication decisions; same grounding discipline as Phase 6 M6's knowledge-base citations (retrieval/narration only ever follows a decision that already exists). `prd.md` G12, FR19. |
| R17 | A human can submit an explicit, attributed override of a computed RxNorm classification or discrepancy type through the agent | Accepted | Real clinicians catch things automation gets wrong; the override is captured, not silently applied — append-only via the audit ledger (R21). `prd.md` G13, FR20. |
| R18 | The fail-closed gate (`RECONCILED`/`DISCREPANCIES_FOUND`/`INCOMPLETE_SOURCES`) has **no** corresponding agent tool, in any form | Accepted, load-bearing | A chatbot is exactly the interface that makes waving away an incomplete result feel low-stakes — the repo owner explicitly ruled this out. Enforced by the *absence* of a tool (`design.md` §3), not a runtime permission check that could be misconfigured or bypassed. `prd.md` G14, FR21. |
| R19 | Every run generates a formal, persisted FHIR `Composition` ("Medication Reconciliation Record"), any outcome, not only incomplete ones | Accepted | The concrete alternative to R18: a queryable fact, not a conversation, is what satisfies the Joint Commission's "good faith effort... documented" language. `prd.md` G15, FR22, `design.md` §4. |
| R20 | The record's per-source attempt-log narrative is built from a fixed template + real telemetry, never LLM-generated free text | Accepted | A document whose purpose is proving an effort was made cannot itself contain an unverified (hallucination-risked) claim. A cosmetic polish layer is a plausible later addition, explicitly not built now (`prd.md` §8). `prd.md` G16, FR23. |
| R21 | A human's manual-verification follow-up is captured as a new, appended `Provenance` entry — never a mutation of the original Composition or gate value | Accepted | Preserves both facts permanently and separately: the system's computed state at run time, and the human's later out-of-band confirmation. Storage-layer guarantee (`audit.py`, `design.md` §5), not a display convention. `prd.md` G17, FR24, FR25. |
| R22 | `med-reconciliation-agent` is a new top-level package, not folded into `med-reconciliation-service` | Accepted | Matches existing repo convention — every other "explains and orchestrates" agent (`mcp-agent`, `claims-agent`, `provider-search-agent`, `provider-curation-agent`) is its own package, never merged into the deterministic service it calls. |
| R23 | `med-reconciliation-agent` is built directly on `agent-platform` (Phase 6) — session/memory, observability, multi-provider seam, and the output-gate *pattern* | Accepted | Phase 6 built this infrastructure specifically so later agents wouldn't reinvent it. The agent's own turn-safety enum (`turn_gate.py`) is a **new**, agent-scoped gate with zero access to the clinical `ReconciliationOutcome` gate (R18) — two different gates guarding two different questions, deliberately kept structurally separate. `prd.md` G18. |

## Supersession notes

None yet. Future entries that revise one of the above will say so explicitly here, same
convention as Phase 4 (`decisions.md` E-series) and Phase 6 (`decisions.md` H-series).
