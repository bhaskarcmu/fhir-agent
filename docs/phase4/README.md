# Phase 4 — Epic Emulator

> ## Canonical status
>
> **M1 + M2 + M3 + M4 built.** `epic-emulator/` is a real Spring Boot module: a pass-through proxy
> (forwards every request to `fhir-service` unchanged, verified by 3 tests), gated behind a
> simulated SMART Backend Services JWT client-assertion auth flow (verified by 6 more tests — the
> full flow, plus rejection of no-header/garbage-token/expired-assertion/wrong-key/unknown-client
> requests), backfilling a placeholder Epic-style extension on `MedicationRequest`/
> `AllergyIntolerance` reads that don't already have one (verified by 6 more tests — bare resource,
> Bundle search results, idempotency, out-of-scope resource types, and write round-tripping), and
> now exhibiting all three named quirks — pagination cap + opaque continuation, the required-
> search-parameter rejection, and Epic-shaped `OperationOutcome` errors, the last of which was also
> retrofitted onto M2's auth-gate rejection (verified by 8 more tests). 23 tests total across the
> module. `decisions.md` indexes 14 decisions (`E1`–`E14`).
>
> M2's other stated task — pinning a specific Epic documentation version — is **only partially
> done**: one real check confirmed Epic's docs site is genuinely public at a shell level (dated
> October 31, 2025) but the specific backend-OAuth2 technical parameters weren't retrievable by a
> plain fetch, and no account registration was attempted (an inherently human step this build
> can't perform). The auth flow was built against the public base SMART Backend Services spec
> instead — see `design.md` §7 and decision E10 for the honest, non-fabricated version of what was
> and wasn't verified.
>
> *This is the one canonical status statement. Other documents link here rather than restate it.*
>
> - [`prd.md`](./prd.md) — problem statement, goals/non-goals, functional requirements, success
>   metrics.
> - [`design.md`](./design.md) — architecture, per-capability-area deep dives, the three quirks'
>   concrete (unverified, flagged-pending-validation) choices, and the milestone plan (§12).
> - [`decisions.md`](./decisions.md) — ADR-style index of every decision, same convention as
>   Phase 2/Phase 3.
> - [`../../epic-emulator/README.md`](../../epic-emulator/README.md) — the module's own README:
>   how the proxy and auth flow work, build/test/run instructions.
>
> **What's next:** M5 — the acceptance case (re-point the existing prescription-refill-risk-triage
> scenario at `epic-emulator`) and the coupling note for Phase 5. Not started; no timeline set.

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
