# Phase 8 — Patient Outcome Prediction

> ## Canonical status
>
> **🚧 Focus: four predictions (O55)** — admission through the ER, hospital stay not related to
> pregnancy or childbirth, any ER visit, and being a high-cost patient ([`prediction-targets.md`](./prediction-targets.md)).
> **M1–M2 built** (prototype reproduced exactly). **M3 built** (closed, O60): rounds 000–004 (000: M2 reproduced through the lab, bit for bit) — the lab and
> its CLI, nine targets explored, plain-language narratives, the portable contract
> `meps-portable-v2`, and production models for **all four** (test AUROC: ER admission 0.785,
> non-obstetric stay 0.795, any ER visit 0.740, high cost 0.834), each with a subgroup fairness report
> and a 65+ check (no separate 65+ model needed). **First promotion (O59): non-obstetric hospital
> stay**, to be served in M12.
> M10/M11 folded into M3 (O45). M4–M13 planned. A research prototype from an earlier session
> was handed over and reconciled with this repo's conventions; what it established is restated
> in `prototype-baseline.md`, and the raw hand-off documents are not kept in the repo (O5). A
> second pass added a permanent **experimentation track** (`outcome-prediction-lab`, O28–O40).
> `prd.md`, `design.md`, `decisions.md` (`O1`–`O60`), `milestone-plan.md` (M1–M13) and
> `experimentation-protocol.md` reflect both passes. Cloud deployment, recalibration and monitoring
> are reserved for **Phase 8b**.
>
> *This is the one canonical status statement. Other documents link here rather than restate it.*
>
> - [`prd.md`](./prd.md) — problem statement, goals/non-goals, users and triggers, functional
>   requirements (the prototype's `FR-*` IDs kept, with status), acceptance criteria, and §11:
>   every deviation from the prototype's plan.
> - [`design.md`](./design.md) — repo layout, components, the `meps25-v1` feature contract, the
>   `RiskAssessment` shape, training vs scoring mode, the FHIR mapping sketch, model artifacts,
>   the agent's tool contract, testing, the prototype defects found in review, and the
>   experimentation workbench (§12).
> - [`prediction-targets.md`](./prediction-targets.md) — the four focus predictions, the decision path
>   that led to them, and where all parked work lives.
> - [`decisions.md`](./decisions.md) — the ADR-style index (`O1`–`O60`), same convention as
>   Phase 2/3/4/6/7.
> - [`milestone-plan.md`](./milestone-plan.md) — M1–M13, short and long story for each, with the
>   mapping from the prototype's planned stages.
> - [`experimentation-protocol.md`](./experimentation-protocol.md) — the standing runbook for
>   research rounds: rules, steps, the target scorecard, the holdout ledger, promotion, and how
>   to resume after a long gap. Outlives the phase.
> - [`prototype-baseline.md`](./prototype-baseline.md) — what the research prototype
>   established: data-source choices, MEPS and Synthea facts, the prototype's method, the exact
>   numbers M1, M2 and M4 must reproduce, and reference URLs.

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

## Research that outlives the phase

Which outcomes are worth predicting — and as a probability, a count, a cost or a tier — is a
question this phase starts answering, not one it closes. `outcome-prediction-lab/` (built in
M3) is the permanent workbench: config-driven runs tracked in a local MLflow store, committed
round reports, a target scorecard that weighs measurability in customer data and actionability
alongside model metrics, and model cards. Two rules keep it honest: the test panels are opened
only for logged confirmation (O32), and nothing reaches the service without a promotion record
tied to a decision (O33). Later explorations are new **rounds** under
`experimentation-protocol.md`, never reopened milestones (O28).

## Data that outlives its source

The MEPS files are public and re-downloadable, but a source can go down, move, or quietly
republish different bytes. So the data is **pinned in git** — the committed
`outcome-prediction-service/meps-manifest.json` records the SHA-256 of every original file,
documentation page and codebook — and **preserved outside it**, in write-once,
content-addressed private mirrors. Downloads accept only bytes that match the manifest, and
fall back to a mirror when AHRQ can't supply them (O41, O42; `design.md` §13). Today the
preserved copy is the repo owner's off-workspace `file://` mirror; the retention-protected GCS
bucket (`outcome-prediction-service/infra/`) is ready but deferred, with a local GCS emulator
standing in for testing (O43).

## Relationship to Phase 1, 6, and 7

Additive. `fhir-service`, `triage-service`, `mcp-agent` and the Kong gateway are unmodified;
the new service is internal-only (O14) and runs under its own `phase8` compose profile.
`client/clinical` is extended additively (M5), coordinated with Phase 7 M3, which widens the
same client (O9). `outcome-prediction-agent` reuses Phase 6's session, observability,
provider seam and output-gate pattern, with the self-hosted model as default (O15, O16).
The `RiskAssessment` follows `triage-service`'s resource type but adds a numeric probability,
using Phase 8's own models (O3).

## Terminology

Internal work is tracked as **milestones** (M1–M13, in `milestone-plan.md`) — never
"Phase 8.x", same convention as every prior phase. The prototype's own planned stages are mapped onto
these milestones in `milestone-plan.md` (O4); its stage numbering is not used anywhere.
