# Target scorecard — `any_ed_y2` via `any-ed-v2` (round 003-portable-contract)

| Criterion | Source | Assessment |
|---|---|---|
| Discrimination | test | AUROC 0.740, AUPRC 0.373 (baseline AUROC 0.666, CV) |
| Calibration | test | Brier 0.1155; mean predicted 0.152 vs rate 0.155 |
| Base rate | data | 15.5% |
| Worklist value | test | top 10%: 44% have the outcome; they hold 28% of all cases |
| Adults 65+ | test | AUROC 0.709 |
| Measurable in customer data | person | _TO BE SCORED BY A PERSON_ — Can a customer's own FHIR / claims data observe this outcome (needed to validate and recalibrate)? |
| Actionable | person | _TO BE SCORED BY A PERSON_ — What would a care manager do differently for a flagged patient? |
| Lead time | person | _TO BE SCORED BY A PERSON_ — Is there time to act before the outcome happens? |
| FHIR representability | person | _TO BE SCORED BY A PERSON_ — Probability -> RiskAssessment natively; count / cost needs a decision revisiting O3 (O35). |
| Regulatory posture | person | _TO BE SCORED BY A PERSON_ — Does this change the FDA clinical-decision-support position? |
| Uplift / impactability | — | Not assessable with MEPS (no intervention data — O37) |
