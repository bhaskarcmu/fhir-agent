# Phase 8 — Patient Outcome Prediction (12-Month Hospitalization Risk)

> ## Canonical status
>
> **📝 Planning complete (first pass). No code written yet.** A research prototype from an
> earlier session was handed over and reconciled with this repo's conventions; what it
> established is restated in `prototype-baseline.md`, and the raw hand-off documents are not
> kept in the repo (O5). `prd.md`, `design.md`, `decisions.md` (`O1`–`O27`)
> and `milestone-plan.md` (M1–M11) reflect that reconciliation. M1 (service scaffold + MEPS
> dataset reproduction) is next, not started. Cloud deployment, recalibration and monitoring
> are reserved for **Phase 8b**.
>
> *This is the one canonical status statement. Other documents link here rather than restate it.*
>
> - [`prd.md`](./prd.md) — problem statement, goals/non-goals, users and triggers, functional
>   requirements (the prototype's `FR-*` IDs kept, with status), acceptance criteria, and §11:
>   every deviation from the prototype's plan.
> - [`design.md`](./design.md) — repo layout, components, the `meps25-v1` feature contract, the
>   `RiskAssessment` shape, training vs scoring mode, the FHIR mapping sketch, model artifacts,
>   the agent's tool contract, testing, and the prototype defects found in review.
> - [`decisions.md`](./decisions.md) — the ADR-style index (`O1`–`O27`), same convention as
>   Phase 2/3/4/6/7.
> - [`milestone-plan.md`](./milestone-plan.md) — M1–M11, short and long story for each, with the
>   mapping from the prototype's planned stages.
> - [`prototype-baseline.md`](./prototype-baseline.md) — what the research prototype
>   established: data-source choices, MEPS and Synthea facts, the prototype's method, the exact
>   numbers M1–M3 must reproduce, and reference URLs.

## What Phase 8 is

The platform's first **machine-learned** clinical capability. Given an adult patient in
`fhir-service` and an as-of date, estimate the probability of at least one inpatient stay in
the next 12 months, and return it as a FHIR `RiskAssessment` — with a simple, hand-checkable
comparison score beside it, a population percentile, the top contributing features, and
references to the FHIR resources the estimate was derived from.

The model is trained only on free, open, US data — AHRQ's Medical Expenditure Panel Survey
(MEPS) longitudinal panels 21–27 — so every reported number can be reproduced from public
files. Synthea is used to test the pipeline, never to judge accuracy.

It deliberately does **not** produce qualitative risk bands, recommend treatment, read free
text, persist scores into the patient record, or deploy to the cloud this phase — see
`prd.md` §4 and §8.

## Where the model lives, and what the agent can't do

All model, feature and FHIR-mapping logic lives in one new service,
`outcome-prediction-service/` (O2). A new agent, `outcome-prediction-agent/`, built on
`agent-platform`, lets a clinician ask for a patient's risk in plain language — but its tools
can only look a patient up, fetch their `RiskAssessment`, and read the model card. **No tool
accepts feature values, thresholds or a model choice**, so the agent cannot re-score, adjust,
or band a result (`design.md` §9).

## Relationship to Phase 1, 6, and 7

Additive. `fhir-service`, `triage-service`, `mcp-agent` and the Kong gateway are unmodified;
the new service is internal-only (O14) and runs under its own `phase8` compose profile.
`client/clinical` is extended additively (M4), coordinated with Phase 7 M3, which widens the
same client (O9). `outcome-prediction-agent` reuses Phase 6's session, observability,
provider seam and output-gate pattern, with the self-hosted model as default (O15, O16).
The `RiskAssessment` follows `triage-service`'s resource type but adds a numeric probability,
using Phase 8's own models (O3).

## Terminology

Internal work is tracked as **milestones** (M1–M11, in `milestone-plan.md`) — never
"Phase 8.x", same convention as every prior phase. The prototype's own planned stages are mapped onto
these milestones in `milestone-plan.md` (O4); its stage numbering is not used anywhere.
