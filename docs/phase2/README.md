# Phase 2 — Claims Adjudication Modernisation Slice

> **Status: PLANNING — no application code yet.** These documents capture the
> requirements and implementation plan **we actually agreed to build**, which
> deviate in places from the source PRD (*Prescription Claim Adjudication
> Modernization Platform — Phase 2 Scope*, DRAFT). Deviations are listed
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

## Non-negotiable constraint

**Phase 1 must remain independently runnable, testable, and cloud-deployable.**
All Phase 2 work is *additive*. A known-good snapshot is tagged `phase1-v1`
(commit `d4cd4be`). See [`requirements.md` §R9](./requirements.md#r9--phase-1-independence-hard-constraint).

## Documents

- **[`requirements.md`](./requirements.md)** — the agreed requirements, scope,
  out-of-scope, and deviations from the PRD.
- **[`plan.md`](./plan.md)** — architecture, service topology, gateway/parity
  design, workstreams, sequencing, and open questions.
- **[`source-prd.md`](./source-prd.md)** — the archived source DRAFT PRD that
  seeded this work (the **input**, not the contract; deviations captured in
  `requirements.md`).

## Provenance

Derived from the DRAFT PRD plus a design conversation that adapted it to this
repo's actual state (stock HAPI FHIR server, Python triage rule engine, cloud-only
Kong fronting FHIR). Where the PRD and this repo disagreed, this repo won.
