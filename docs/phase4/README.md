# Phase 4 — Epic Emulator

> ## Canonical status
>
> **⚠️ All 5 milestones are built and merged, but a post-merge safety finding is still open — see
> [`docs/phase5/phase4-testing-and-analysis.md`](../phase5/phase4-testing-and-analysis.md) §0
> before treating this as demo-ready.** Summary: a realistic multi-allergy patient can get a
> silent false-negative ("safe to dispense") result through `epic-emulator` due to the pagination
> quirk (M4) combined with a pre-existing gap in `client/clinical`'s FHIR client. Not yet fixed.
>
> **Phase 4 milestones: complete — M1 through M5 all built.** `epic-emulator/` is a real Spring
> Boot module: a
> pass-through proxy (verified by 3 tests), gated behind a simulated SMART Backend Services JWT
> client-assertion auth flow (6 more tests), backfilling a placeholder Epic-style extension on
> `MedicationRequest`/`AllergyIntolerance` reads (6 more tests), and exhibiting all three named
> quirks — pagination cap + opaque continuation, the required-search-parameter rejection, and
> Epic-shaped `OperationOutcome` errors, also retrofitted onto the auth gate (8 more tests). 24
> unit/integration tests total. **M5's acceptance case is verified live**, not just in unit tests:
> [`e2e/test_epic_emulator_acceptance.py`](../../e2e/test_epic_emulator_acceptance.py) ran the
> actual prescription-refill-risk-triage scenario against a real running `fhir-service` and
> `epic-emulator`, twice (HIGH-risk drug-allergy-conflict and LOW-risk control), and got identical
> `RiskAssessment` outcomes direct vs. via the emulator both times. The coupling note (PRD G6) is
> [`coupling-note.md`](./coupling-note.md). `decisions.md` indexes 15 decisions (`E1`–`E15`).
>
> M2's other stated task — pinning a specific Epic documentation version — is **still only
> partially done**: one real check confirmed Epic's docs site is genuinely public at a shell level
> (dated October 31, 2025) but the specific backend-OAuth2 technical parameters weren't retrievable
> by a plain fetch, and no account registration was attempted (an inherently human step this build
> can't perform). The auth flow, and every quirk/extension value, were built against the public
> base SMART Backend Services spec and structurally-representative placeholders instead — see
> `design.md` §7 and decision E10 for the honest, non-fabricated version of what was and wasn't
> verified. **This is the one open item a follow-on effort with real Epic sandbox access should
> resolve first** — everything else in Phase 4 is built, tested, and (for M5) verified live.
>
> *This is the one canonical status statement. Other documents link here rather than restate it.*
>
> - [`prd.md`](./prd.md) — problem statement, goals/non-goals, functional requirements, success
>   metrics.
> - [`design.md`](./design.md) — architecture, per-capability-area deep dives, the three quirks'
>   concrete (unverified, flagged-pending-validation) choices, and the milestone plan (§12).
> - [`decisions.md`](./decisions.md) — ADR-style index of every decision, same convention as
>   Phase 2/Phase 3.
> - [`coupling-note.md`](./coupling-note.md) — PRD G6: which capability areas shared state/logic in
>   practice, evidence for Phase 5's decomposition.
> - [`../../epic-emulator/README.md`](../../epic-emulator/README.md) — the module's own README:
>   how the proxy, auth flow, extensions, and quirks work, build/test/run instructions.
> - [`../../e2e/test_epic_emulator_acceptance.py`](../../e2e/test_epic_emulator_acceptance.py) —
>   the live acceptance test.
>
> **What's next:** Phase 4 is built and merged, but **not fully closed** — a post-merge
> clinician/business/architect testing pass found a live, unresolved safety bug (pagination can
> silently drop clinical data — see
> [`docs/phase5/phase4-testing-and-analysis.md`](../phase5/phase4-testing-and-analysis.md) §0/§4.0)
> that should be decided on before treating this module as demo-ready. A future Phase 5 would
> decompose along whatever the coupling note actually shows, not the original three-area guess —
> see the coupling note and the PRD's forward note (§10). No Phase 5 work has started; no timeline
> set.

## What Phase 4 is

`fhir-service` is intentionally EHR-agnostic — plain FHIR R4, nothing vendor-specific. Nothing in
the platform today exercises what a real integration with **Epic** actually looks like: Epic's
own login flow, Epic's custom data extensions, or Epic's well-documented quirky API behavior.

Phase 4 builds **`epic-emulator`**: one new service that sits in front of `fhir-service` and
reproduces enough of Epic's real, *publicly documented* behavior — three specific things, chosen
deliberately narrow — so the rest of the platform can be developed and tested against
Epic-like behavior without a live Epic connection:

1. **Auth emulation** — Epic's SMART Backend Services login handshake (JWT-based, not a
   password).
2. **Custom extensions** — Epic's extra fields on top of standard Medication and
   AllergyIntolerance records, scoped to the data the platform's existing drug-allergy check
   already reads.
3. **Three named quirks** — pagination behavior, a required search-parameter combination, and
   error-message shape, chosen to sample three different layers of "talking to the API"
   rather than three variations on one theme.

It is built as **one monolith on purpose**: these three areas' internal boundaries aren't known
yet, and a real split — if one turns out to be needed — belongs in a future Phase 5, informed by
what building them together actually reveals about how coupled they are.

## Terminology

Internal work is tracked as **milestones** (M1–M5, in `design.md` §12) — never "Phase 4.x".
"Phase" is reserved for top-level phases: Phase 1, Phase 2, Phase 3, Phase 4 (this one), and a
possible future **Phase 4b** (live cloud deployment) if one is ever needed — nothing in Phase 4's
scope requires it (see `design.md` §11).

## Relationship to Phase 1, 2, and 3

Additive only. `fhir-service`, `triage-service`, `claims-service`, `mcp-agent`, and every Phase 3
provider-search package are unmodified. `epic-emulator` follows the same "standalone package, not
an extension of something existing" precedent Phase 2 set with `claims-agent` and Phase 3 repeated
with its four new packages.

**Correction to earlier framing:** `epic-emulator/` is not actually a new directory — it already
existed as an **empty placeholder**, reserved back in Phase 2
([`docs/phase2/plan.md` §16](../phase2/plan.md#16-future-work), deviation D2 in
[`docs/phase2/requirements.md`](../phase2/requirements.md#deviations-from-the-prd)), alongside a
sibling `athena-emulator/` placeholder. That original framing describes *two* EHR-specific edges
over one generic core as the actual portability proof ("one emulator proves nothing"). Phase 4
builds out only the Epic half; `athena-emulator/` remains an untouched placeholder, so Phase 4
alone does not complete that original two-emulator claim — whether it's ever built is a separate,
later decision, not in Phase 4 or Phase 5 scope.

`triage-service` and `claims-service` are deliberately **not** folded into `epic-emulator`, even
though an earlier planning round considered it: both are already independently built and
validated, and Epic emulation is a protocol/format concern, not a clinical or claims-decision
concern. `epic-emulator`'s one acceptance test *exercises* `triage-service` through the proxy
(re-pointing its FHIR base URL); it does not duplicate `triage-service`'s rules, and it does not
touch `claims-service` at all this phase. See [`decisions.md` E6](./decisions.md).
