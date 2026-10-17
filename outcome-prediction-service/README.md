# outcome-prediction-service

Phase 8's machine-learning service: builds the training data from AHRQ MEPS, and (from later
milestones) trains, evaluates and serves the 12-month hospitalization model as FHIR
`RiskAssessment`s. Planning, decisions and status: [`docs/phase8/`](../docs/phase8/README.md).

**Built so far:** M1 (MEPS acquisition, dataset build, variable dictionary) and M2 (training,
evaluation, model artifact). No API or compose service yet.

## Install

```bash
python -m pip install -e "outcome-prediction-service[dev]"
```

## Pipeline stages (one command each)

```bash
# 1. Download + checksum the seven two-year longitudinal panels (~38 MB of zips, ~720 MB extracted)
python -m outcome_prediction.meps.download

# 2. Build the modelling table: 56,360 adults, 4,820 year-2 hospitalizations
python -m outcome_prediction.meps.build
#    -> data/processed/meps_hosp12.csv
#    -> data/processed/meps_hosp12_build_report.json   (per-panel counts, resolved diagnosis columns)

# 3. Variable dictionary for any MEPS file (here HC-252)
python -m outcome_prediction.meps.dictionary 252
#    -> data/processed/h252_dictionary.csv

# 4. Evaluate (temporal test, panels 21-25 -> 26-27), refit on all panels, write the artifact
python -m outcome_prediction.model.train
#    -> models/gbm-meps25-v1-<table sha256[:12]>/   model.joblib, comparison.joblib,
#                                                   metadata.json, MANIFEST.sha256
#    -> data/reports/metrics.json, data/reports/model_report.md

# (evaluation only, no artifact)
python -m outcome_prediction.model.evaluate
```

**Artifacts** (`models/`, gitignored) are never overwritten: the model ID is derived from the
training table's checksum, so rebuilding from the same table means deleting the old artifact
deliberately. `load_artifact()` verifies every file against `MANIFEST.sha256` *before* any
`joblib` deserialisation, and refuses missing, changed or unlisted files. The headline metrics in
`metadata.json` come from the validation models (panels 21–25 → 26–27); the stored models are
refit on all panels, so their own held-out performance is unknown by construction.

`scikit-learn` is pinned to exactly 1.9.1 — pickled models aren't portable across versions.

Everything generated lands under `outcome-prediction-service/data/` (gitignored). Point several
worktrees at one cache with `OUTCOME_PREDICTION_DATA_DIR=/path/to/data`.

**Checksums.** The first download records each `.dta`'s SHA-256 in
`data/raw/meps/checksums.json`; every later run verifies it and stops with `ChecksumMismatch`
if a file changed. Delete the file to re-download deliberately.

## Tests

```bash
pytest outcome-prediction-service/src/outcome_prediction/tests -q -rs
```

Unit tests use tiny synthetic Stata files and a synthetic modelling table.
`test_meps_reproduction.py` and `test_model_reproduction.py` — the M1/M2 acceptance checks
against the prototype's exact numbers — need the real MEPS cache and **self-skip** without it
(as in CI, where the download is deliberately not run).

## Data and licence notes

MEPS public-use files are free US government data; whether their terms allow commercial use
of trained models is unconfirmed (`docs/phase8/decisions.md` O23,
[`data/reference/README.md`](../data/reference/README.md)). No PHI is ever used here.
