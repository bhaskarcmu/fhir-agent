# Model card — `ref-codes-lsa` (round 002-text-and-explanations)

Reference: round 001's configuration on the corrected drug classes.

| | |
|---|---|
| **Intended use** | Population-level planning aid for primary-care care management; not a diagnosis, not for emergencies |
| **Outcome** | `admit_nonobstetric_y2` — an overnight hospital stay that isn't related to pregnancy or childbirth (year 2 of a MEPS two-year panel) |
| **Population** | US civilian non-institutionalised adults (18+) in MEPS panels 21–27, observed in both years |
| **Training data** | Panels 21–25 (2016–2021); evaluation by leave-one-panel-out cross-validation |
| **Test data** | Panels 26–27 (2021–2023), scored once after a holdout-ledger entry |
| **Inputs** | 5 categorical + 30 numeric features (`portable+knowledge`); text representations: lsa |
| **Model** | `gbm`, task `binary`, params round-001 tuned |
| **Cross-validated performance** | auroc 0.799, auprc 0.272, brier 0.061, top10_ppv 0.292, top10_sensitivity 0.394, auroc_65plus 0.702 (n = 44,497) |
| **Cross-validated baseline** | auroc 0.748, auprc 0.225, brier 0.063, top10_ppv 0.247, top10_sensitivity 0.334, auroc_65plus 0.647 (n = 44,497) |
| **Test performance** | _not confirmed_ |
| **Test baseline** | _not confirmed_ |
| **Data provenance** | manifest sha256 `8467b5410f00…`, code `40d0d76af0c7` |

## Limitations

- Trained on MEPS **self-reported** survey data; customer records differ (codes, charges vs payments,
  missing income). Recalibrate and validate on customer data before any use (Phase 8b).
- Condition codes are 3-character ICD-10 and only for conditions linked to a year-1 medical event.
- Explanations describe what the model weighed, not causes.
- **Uplift / impactability is not assessable with MEPS** (no intervention data — O37): this model ranks
  risk, not who would benefit from outreach.
- Subgroup fairness by race/ethnicity and insurance is not yet reported on this card.
