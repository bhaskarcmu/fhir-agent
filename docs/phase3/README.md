# Phase 3 — Provider Search & Referral

> ## Canonical status
>
> **Draft — planning only, no implementation started.** This directory holds the PRD and
> design proposal; open questions from the first draft have been resolved (see each doc's
> decisions section) but nothing has been built yet.
>
> *This is the one canonical status statement. Other documents link here rather than restate it.*
>
> - [`prd.md`](./prd.md) — problem, goals/non-goals, requirements, success metrics.
> - [`design.md`](./design.md) — architecture, the two agents' tool contracts, the hand-built
>   MCP server, data model, milestone plan.

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
Every Phase 3 milestone produces a cloud-readiness stub (Dockerfile + Terraform sketch, not
applied) so Phase 3b is a deploy of proven config, not a redesign.

## Relationship to Phase 1 and Phase 2

Additive only — Phase 1 (refill-triage) and Phase 2 (claims adjudication) are unmodified.
Provider Search introduces four new standalone packages
(`provider-registry-service`, `provider-mcp-server`, `provider-search-agent`,
`provider-curation-agent`) rather than extending `mcp-agent`, following the same
"separate package, not an extension" precedent Phase 2 set with `claims-agent`.
