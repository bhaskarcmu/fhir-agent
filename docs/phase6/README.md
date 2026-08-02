# Phase 6 — Agent Platform Hardening + Overall Observability

> ## Canonical status
>
> **🚧 M1-M5 implemented (M5 PR open, unmerged as of this note). M6 not started. M7 planned,
> not started.**
>
> M1 (Output Contract & Fail-Closed Enforcement), M2 (Observability, Platform-Wide), M3 (Context,
> Memory & Session Transport), M4 (Deploy Resilience & Cost Control), and M5 (Provider
> Abstraction & Cross-Model Follow-ups) are all built, tested, and live-validated — see
> [`milestone-plan.md`](./milestone-plan.md) for each milestone's real implementation detail. M5
> was substantially reworked after a design-review pass (the default provider flipped from
> Anthropic to self-hosted Ollama, among other changes — see
> [`decisions.md` H45-H51](./decisions.md)). **M7 ("Strong Model in Production") was added to the
> build order after M5** to carry the fuller production-safety design M5's minimal
> `DEPLOYMENT_ENV=production` guardrail was deliberately left as a stopgap for — see
> [`milestone-plan.md` M7](./milestone-plan.md#m7--strong-model-in-production-planned-not-yet-implemented).
> **M6 (Policy, Knowledge & Judge) starts next**, once M5 merges.
>
> *This is the one canonical status statement. Other documents link here rather than restate it.*
>
> - [`prd.md`](./prd.md) — problem statement, goals/non-goals, functional requirements (R1–R19),
>   success metrics.
> - [`design.md`](./design.md) — target architecture (`agent-platform/`), the five topics,
>   cross-cutting principles, per-topic deep dives, testing strategy.
> - [`milestone-plan.md`](./milestone-plan.md) — M1–M7, short and long story for each, dependency
>   order, status table. **Kept as its own document, not folded into `design.md`** — see
>   [`decisions.md` H23](./decisions.md).
> - [`decisions.md`](./decisions.md) — ADR-style index of every decision (H1–H51 as of this note),
>   same status-and-supersession convention as Phase 2/3/4.
> - [`telemetry-schema.md`](./telemetry-schema.md) — the custom span-attribute dictionary:
>   `fhir_agent.layer`/`.component` grounded in each service's real package structure, the
>   `TELEMETRY_VERBOSITY` depth model, and request-ID surfacing.

## What Phase 6 is

Hardens the LLM-agent tier — `mcp-agent` (Phase 1's refill-risk-triage CLI, the **pilot
target**) and later `claims-agent` (Phase 2's claims-explanation agent, the **carry-over
target**) — to the same rigor the deterministic tiers already have: fail-closed output, real
observability, session/memory management, deployment resilience, and a genuine (if
not-yet-activated) multi-provider seam. Built once as a shared platform layer
(`agent-platform/`), not duplicated per agent.

The **"+ Overall Observability"** half of the title is deliberate, not incidental: Phase 6's
observability milestone (M2) is scoped platform-wide, not agent-tier-only, and closes Phase 2's
long-open **R15** requirement in the same pass — see [`decisions.md` H16](./decisions.md).

## Relationship to Phase 1, 2, and 5

- **Phase 1 (`mcp-agent`)** — the pilot. Already has the conversational shape (a working
  Anthropic tool-use loop); Phase 6 hardens it without changing its clinical behavior.
- **Phase 2 (`claims-agent`, `claims-service`, `rxclaim-emulator`)** — the carry-over target for
  the shared platform layer, and the owner of the R15 requirement M2 closes. Phase 6 is
  deliberately **not** a Phase 2 extension — see [`decisions.md` H1](./decisions.md) for why
  reopening a completed, previously status-corrected phase was rejected in favor of a phase of
  its own.
- **Phase 5 (`epic-emulator` decomposition)** — unrelated in subject matter, sequential in
  number only. See [`../phase5/README.md`](../phase5/README.md), which documents this exact
  distinction (the two were briefly conflated during early brainstorming before either phase had
  its own canonical doc).
- **Phase 3 and Phase 4 agents** — explicitly out of scope; see [`prd.md` §3](./prd.md#3-non-goals).

## Terminology

Internal work is tracked as **milestones** (M1–M7, in [`milestone-plan.md`](./milestone-plan.md))
— never "Phase 6.x". "Phase" is reserved for top-level phases. No sub-phase (e.g. a "Phase 6b")
is anticipated — this phase is cloud-agnostic and local-first throughout, so it doesn't have the
live-deploy-deferred shape Phase 2b/3b/4b address for their phases. M7 was added mid-build (after
M5's design-review rework) as a genuinely new milestone in the same sequence, not a sub-phase —
see [`decisions.md` H47](./decisions.md).

## Provenance

Scoped through a structured, multi-round conversational process: an initial brainstorm proposing
the five topics and a draft milestone order, a full codebase audit that verified or corrected
every load-bearing claim in it, and a decision pass resolving every question the audit and
brainstorm surfaced — including catching and fixing a genuine naming collision with
already-reserved Phase 5 content along the way. Full trail: [`decisions.md`](./decisions.md).
