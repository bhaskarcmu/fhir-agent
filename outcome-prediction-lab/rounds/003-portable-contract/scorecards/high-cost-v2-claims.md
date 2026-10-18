# Target scorecard — `high_cost_y2` via `high-cost-v2-claims` (round 003-portable-contract)

| Criterion | Source | Assessment |
|---|---|---|
| Discrimination | test | AUROC 0.834, AUPRC 0.419 (baseline AUROC 0.734, CV) |
| Calibration | test | Brier 0.0722; mean predicted 0.105 vs rate 0.100 |
| Base rate | data | 10.0% |
| Worklist value | test | top 10%: 44% have the outcome; they hold 44% of all cases |
| Adults 65+ | test | AUROC 0.782 |
| Measurable in customer data | person | _TO BE SCORED BY A PERSON_ — Can a customer's own FHIR / claims data observe this outcome (needed to validate and recalibrate)? |
| Actionable | person | _TO BE SCORED BY A PERSON_ — What would a care manager do differently for a flagged patient? |
| Lead time | person | _TO BE SCORED BY A PERSON_ — Is there time to act before the outcome happens? |
| FHIR representability | person | _TO BE SCORED BY A PERSON_ — Probability -> RiskAssessment natively; count / cost needs a decision revisiting O3 (O35). |
| Regulatory posture | person | _TO BE SCORED BY A PERSON_ — Does this change the FDA clinical-decision-support position? |
| Uplift / impactability | — | Not assessable with MEPS (no intervention data — O37) |
