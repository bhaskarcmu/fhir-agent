# Model card — `er-admit-v2` (round 004-focus-four-readiness)

Production contract meps-portable-v2, records-only tier; income learned-missing and blanked at scoring.

| | |
|---|---|
| **Intended use** | Population-level planning aid for primary-care care management; not a diagnosis, not for emergencies |
| **Outcome** | `admit_via_er_y2` — a hospital admission through the emergency room (year 2 of a MEPS two-year panel) |
| **Population** | US civilian non-institutionalised adults (18+) in MEPS panels 21–27, observed in both years |
| **Training data** | Panels 21–25 (2016–2021); evaluation by leave-one-panel-out cross-validation |
| **Test data** | Panels 26–27 (2021–2023), scored once after a holdout-ledger entry |
| **Inputs** | 5 categorical + 26 numeric features (`portable-v2`); text representations: icd_lsa |
| **Model** | `gbm`, task `binary`, params round-001 tuned |
| **Cross-validated performance** | auroc 0.780, auprc 0.186, brier 0.043, top10_ppv 0.195, top10_sensitivity 0.399, auroc_65plus 0.717 (n = 44,497) |
| **Cross-validated baseline** | auroc 0.735, auprc 0.164, brier 0.044, top10_ppv 0.176, top10_sensitivity 0.360, auroc_65plus 0.679 (n = 44,497) |
| **Test performance** | auroc 0.785, auprc 0.192, brier 0.043, top10_ppv 0.199, top10_sensitivity 0.403, auroc_65plus 0.729 (n = 11,863) |
| **Test baseline** | auroc 0.754, auprc 0.185, brier 0.044, top10_ppv 0.189, top10_sensitivity 0.383, auroc_65plus 0.685 (n = 11,863) |
| **Feature contract** | portable-v2 — production contract meps-portable-v2 (O52) |
| **Missing inputs** | trained with missingness augmentation on povcaty1; scored with povcaty1 blanked, as production will |
| **Outcome observable by a customer** | records (within the health system) or claims (all hospitals) |
| **Data provenance** | manifest sha256 `8467b5410f00…`, code `548f63b5d0c5` |

## Subgroup fairness (test panels)

Full tables: [`fairness/er-admit-v2.md`](../fairness/er-admit-v2.md). Widest gaps among groups with enough events:

| Dimension | AUROC range | Calibration ratio range | Cases caught by the top-10% flag |
|---|---|---|---|
| Race / ethnicity | 0.639–0.812 | 0.90–1.12 | 19%–43% |
| Insurance (year 1) | 0.686–0.752 | 0.89–1.24 | 0%–52% |
| Sex | 0.767–0.810 | 0.98–1.11 | 34%–44% |
| Age band | 0.666–0.751 | 0.92–1.21 | 7%–67% |

## Limitations

- Trained on MEPS **self-reported** survey data; customer records differ (codes, charges vs payments,
  missing income). Recalibrate and validate on customer data before any use (Phase 8b).
- Condition codes are 3-character ICD-10 and only for conditions linked to a year-1 medical event.
- Explanations describe what the model weighed, not causes.
- **Uplift / impactability is not assessable with MEPS** (no intervention data — O37): this model ranks
  risk, not who would benefit from outreach.
