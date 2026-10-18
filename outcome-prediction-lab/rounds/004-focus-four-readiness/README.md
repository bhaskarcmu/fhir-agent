# Round 004 — readiness of the four focus predictions

**Type:** production-readiness round (decisions.md O55), run through the CLI. **Status:** see `report.md`.

## Questions

1. **Admission through the emergency room** — the only focus target without a production-contract
   (`meps-portable-v2`) model. How well does one do?
2. **Fairness** — for all four production models, how do discrimination, calibration and the top-10%
   flag differ by race/ethnicity, insurance type, sex and age band (FR-E6)?
3. **Adults 65+** — how do the four production models perform and calibrate for 65+ (the population
   risk-bearing Medicare practices care about most), and does a **65+-only specialist** model do better
   (FR-M6)?

## Configs (CV on panels 21–25)

- `er-admit-research` / `er-admit-v2` / `er-admit-v2-claims` — same pattern as round 003; baseline
  age + prior stays + prior ER visits.
- `<target>-65plus` for all four — the production configuration trained and scored on adults 65+ only
  (`"population": {"age_min": 65}`).

## Pre-registered test-panel looks (named before any run)

- `er-admit-v2` — confirmation of the records-only production candidate (ER-origin admissions are
  observable in records).
- Fairness, one logged look each, on the four production models: `003/nonobstetric-v2`, `003/any-ed-v2`,
  `003/high-cost-v2-claims`, `004/er-admit-v2`.
- **65+ specialists: confirmed only if** a specialist's CV AUROC on 65+ beats the general production
  model's CV AUROC on 65+ by **≥ +0.005**; otherwise no look, and the general model stays.
