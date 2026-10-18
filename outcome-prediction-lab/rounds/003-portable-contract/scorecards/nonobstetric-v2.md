# Target scorecard — `admit_nonobstetric_y2` via `nonobstetric-v2` (round 003-portable-contract)

| Criterion | Source | Assessment |
|---|---|---|
| Discrimination | test | AUROC 0.795, AUPRC 0.276 (baseline AUROC 0.748, CV) |
| Calibration | test | Brier 0.0647; mean predicted 0.080 vs rate 0.079 |
| Base rate | data | 7.9% |
| Worklist value | test | top 10%: 30% have the outcome; they hold 38% of all cases |
| Adults 65+ | test | AUROC 0.701 |
| Measurable in customer data | person | **Yes — records or claims** — Inpatient Encounters with a non-obstetric reason; records-only customers see only their own hospitals. |
| Actionable | person | **High** — The classic care-management enrolment signal; includes planned stays (surgery), so it's broader than avoidable admissions. |
| Lead time | person | **Good** — 12-month horizon from a year of history: weeks to months to act for most patients; little lead time for events in the first weeks. |
| FHIR representability | person | **Native** — A 12-month event probability maps directly onto RiskAssessment.prediction.probabilityDecimal (O3). |
| Regulatory posture | person | **Non-device CDS likely** — Population-level planning aid reviewed by a clinician, with its basis shown (per-patient narratives); not time-critical, not a diagnosis. Same posture for all four; to be confirmed by regulatory review before Phase 8b. |
| Uplift / impactability | — | Not assessable with MEPS (no intervention data — O37) |
