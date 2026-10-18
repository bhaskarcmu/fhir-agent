# Model card — `meps25-v1` (round 000-baseline-reproduction)

M2's reference gradient-boosting model, fitted by the service's own code.

| | |
|---|---|
| **Intended use** | Population-level planning aid for primary-care care management; not a diagnosis, not for emergencies |
| **Outcome** | `label_hosp_12m` — at least one inpatient discharge (the prototype's label; includes childbirth) (year 2 of a MEPS two-year panel) |
| **Population** | US civilian non-institutionalised adults (18+) in MEPS panels 21–27, observed in both years |
| **Training data** | Panels 21–25 (2016–2021); evaluation by leave-one-panel-out cross-validation |
| **Test data** | Panels 26–27 (2021–2023), scored once after a holdout-ledger entry |
| **Inputs** | 5 categorical + 20 numeric features (`prototype`); text representations: none |
| **Model** | `meps25-v1`, task `binary`, params the service's fixed meps25-v1 settings |
| **Cross-validated performance** | auroc 0.768, auprc 0.262, brier 0.070, top10_ppv 0.293, top10_sensitivity 0.345, auroc_65plus 0.699 (n = 44,497) |
| **Cross-validated baseline** | _not available_ |
| **Test performance** | auroc 0.769, auprc 0.265, brier 0.072, top10_ppv 0.293, top10_sensitivity 0.333, auroc_65plus 0.695 (n = 11,863) |
| **Test baseline** | _not available_ |
| **Feature contract** | meps25-v1 — M2's reproduced reference contract (the prototype's inputs and encoding); superseded for new work by meps-portable-v2 (O52) |
| **Missing inputs** | trained with missingness augmentation on none; scored with nothing blanked, as production will |
| **Outcome observable by a customer** | records (within the health system) or claims (all hospitals) |
| **Data provenance** | manifest sha256 `8467b5410f00…`, code `c21cae0d8473` |

## Subgroup fairness

_Not yet assessed — run `outcome-prediction-lab fairness`._

## Limitations

- Trained on MEPS **self-reported** survey data; customer records differ (codes, charges vs payments,
  missing income). Recalibrate and validate on customer data before any use (Phase 8b).
- Condition codes are 3-character ICD-10 and only for conditions linked to a year-1 medical event.
- Explanations describe what the model weighed, not causes.
- **Uplift / impactability is not assessable with MEPS** (no intervention data — O37): this model ranks
  risk, not who would benefit from outreach.
