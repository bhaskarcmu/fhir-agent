# Target scorecard — `admit_via_er_y2` via `er-admit-v2` (round 004-focus-four-readiness)

| Criterion | Source | Assessment |
|---|---|---|
| Discrimination | test | AUROC 0.785, AUPRC 0.192 (baseline AUROC 0.735, CV) |
| Calibration | test | Brier 0.0432; mean predicted 0.051 vs rate 0.049 |
| Base rate | data | 4.9% |
| Worklist value | test | top 10%: 20% have the outcome; they hold 40% of all cases |
| Adults 65+ | test | AUROC 0.729 |
| Measurable in customer data | person | **Yes — records or claims** — Admission source = emergency department is on the inpatient Encounter (hospitalization.admitSource) or the claim's point of origin; records-only customers see only their own hospitals. |
| Actionable | person | **High** — Unplanned admissions are what care management tries to prevent: outreach, medication reconciliation, same-day / after-hours access, care plans for exacerbations. |
| Lead time | person | **Good** — 12-month horizon from a year of history: weeks to months to act for most patients; little lead time for events in the first weeks. |
| FHIR representability | person | **Native** — A 12-month event probability maps directly onto RiskAssessment.prediction.probabilityDecimal (O3). |
| Regulatory posture | person | **Non-device CDS likely** — Population-level planning aid reviewed by a clinician, with its basis shown (per-patient narratives); not time-critical, not a diagnosis. Same posture for all four; to be confirmed by regulatory review before Phase 8b. |
| Uplift / impactability | — | Not assessable with MEPS (no intervention data — O37) |
