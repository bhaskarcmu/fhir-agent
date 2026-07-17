# Phase 3 — Provider Search & Referral

> ## Canonical status
>
> **M1–M6 done, M7 not started.** `provider-registry-service` (M2) is built and tested
> against a real local Postgres. Ingestion (M3) loaded real NPPES/NUCC/Census data for the
> pilot state; `provider-curation-agent` (M4) wraps it with an AI run-summary and expanded
> ingestion to the full curated set (NC, CA, MT). `provider-mcp-server` (M5) is a real,
> hand-built MCP server. `provider-search-agent` (M6) is a real MCP client/host — the
> protocol boundary is complete end to end, and a real groundedness eval (genuine Claude
> API calls) verifies every provider it states is real, not fabricated — see `design.md`
> §13 for exact counts, not restated here (they'd drift). Nothing deployed to any cloud
> (Phase 3b, not started; see `design.md` §13's cloud-delivery-gap callout before assuming
> a stub means deploy-ready).
>
> *This is the one canonical status statement. Other documents link here rather than restate it.
> Milestone-by-milestone verified test results live in `design.md` §13, updated per PR — check
> there for current counts.*
>
> - [`prd.md`](./prd.md) — problem, goals/non-goals, requirements, success metrics.
> - [`design.md`](./design.md) — architecture, the two agents' tool contracts, the hand-built
>   MCP server, data model, **milestone plan with verified test results** (§13).
> - [`decisions.md`](./decisions.md) — ADR-style index of every architectural decision, with
>   status tracking (Accepted / Partially delivered / Superseded), same convention as Phase 2's.
>
> **What's next:** M7 (`docker-compose` demo profile bundling all four new components;
> end-to-end local verification — the last milestone before Phase 3b's cloud deployment).

## What Phase 3 is

A first-party Provider Search capability: given a patient's location and a clinical need,
return a ranked, explained list of real, traceable providers sourced from authoritative
public data (NPPES) — not a paid third-party directory API. It's also this platform's first
genuine Model Context Protocol integration: a hand-built MCP server and a real MCP
client/host, wired through the actual protocol handshake.

## Terminology

Internal work is tracked as **milestones** (M1, M2, ...) inside `design.md` §13 — never as
"Phase 3.x". "Phase" is reserved for top-level platform phases: Phase 1, Phase 2, Phase 3
(this one), and **Phase 3b** — the future GCP cloud-deployment phase that mirrors Phase 2b.
Every Phase 3 milestone produces a cloud-readiness stub (Dockerfile + per-service Terraform
sketch, not applied) — but Phase 2's own docs record that per-service stubs turned out **not**
to add up to "Phase 2b is just a deploy": no root Terraform module, deploy script, or executed
cloud smoke test ever shipped. `design.md` §13 names those three as their own explicit
milestone deliverables (landing in M7) rather than repeating that gap silently — see the
"do not read this as X" callout there before assuming Phase 3b is one command.

## Relationship to Phase 1 and Phase 2

Additive only — Phase 1 (refill-triage) and Phase 2 (claims adjudication) are unmodified.
Provider Search introduces four new standalone packages
(`provider-registry-service`, `provider-mcp-server`, `provider-search-agent`,
`provider-curation-agent`) rather than extending `mcp-agent`, following the same
"separate package, not an extension" precedent Phase 2 set with `claims-agent`.
