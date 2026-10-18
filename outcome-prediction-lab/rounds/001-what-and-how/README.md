# Round 001 — what to predict, and how

**Type:** exploration + learning round (first round under `docs/phase8/experimentation-protocol.md`;
M3, with the former M10/M11 folded in). **Status:** see `report.md`.

## Questions

1. **How much better can we do on the prototype's exact objective** — any inpatient stay in year 2,
   trained on panels 21–25, tested on panels 26–27 — and where does any gain come from?
2. **What else is worth predicting** from MEPS, and how well can it be predicted?
3. **Which concepts help:** honest missing-value encoding, code features via TF-IDF (sparse, and
   compressed with LSA), autoencoder embeddings (plain and denoising), random forest, published
   clinical knowledge (frailty / Charlson / Elixhauser), monotonic constraints, tuning,
   missingness handling, and model interpretation.

## Method (fixed before any test-panel look)

- All choices made on **leave-one-panel-out cross-validation within panels 21–25**.
- Test panels 26–27 scored **once**, for the finalists below, each logged in
  `../../holdout-ledger.md` before scoring.
- Any-stay improvement reported as a **paired bootstrap** difference against the prototype on the
  same test people (500 resamples, seed 0), for AUROC, AUPRC and AUROC among adults 65+.

## Finalists (named after CV, before the test look)

Chosen on CV (see `metrics.json` → `cv_any_stay`, `cv_finalists`):

| Candidate | Definition |
|---|---|
| `any_stay/prototype` | The prototype exactly (reference) |
| `any_stay/new-portable` | Tuned gradient boosting (lr 0.03, 15 leaves, min leaf 120, L2 1.0, 600 iterations) on honest-encoded portable features + coverage + code counts + knowledge scores + **TF-IDF/LSA code representation (32 dims)** — best portable CV AUROC |
| `any_stay/new-with-survey` | The same plus year-1 survey items — **not portable** to records; reported to size the gap |
| `target/<name>` (8) | The `new-portable` configuration on each new target, against a simple baseline (age + the target's own year-1 analogue) |

Pre-stated caveat from CV (`cv_pregnancy_check`): most of the code representation's gain on the
any-stay label comes from pregnancy codes predicting childbirth admissions; on the non-obstetric
label and among men the gain is ≈ +0.002 AUROC. The test look will report both.
