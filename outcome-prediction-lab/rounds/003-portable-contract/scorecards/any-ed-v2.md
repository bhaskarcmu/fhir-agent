# Target scorecard — `any_ed_y2` via `any-ed-v2` (round 003-portable-contract)

| Criterion | Source | Assessment |
|---|---|---|
| Discrimination | test | AUROC 0.740, AUPRC 0.373 (baseline AUROC 0.666, CV) |
| Calibration | test | Brier 0.1155; mean predicted 0.152 vs rate 0.155 |
| Base rate | data | 15.5% |
| Worklist value | test | top 10%: 44% have the outcome; they hold 28% of all cases |
| Adults 65+ | test | AUROC 0.709 |
| Measurable in customer data | person | **Yes — records or claims** — Emergency Encounters (class EMER); records-only customers miss visits to other systems' ERs. |
| Actionable | person | **High** — Access interventions (same-day appointments, nurse lines, urgent care) aim squarely at avoidable ER use; strongest lift over a simple rule of the four. |
| Lead time | person | **Good** — 12-month horizon from a year of history: weeks to months to act for most patients; little lead time for events in the first weeks. |
| FHIR representability | person | **Native** — A 12-month event probability maps directly onto RiskAssessment.prediction.probabilityDecimal (O3). |
| Regulatory posture | person | **Non-device CDS likely** — Population-level planning aid reviewed by a clinician, with its basis shown (per-patient narratives); not time-critical, not a diagnosis. Same posture for all four; to be confirmed by regulatory review before Phase 8b. |
| Uplift / impactability | — | Not assessable with MEPS (no intervention data — O37) |
