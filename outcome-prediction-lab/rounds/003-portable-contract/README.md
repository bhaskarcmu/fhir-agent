# Round 003 — the portable feature contract (`meps-portable-v2`)

**Type:** production-readiness round, run through the `outcome-prediction-lab` CLI. **Status:** see `report.md`.

## Question

How much do the three lead targets lose when the models use **only what a customer's FHIR / claims
data can supply** (`outcome_prediction/contract.py`, O52) — no last-year spending (O25), no
MEPS-only CCSR groups or Multum drug classes, income usually missing — and does missingness
augmentation keep them well-calibrated when income is absent (O53)?

## Configs (all CV on panels 21–25)

| Target | `-research` | `-v2` (records only) | `-v2-claims` |
|---|---|---|---|
| Non-obstetric admission | round-002 reference (incl. spending, CCSR, Multum) | contract `portable-v2`, ICD-only codes → LSA, income augmented in training and blanked at scoring | + prescription fills, home-health days |
| Any ER visit | same pattern | same | same |
| High-cost patient | same pattern | same | same |

Baselines are portable too: age + the target's year-1 analogue, **never last year's spending**.

## Pre-registered test-panel looks (named before any run)

The production candidates, one logged look each, regardless of how CV turns out:
`nonobstetric-v2`, `any-ed-v2`, and `high-cost-v2-claims` — high cost needs claims to be validated
at all (`LABEL_OBSERVABILITY`, O54), so its production model is the claims version.
