# Phase 7 — Medication Reconciliation

> ## Canonical status
>
> **📝 Planning complete, scope expanded twice. No code written yet.** First pass scoped a
> deterministic reconciliation core; a second pass added a conversational agent layer, an
> audited human-override capability, and a formal immutable record-keeping mechanism — after
> explicitly deciding the fail-closed gate itself must **never** be reachable from a chatbot.
> `prd.md`, `design.md`, `decisions.md` (`R1`–`R23`), and `milestone-plan.md` (M1–M12) all reflect
> both passes. M1 (`athena-emulator`: proxy, auth, quirks) is next, not started.
>
> *This is the one canonical status statement. Other documents link here rather than restate it.*
>
> - [`prd.md`](./prd.md) — problem statement, goals/non-goals, triggers, functional requirements,
>   acceptance criteria.
> - [`design.md`](./design.md) — architecture, component breakdown, the agent's tool contract
>   (and what's deliberately excluded from it), the Medication Reconciliation Record and audit
>   ledger, the precedence-policy and RxNorm term-type-matching sketches, the reconciled-line data
>   model.
> - [`decisions.md`](./decisions.md) — the ADR-style index (`R1`–`R23`), same convention as
>   Phase 2/3/4/6.
> - [`milestone-plan.md`](./milestone-plan.md) — M1–M12, short and long story for each, none
>   started.

## What Phase 7 is

Given a confirmed patient identity and a discharge encounter, retrieve the medication list from
each connected source (`epic-emulator`, and `athena-emulator` — built out for real this phase)
independently, normalize each entry to a standard drug concept, and return a reconciled view that
preserves every source's contribution, labels each line by discrepancy type (using the Joint
Commission's own vocabulary: omission, addition/duplication, change, unclear), and attaches the
source and timestamp to every field.

It deliberately does **not** produce a single merged medication list, does not auto-resolve
ambiguous patient identity, and does not assess drug interactions — see `prd.md` §4 for the full
non-goals and the reasoning behind each.

## The agentic layer, and the one thing it explicitly cannot do

A new agent, `med-reconciliation-agent`, handles conversational patient/encounter lookup and
plain-language explanation of results — the same "orchestrates, never decides" shape `mcp-agent`
and `claims-agent` already use. A clinician can also submit an explicit, attributed override of a
computed drug-match classification or discrepancy type through it.

**The fail-closed gate — `RECONCILED` / `DISCREPANCIES_FOUND` / `INCOMPLETE_SOURCES` — has no
agent tool at all.** Not restricted: absent. The alternative to a chat-based override is a formal,
immutable FHIR `Composition` ("Medication Reconciliation Record"), generated for every run
regardless of outcome, containing a templated (never LLM-generated) per-source attempt log — the
artifact that satisfies the Joint Commission's "good faith effort... documented" standard. A
human's later manual verification is appended to that record as a new `Provenance` entry; it never
edits or replaces what the system originally computed.

## Relationship to Phase 1, 2, 4, and 6

Additive. `fhir-service`, `triage-service`, and `mcp-agent` are unmodified. `client/clinical` is
extended in a backward-compatible way only (Phase 7 M3) — existing `triage-service` call sites'
behavior is unchanged. `epic-emulator` (Phase 4) is extended with Outside-Record endpoint
variants (Phase 7 M2); this work is tracked in Phase 7's own `decisions.md` (R9), not a reopened
Phase 4 milestone. `athena-emulator` — reserved as an empty placeholder since Phase 2, untouched
through Phase 4 — is built out for the first time in this phase (R2). `med-reconciliation-agent`
is built directly on `agent-platform` (Phase 6) — its session/memory, observability, and
multi-provider seam are reused, not reinvented (R23).

## Terminology

Internal work is tracked as **milestones** (M1–M12, in `milestone-plan.md`) — never "Phase 7.x",
same convention as every prior phase.
