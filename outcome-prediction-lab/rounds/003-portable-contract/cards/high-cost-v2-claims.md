# Model card — `high-cost-v2-claims` (round 003-portable-contract)

Production contract plus claims-only inputs (prescription fills, home-health days).

| | |
|---|---|
| **Intended use** | Population-level planning aid for primary-care care management; not a diagnosis, not for emergencies |
| **Outcome** | `high_cost_y2` — health care costs among the highest 10% of adults (year 2 of a MEPS two-year panel) |
| **Population** | US civilian non-institutionalised adults (18+) in MEPS panels 21–27, observed in both years |
| **Training data** | Panels 21–25 (2016–2021); evaluation by leave-one-panel-out cross-validation |
| **Test data** | Panels 26–27 (2021–2023), scored once after a holdout-ledger entry |
| **Inputs** | 5 categorical + 28 numeric features (`portable-v2+claims`); text representations: icd_lsa |
| **Model** | `gbm`, task `binary`, params round-001 tuned |
| **Cross-validated performance** | auroc 0.847, auprc 0.453, brier 0.070, top10_ppv 0.456, top10_sensitivity 0.455, auroc_65plus 0.787 (n = 44,497) |
| **Cross-validated baseline** | auroc 0.734, auprc 0.264, brier 0.083, top10_ppv 0.303, top10_sensitivity 0.303, auroc_65plus 0.641 (n = 44,497) |
| **Test performance** | auroc 0.834, auprc 0.419, brier 0.072, top10_ppv 0.436, top10_sensitivity 0.436, auroc_65plus 0.782 (n = 11,863) |
| **Test baseline** | auroc 0.722, auprc 0.249, brier 0.084, top10_ppv 0.290, top10_sensitivity 0.290, auroc_65plus 0.634 (n = 11,863) |
| **Feature contract** | portable-v2+claims — production contract meps-portable-v2 (O52) |
| **Missing inputs** | trained with missingness augmentation on povcaty1; scored with povcaty1 blanked, as production will |
| **Outcome observable by a customer** | claims only — a records-only customer can never validate or recalibrate it |
| **Data provenance** | manifest sha256 `8467b5410f00…`, code `409fcf7a93b1` |

## Subgroup fairness (test panels)

Full tables: [`fairness/high-cost-v2-claims.md`](../fairness/high-cost-v2-claims.md). Widest gaps among groups with enough events:

| Dimension | AUROC range | Calibration ratio range | Cases caught by the top-10% flag |
|---|---|---|---|
| Race / ethnicity | 0.811–0.885 | 0.85–1.20 | 26%–58% |
| Insurance (year 1) | 0.816–0.831 | 1.04–1.05 | 35%–55% |
| Sex | 0.823–0.846 | 1.04–1.06 | 41%–46% |
| Age band | 0.770–0.825 | 1.01–1.16 | 23%–58% |

## Limitations

- Trained on MEPS **self-reported** survey data; customer records differ (codes, charges vs payments,
  missing income). Recalibrate and validate on customer data before any use (Phase 8b).
- Condition codes are 3-character ICD-10 and only for conditions linked to a year-1 medical event.
- Explanations describe what the model weighed, not causes.
- **Uplift / impactability is not assessable with MEPS** (no intervention data — O37): this model ranks
  risk, not who would benefit from outreach.
