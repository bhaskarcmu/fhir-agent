# Target scorecard — `admit_nonobstetric_y2` via `ref-codes-lsa` (round 002-text-and-explanations)

| Criterion | Source | Assessment |
|---|---|---|
| Discrimination | CV | AUROC 0.799, AUPRC 0.272 (baseline AUROC 0.748, CV) |
| Calibration | CV | Brier 0.0608; mean predicted 0.074 vs rate 0.074 |
| Base rate | data | 7.4% |
| Worklist value | CV | top 10%: 29% have the outcome; they hold 39% of all cases |
| Adults 65+ | CV | AUROC 0.702 |
| Measurable in customer data | person | _TO BE SCORED BY A PERSON_ — Can a customer's own FHIR / claims data observe this outcome (needed to validate and recalibrate)? |
| Actionable | person | _TO BE SCORED BY A PERSON_ — What would a care manager do differently for a flagged patient? |
| Lead time | person | _TO BE SCORED BY A PERSON_ — Is there time to act before the outcome happens? |
| FHIR representability | person | _TO BE SCORED BY A PERSON_ — Probability -> RiskAssessment natively; count / cost needs a decision revisiting O3 (O35). |
| Regulatory posture | person | _TO BE SCORED BY A PERSON_ — Does this change the FDA clinical-decision-support position? |
| Uplift / impactability | — | Not assessable with MEPS (no intervention data — O37) |
