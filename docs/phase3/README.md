# Phase 3 — Provider Search & Referral

> ## Canonical status
>
> **M1–M7 done — Phase 3 complete. Phase 3b (live GCP deployment) not started.**
> `provider-registry-service` (M2) is built and tested against a real local Postgres.
> Ingestion (M3) loaded real NPPES/NUCC/Census data for the pilot state;
> `provider-curation-agent` (M4) wraps it with an AI run-summary and expanded ingestion to
> the full curated set (NC, CA, MT). `provider-mcp-server` (M5) is a real, hand-built MCP
> server; `provider-search-agent` (M6) is a real MCP client/host — the protocol boundary is
> complete end to end, verified by a real groundedness eval (genuine Claude API calls). M7
> composed a real root Terraform module, a real (unexecuted) deploy script, and wired an
> executed `terraform validate` + full-suite CI job — and, for the first time, built and ran
> all four Phase 3 Docker images together end-to-end, not just their Python code directly.
> See `design.md` §13 for exact counts, not restated here (they'd drift).
>
> **Nothing is deployed to any live cloud.** `terraform validate` passes; `terraform plan`
> and `apply` have never been run against a real GCP project — see `design.md` §13's
> cloud-delivery-gap callout before assuming a validated stub means deploy-ready.
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
> **What's next:** Phase 3b — live GCP deployment (`terraform apply` + `deploy-phase3.sh`
> against a real project). Not started; no timeline set.

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
cloud smoke test ever shipped. M7 built all three of those (root module, `deploy-phase3.sh`,
an executed `terraform validate` CI job) rather than repeating that gap — see `design.md`
§13's "do not read this as X" callout before assuming Phase 3b is one command regardless.

## Relationship to Phase 1 and Phase 2

Additive only — Phase 1 (refill-triage) and Phase 2 (claims adjudication) are unmodified.
Provider Search introduces four new standalone packages
(`provider-registry-service`, `provider-mcp-server`, `provider-search-agent`,
`provider-curation-agent`) rather than extending `mcp-agent`, following the same
"separate package, not an extension" precedent Phase 2 set with `claims-agent`.
