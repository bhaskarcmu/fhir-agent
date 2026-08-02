# Phase 5 — Epic Emulator Decomposition (reserved)

> ## Canonical status
>
> **🔒 Reserved, not started. No code, no milestone plan, no timeline.**
>
> Phase 5 is reserved for decomposing `epic-emulator` (built in Phase 4) along whatever its
> actual internal coupling turns out to require — evidence for that decomposition is
> [`phase4/coupling-note.md`](../phase4/coupling-note.md) (PRD G6), not a guess made in advance.
> The reservation was set by Phase 4 itself: `epic-emulator` was deliberately built as **one
> monolith** because its three capability areas' internal boundaries weren't known yet
> ([`phase4/decisions.md` E1](../phase4/decisions.md)).
>
> **Before any Phase 5 work starts:** [`phase4-testing-and-analysis.md`](./phase4-testing-and-analysis.md)
> §0/§4.0 documents a live, unresolved clinical-safety bug in already-merged Phase 4 code —
> `epic-emulator`'s pagination cap can silently drop allergy records, flipping a HIGH-risk
> drug-conflict result into a false-negative LOW. The durable record of this bug is
> [`phase4/decisions.md` E16](../phase4/decisions.md). **Fixing or deliberately mitigating it is
> a precondition for treating Phase 4 as demo-ready — it is not itself Phase 5 scope**, but
> Phase 5 should not start without an explicit decision on it (§4.0 lays out two non-mutually-
> exclusive fix options).
>
> **What Phase 5 is not:** it is not "Agent Platform Hardening." That work — hardening the
> LLM-agent tier (`mcp-agent`, later `claims-agent`): memory/session management, distributed
> tracing & metrics, multi-provider LLM support, fail-closed output-safety — is a separate,
> later effort, reserved as **Phase 6** ("Agent Platform Hardening + Overall Observability"),
> now with its own canonical status doc: [`../phase6/README.md`](../phase6/README.md). The two
> were briefly conflated during brainstorming before either document existed; this page is the
> correction.
>
> *This is the one canonical status statement for Phase 5. Other documents link here rather than
> restate it.*

## What's reserved here, and why

`epic-emulator` (Phase 4) was deliberately built as one Spring Boot monolith — auth emulation,
custom-extension backfill, and the three named quirks all in one process — because splitting it
prematurely would have meant guessing at boundaries with no evidence behind them.
[`phase4/coupling-note.md`](../phase4/coupling-note.md) (PRD G6) is the evidence-gathering
exercise a real Phase 5 decomposition would use, and
[`phase4/decisions.md` E1](../phase4/decisions.md) records that decision.

[`phase4-testing-and-analysis.md`](./phase4-testing-and-analysis.md) — the document that occupied
this folder before this README existed — is a post-merge clinician/business/architect testing
pass over completed Phase 4, run against real running services. It is Phase 5's primary input,
**not a Phase 5 PRD**: it leads with the open safety bug (§0), then gives decomposition-relevant
findings (§3.3/§3.4) and recommendations (§4), including "fix or mitigate the pagination bug
before Phase 5 starts" (§4.0).

## What has and hasn't happened

- ✅ The analysis pass that will inform Phase 5's scope — [`phase4-testing-and-analysis.md`](./phase4-testing-and-analysis.md).
- ✅ The coupling-note evidence Phase 4 itself produced — [`phase4/coupling-note.md`](../phase4/coupling-note.md).
- ❌ No Phase 5 PRD, design doc, or milestone plan exists.
- ❌ No decision on §4.0's fix-or-mitigate question for the pagination bug.
- ❌ No code, no branch, no timeline.

## Relationship to Phase 6

Phase 6 ("Agent Platform Hardening + Overall Observability", planning complete as of 2026-08-02
— see [`../phase6/README.md`](../phase6/README.md)) is unrelated in subject matter — it hardens
the conversational LLM-agent tier, not `epic-emulator` — and does not depend on Phase 5
completing first. The two are sequential in number only because Phase 5's reservation predates
Phase 6 being scoped; nothing prevents either from starting independently once each has an owner
and a decision to begin. Phase 6 is now ahead of Phase 5 in actual planning progress — worth
noting so the number ordering isn't mistaken for priority ordering.
