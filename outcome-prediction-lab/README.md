# outcome-prediction-lab

Phase 8's experimentation workbench: research **rounds** that explore what to predict and how,
without eroding the test set. Runbook: [`docs/phase8/experimentation-protocol.md`](../docs/phase8/experimentation-protocol.md).
Decisions: `docs/phase8/decisions.md` O28–O48.

Imports `outcome-prediction-service` (dataset build, model definitions, MEPS download) — one
implementation, not a fork (O29). Nothing in the service imports the lab.

## Install

Needs **Python 3.12+** (`shap` ≥ 0.52 requires it); the service it imports still supports 3.11.
CI runs the lab in its own `phase8 lab (python 3.12)` job.

```bash
python -m pip install -e "outcome-prediction-service[dev]" -e "outcome-prediction-lab[dev]"
python -m pip install -e "outcome-prediction-lab[tracking]"   # optional: MLflow (local SQLite store)
```

## Round 001 — what to predict, and how

Results: [`rounds/001-what-and-how/report.md`](./rounds/001-what-and-how/report.md).

```bash
python -m outcome_prediction_lab.round_001 cv_any_stay     # prototype objective: concepts and models, CV
python -m outcome_prediction_lab.round_001 cv_finalists    # settle choices on CV (incl. the pregnancy check)
python -m outcome_prediction_lab.round_001 cv_missing      # production-like missingness
python -m outcome_prediction_lab.round_001 cv_targets      # new targets vs simple baselines, CV
python -m outcome_prediction_lab.round_001 confirm         # ONE logged look at test panels 26–27
python -m outcome_prediction_lab.round_001 explain         # SHAP, surrogate tree, narratives, action items
```

`confirm` refuses to score any candidate without a prior entry in
[`holdout-ledger.md`](./holdout-ledger.md) (O32).

## What's in the package

| Module | What it does |
|---|---|
| `data.py` | The lab table: 56,360 adults × 82 columns from 28 MEPS files (manifest-pinned); person-ID normalisation; year-1 code "documents"; year-2 labels |
| `knowledge.py` | Hospital Frailty Risk Score and Charlson/Elixhauser (ICD-10, Quan) tables, vendored from comorbidipy (MIT) |
| `features.py` | Honest missing-value encoding; feature sets; pipelines (gradient boosting, random forest, TF-IDF logistic regression, LSA, autoencoders) — every learned step inside the pipeline, refit per fold |
| `evaluate.py` | Leave-one-panel-out CV; binary / count / cost metrics; paired bootstrap |
| `holdout.py` | The ledger and its guard |
| `explain.py` | SHAP importance and per-patient templated narratives; code pattern traced to the patient's codes; surrogate and single trees; value-of-information action items |
| `round_001.py` | The round's stages |

## Data

The lab reads MEPS through `outcome_prediction.meps.download`, so every file is verified against
the committed manifest and fetched from the archive, AHRQ or a mirror as needed. Its table is
cached at `outcome-prediction-service/data/processed/lab_table.joblib` (gitignored).

## Tests

```bash
pytest outcome-prediction-lab/src/outcome_prediction_lab/tests -q
```

Unit tests only (synthetic data): ledger guard, ID normalisation, targets, knowledge scores,
honest encoding, autoencoder, bootstrap, narratives.
