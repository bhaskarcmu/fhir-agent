# Phase 2 — Claims Adjudication Modernisation Slice

> ## Canonical status
>
> **BUILT and running locally (M0–M7 complete).** A claim can be submitted, adjudicated,
> persisted as FHIR artefacts, and explained — end to end, on a laptop.
>
> **Not deployed to cloud (M8 / Phase 2b not started).** Deliberately deferred to avoid GCP
> spend until the platform was proven locally. Note that the cloud path is **less complete than
> the milestone table implies**: per-service Cloud Run stubs exist for the two Java services,
> but there is no root Terraform module and nothing has been applied — see the
> [cloud-delivery gap](./plan.md#6-workstreams--milestones). Phase 2b is real authoring work,
> not one command.
>
> **Observability (R15) — was found undelivered post-hoc (2026-08), now closed.** M3/M4's
> touchpoints said "OTel tracing wired" / "Managed-Prometheus metric names" before any such
> instrumentation actually existed; a later platform-wide observability effort has since built
> it for real — see [C5](./decisions.md). Same caveat as the cloud-delivery gap above: it runs
> locally, not yet cloud-deployed (M8/Phase 2b's job either way).
>
> *This is the one canonical status statement. Other documents link here rather than restate it.*
> Next steps: [`plan.md` §16](./plan.md#16-future-work).
>
> To run it: [`../demo-guide.md`](../demo-guide.md). To work on it:
> [`../developer-guide.md`](../developer-guide.md).
>
> These documents capture the requirements and implementation plan **we actually
> agreed to build**, which deviate in places from the source PRD (*Prescription Claim
> Adjudication Modernization Platform — Phase 2 Scope*, DRAFT). Deviations are listed
> explicitly in [`requirements.md`](./requirements.md#deviations-from-the-prd).

## What Phase 2 is

Extend the existing Phase 1 platform (prescription **refill risk triage**) into a
**prescription claim adjudication** slice: submit a claim → adjudicate it against
a simulated legacy core + deterministic benefit/prior-auth rules + reused clinical
safety checks → emit auditable FHIR decision artefacts → explain the outcome in
plain language via a dedicated agent.

Full descriptive name (from the PRD): *"Prescription Claim Adjudication
Modernisation Slice: API façade + rules service + audit trail + MCP explanation
layer."*

## The four framing decisions (locked)

| Decision | Choice |
|---|---|
| Rules stack | **Hybrid** — Java/Spring Boot façade + legacy emulator + anti-corruption layer; **reuse** the existing Python triage service for clinical safety (drug-allergy / duplicate-therapy) |
| Deliverable | **Fully runnable end-to-end demo** (like the Phase 1 refill demo) |
| Legacy emulator realism | **Convincing legacy shape** (DDS-style records, DB2/SQL400 table naming, RPG/CL-flavoured adjudication function) |
| FHIR ambition | **Da Vinci-aware but generic** R4 resources (not full PAS conformance) |

## Cloud, security & scalability decisions (designed + stubbed + tested throughout; live deploy = Phase 2b)

| # | Area | Choice |
|---|---|---|
| C1 | Compute | **Hybrid: GKE for Phase 1 (untouched) + Cloud Run for new Phase 2 services**; HAPI always-on. No Phase 1 rework. |
| C2 | Gateway | **DB-less Kong** as the canonical Phase 2 gateway (one declarative dialect — committed as `kong.tmpl.yml`, rendered to `kong.yml` at startup — for local + cloud); Phase 1 KIC Kong untouched, unified later via a **gateway-strangler** ([runbook](../gateway-runbook.md), plan §3). |
| C3 | Rules data | **Postgres behind a repository interface** now; Bigtable/Firestore is the documented scale swap. |
| C4 | Audit | **FHIR `Provenance`** now (with R18 invariants); BigQuery analytics plane deferred to Phase 2b. |
| C5 | Observability | **OpenTelemetry tracing + Micrometer/Prometheus metrics** (R15) — designed, and now built (was found undelivered post-hoc 2026-08, closed by a later platform-wide effort). See [`decisions.md` C5](./decisions.md). |

**Cloud is a first-class concern from every milestone** (design + stub + test); only the
live/paid GCP deploy is late (**Phase 2b**). Normative sections: **Decision Contract
(R17)**, **audit invariants + idempotency (R18)**, **test matrix (R19)**, plus security
(R14), observability (R15), deployability (R16), a **stakeholder × milestone** matrix
(plan §13), the **modernization/strangler snapshot** and **reliability patterns** (plan §5),
**engineering standards** (plan §14), and the **delivery/PR strategy** (plan §15).

**Payer grounding — Medicare *and* commercial.** Coverage is grounded in **real public
disclosure data** for both: CMS Part D (Medicare) and ACA-mandated disclosures — EHB
benchmark plans + QHP machine-readable formularies (tier/PA/step-therapy/quantity-limit) —
for representative commercial plans (requirements R13.1). The rules engine is
payer-agnostic; plan type is configuration. The data-engineering source catalog, synthesis
tooling, curated fixtures, and verified URLs live under `data/reference/`.

## Non-negotiable constraint

**Phase 1 must remain independently runnable, testable, and cloud-deployable.**
All Phase 2 work is *additive*. A known-good snapshot is tagged `phase1-v1`
(commit `d4cd4be`). See [`requirements.md` §R9](./requirements.md#r9--phase-1-independence-hard-constraint).

## Documents

- **[`requirements.md`](./requirements.md)** — the agreed requirements, scope,
  out-of-scope, and deviations from the PRD. **Normative** — what must be true.
- **[`plan.md`](./plan.md)** — architecture, service topology, gateway/parity
  design, workstreams, sequencing, open questions, and **[§16 future work](./plan.md#16-future-work)**.
- **[`decisions.md`](./decisions.md)** — ADR-style index of every decision (D1–D8, C1–C5, and
  later ones) with status and supersession markers.
- **[`source-prd.md`](./source-prd.md)** — the archived source DRAFT PRD that
  seeded this work (the **input**, not the contract; deviations captured in
  `requirements.md`).

Practical guides live one level up and cover both phases:
**[demo](../demo-guide.md)** · **[developer](../developer-guide.md)** ·
**[testing](../testing-guide.md)** · **[docs index](../README.md)**.

## Provenance

Derived from the DRAFT PRD plus a design conversation that adapted it to this
repo's actual state (stock HAPI FHIR server, Python triage rule engine, cloud-only
Kong fronting FHIR). Where the PRD and this repo disagreed, this repo won.
