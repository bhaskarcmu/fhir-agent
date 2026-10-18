# Model card — `any-ed-v2` (round 003-portable-contract)

Production contract meps-portable-v2, records-only tier; income learned-missing and blanked at scoring.

| | |
|---|---|
| **Intended use** | Population-level planning aid for primary-care care management; not a diagnosis, not for emergencies |
| **Outcome** | `any_ed_y2` — at least one emergency-room visit (year 2 of a MEPS two-year panel) |
| **Population** | US civilian non-institutionalised adults (18+) in MEPS panels 21–27, observed in both years |
| **Training data** | Panels 21–25 (2016–2021); evaluation by leave-one-panel-out cross-validation |
| **Test data** | Panels 26–27 (2021–2023), scored once after a holdout-ledger entry |
| **Inputs** | 5 categorical + 26 numeric features (`portable-v2`); text representations: icd_lsa |
| **Model** | `gbm`, task `binary`, params round-001 tuned |
| **Cross-validated performance** | auroc 0.731, auprc 0.355, brier 0.115, top10_ppv 0.433, top10_sensitivity 0.283, auroc_65plus 0.692 (n = 44,497) |
| **Cross-validated baseline** | auroc 0.666, auprc 0.310, brier 0.121, top10_ppv 0.385, top10_sensitivity 0.252, auroc_65plus 0.653 (n = 44,497) |
| **Test performance** | auroc 0.740, auprc 0.373, brier 0.115, top10_ppv 0.439, top10_sensitivity 0.284, auroc_65plus 0.709 (n = 11,863) |
| **Test baseline** | auroc 0.682, auprc 0.325, brier 0.121, top10_ppv 0.417, top10_sensitivity 0.269, auroc_65plus 0.660 (n = 11,863) |
| **Feature contract** | portable-v2 — production contract meps-portable-v2 (O52) |
| **Missing inputs** | trained with missingness augmentation on povcaty1; scored with povcaty1 blanked, as production will |
| **Outcome observable by a customer** | records (within the health system) or claims (all ERs) |
| **Data provenance** | manifest sha256 `8467b5410f00…`, code `409fcf7a93b1` |

## Limitations

- Trained on MEPS **self-reported** survey data; customer records differ (codes, charges vs payments,
  missing income). Recalibrate and validate on customer data before any use (Phase 8b).
- Condition codes are 3-character ICD-10 and only for conditions linked to a year-1 medical event.
- Explanations describe what the model weighed, not causes.
- **Uplift / impactability is not assessable with MEPS** (no intervention data — O37): this model ranks
  risk, not who would benefit from outreach.
- Subgroup fairness by race/ethnicity and insurance is not yet reported on this card.
