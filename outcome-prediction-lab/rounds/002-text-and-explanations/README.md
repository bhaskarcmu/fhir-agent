# Round 002 — text on codes and drug names, and self-explanatory patient narratives

**Type:** exploration + learning round, run entirely through the `outcome-prediction-lab` CLI.
**Status:** see `report.md`. **Label:** non-obstetric admission (`admit_nonobstetric_y2`, O47) —
so pregnancy codes can't inflate text-feature gains, the round-001 lesson.

## Questions

1. Does **TF-IDF on plain-language code descriptions** (words and word pairs from each code's full
   name) add anything over TF-IDF on the codes themselves?
2. Do **character n-grams on drug names** help — as model features, and for mapping messy free-text
   drug names to therapeutic classes (`drug-names` experiment)?
3. How much did round 001 lose by using only the third level of the drug-class hierarchy (a defect
   found while naming the classes)?
4. Can every patient get a **self-explanatory narrative**: plain words, full names instead of codes,
   comparisons with observed rates in meaningful groups of real adults?

## Method (fixed before running)

- Configs in `configs/`; every run is leave-one-panel-out CV on panels 21–25 (`outcome-prediction-lab run`).
- Reference: `ref-codes-lsa` — round 001's configuration (tuned gradient boosting, portable features,
  code-token LSA) on the corrected drug classes.
- **Test-panel rule:** a text variant is confirmed on panels 26–27 only if it beats the reference by
  ≥ +0.003 CV AUROC; otherwise there is **no test look this round**. Narratives explain test-panel
  patients without reporting their outcomes or any metric — not a performance look.
- Drug-name experiment: train on pharmacy names seen 2016–2020, test on names first seen 2021–2022.
