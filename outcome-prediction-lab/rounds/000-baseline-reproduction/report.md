# Round 000 report — M2's model reproduced through the lab

**Status:** complete — **passed**. **Pre-registration:** [`README.md`](./README.md). **Run through the
CLI:** [`configs/`](./configs/), [`runs/`](./runs/). **Test-panel looks:** 2, pre-registered and logged
in [`../../holdout-ledger.md`](../../holdout-ledger.md); both re-score results M2 had already reported.

## 1. Result

The lab's `confirm` reproduces M2 (`outcome-prediction-service/data/reports/metrics.json`) **bit for
bit** on the same 44,497 training and 11,863 test adults:

| Model | Measure | M2 | Lab (round 000) |
|---|---|---|---|
| `meps25-v1` (gradient boosting) | AUROC | 0.769008189627725 | 0.769008189627725 |
| | AUPRC | 0.2646971976727336 | 0.2646971976727336 |
| | Brier | 0.07247803262282396 | 0.07247803262282396 |
| | Mean predicted | 0.09172567531071446 | 0.09172567531071446 |
| `meps25-v1-comparison` (age + prior stay) | AUROC | 0.7076200378839681 | 0.7076200378839681 |
| | AUPRC | 0.2253834619054936 | 0.2253834619054936 |
| | Brier | 0.0750866564313514 | 0.0750866564313514 |
| | Mean predicted | 0.09024741815655428 | 0.09024741815655428 |

It is exact because the lab doesn't re-implement the model: `"model": "meps25-v1"` calls the service's
own `fit_gbm` / `fit_comparison` and matrices (O29) on the lab table without honest re-encoding.

## 2. The lab's cross-validated numbers (panels 21–25, leave one panel out)

New information M2 couldn't give — M2 has a single train/test split:

| Model | CV AUROC | AUPRC | Brier | AUROC 65+ | Top-10% precision |
|---|---|---|---|---|---|
| `meps25-v1` | 0.768 | 0.262 | 0.0702 | 0.699 | 29% |
| `meps25-v1-comparison` | 0.686 | 0.202 | 0.0734 | 0.647 | 25% |

Consistent with M2's test numbers (0.769 / 0.708): the gradient-boosting model generalises across
panels as it did to the later test panels. The comparison model does a little better on the test
panels than in CV (0.708 vs 0.686) — a two-input model is sensitive to panel-to-panel shifts in how
much prior stays predict.

## 3. What this proves about the tooling

- The CLI path (config → `run` → ledger → `confirm` → `card`) leaves numbers unchanged from the
  service's own path — so every round's results are comparable with the served model.
- The guards are covered by tests that show them refusing: configs naming panels or splits; `confirm`
  and `fairness` without a ledger entry; promotion without confirmation, card, matching checksum or
  decision; a `meps25-v1` config with any other features (`test_lab_tooling.py`).
- Model card for `meps25-v1`: [`cards/meps25-v1.md`](./cards/meps25-v1.md).

`meps25-v1` stays the **reference** model only (O55, `prediction-targets.md` §4): its label includes
childbirth (O47) and its inputs include non-portable spending (O52).
