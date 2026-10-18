# Round 000 — reproduce M2's model through the lab

**Type:** tooling proof (milestone-plan M3, FR-X4). Run through the CLI. **Status:** see `report.md`.

Numbered 000 because it is what M3 was specified to start with; it was run after rounds 001–004,
once the lab could call the service's own fitting code (`"model": "meps25-v1"`, O29).

## Question

Does the lab, run through its CLI, reproduce M2's `meps25-v1` models — the service's gradient
boosting model and its age + prior-stay comparison model — **exactly**?

## Configs

- `meps25-v1` — the service's `fit_gbm` on `feature_matrix` (prototype inputs and encoding).
- `meps25-v1-comparison` — the service's `fit_comparison` on `comparison_matrix`.

Both read the lab table without the honest re-encoding (`runs.reference_frame`), because the
prototype's encoding is part of the `meps25-v1` contract.

## Pre-registered test-panel looks

`meps25-v1` and `meps25-v1-comparison`, once each. These re-score test panels whose results M2
already reported, so they reveal nothing new; they are logged anyway, like every look.

**Pass criterion:** test AUROC, AUPRC, Brier and mean predicted equal
`outcome-prediction-service/data/reports/metrics.json` (M2) to 1e-9, on the same 44,497 training and
11,863 test adults.
