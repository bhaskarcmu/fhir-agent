# Target scorecard — `label_hosp_12m` via `meps25-v1-comparison` (round 000-baseline-reproduction)

| Criterion | Source | Assessment |
|---|---|---|
| Discrimination | test | AUROC 0.708, AUPRC 0.225 |
| Calibration | test | Brier 0.0751; mean predicted 0.090 vs rate 0.088 |
| Base rate | data | 8.8% |
| Worklist value | test | top 10%: 27% have the outcome; they hold 30% of all cases |
| Adults 65+ | test | AUROC 0.639 |
| Measurable in customer data | person | _TO BE SCORED BY A PERSON_ — Can a customer's own FHIR / claims data observe this outcome (needed to validate and recalibrate)? |
| Actionable | person | _TO BE SCORED BY A PERSON_ — What would a care manager do differently for a flagged patient? |
| Lead time | person | _TO BE SCORED BY A PERSON_ — Is there time to act before the outcome happens? |
| FHIR representability | person | _TO BE SCORED BY A PERSON_ — Probability -> RiskAssessment natively; count / cost needs a decision revisiting O3 (O35). |
| Regulatory posture | person | _TO BE SCORED BY A PERSON_ — Does this change the FDA clinical-decision-support position? |
| Uplift / impactability | — | Not assessable with MEPS (no intervention data — O37) |
