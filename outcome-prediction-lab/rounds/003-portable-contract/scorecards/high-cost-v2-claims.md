# Target scorecard — `high_cost_y2` via `high-cost-v2-claims` (round 003-portable-contract)

| Criterion | Source | Assessment |
|---|---|---|
| Discrimination | test | AUROC 0.834, AUPRC 0.419 (baseline AUROC 0.734, CV) |
| Calibration | test | Brier 0.0722; mean predicted 0.105 vs rate 0.100 |
| Base rate | data | 10.0% |
| Worklist value | test | top 10%: 44% have the outcome; they hold 44% of all cases |
| Adults 65+ | test | AUROC 0.782 |
| Measurable in customer data | person | **Claims only (O54)** — Total next-year spending needs paid claims across all providers; records hold one system's charges. |
| Actionable | person | **Medium — finance, not need** — Useful for budgeting and programme sizing. Must NOT be used alone to allocate care: cost-based targeting under-serves groups with less access to care (Obermeyer et al., 2019; round 004 found uninsured adults almost never flagged). |
| Lead time | person | **Good** — 12-month horizon from a year of history: weeks to months to act for most patients; little lead time for events in the first weeks. |
| FHIR representability | person | **Native** — A 12-month event probability maps directly onto RiskAssessment.prediction.probabilityDecimal (O3). |
| Regulatory posture | person | **Non-device; fairness review needed** — Financial use is outside clinical decision support, but resource-allocation use needs a documented fairness review per customer (O57). |
| Uplift / impactability | — | Not assessable with MEPS (no intervention data — O37) |
