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

## Data manifest and private mirror

Data is never committed, but **`meps-manifest.json` is**: the URL and SHA-256 of every original
zip, extracted `.dta`, documentation page and codebook. `download` accepts only bytes that match
it, trying the local archive, then AHRQ, then each private mirror. If AHRQ republishes a file,
the original still comes from a mirror until the manifest is deliberately updated.
(`docs/phase8/decisions.md` O41, O42; `design.md` §13.)

```bash
# Record the originals (zips + doc pages + codebooks) — first time, or to re-check
python -m outcome_prediction.meps.manifest snapshot
# AHRQ changed a file? Adopting it is a deliberate, reviewed manifest change:
python -m outcome_prediction.meps.manifest snapshot --accept-change

# Copy the originals to every configured mirror (write-once), and audit them
export OUTCOME_PREDICTION_MEPS_MIRRORS=gs://<bucket>,file:///mnt/backup/meps   # tried in order
python -m outcome_prediction.meps.mirror push
python -m outcome_prediction.meps.mirror verify
```

`gs://` mirrors need `pip install -e "outcome-prediction-service[gcs]"`. `file://` is any
directory — e.g. an off-workspace disk, which is where the preserved copy lives today.

### Local GCS emulator (stands in for the real bucket)

The real bucket is deferred (`docs/phase8/decisions.md` O43). To exercise the `gs://` path with
the real `google-cloud-storage` client, run the emulator from docker-compose:

```bash
docker compose --profile phase8 up -d --wait gcs-emulator
curl -X POST "http://localhost:4443/storage/v1/b?project=local" \
  -H 'Content-Type: application/json' -d '{"name":"phase8-reference-data"}'   # once per volume

export STORAGE_EMULATOR_HOST=http://localhost:4443
export OUTCOME_PREDICTION_MEPS_MIRRORS=gs://phase8-reference-data
python -m outcome_prediction.meps.mirror push && python -m outcome_prediction.meps.mirror verify
```

It is a **test stand-in, not a backup**: its data is a Docker volume on this workspace's host
(`docker compose --profile phase8 down -v` deletes it), and it enforces none of the real
bucket's protections (retention, IAM, public-access prevention). The emulator tests
(`test_meps_mirror_emulator.py`) run whenever `STORAGE_EMULATOR_HOST` is set; CI sets it.

### Later: the real private bucket

`infra/main.tf` is a standalone Terraform root module — private, retention-protected,
multi-region — ready to apply when wanted. It needs GCP credentials, which this repo doesn't
provision.

```bash
cd outcome-prediction-service/infra
terraform init
terraform apply -var project_id=<gcp-project> \
  -var 'writer_members=["user:<you>@<domain>"]' -var 'reader_members=["user:<you>@<domain>"]'
gcloud auth application-default login     # credentials for the Python client
export OUTCOME_PREDICTION_MEPS_MIRRORS=$(terraform output -raw mirror_uri)
python -m outcome_prediction.meps.mirror push && python -m outcome_prediction.meps.mirror verify
```

`lock_retention` stays `false` at first: locking makes the retention policy permanent and can't
be undone. Flip it deliberately once `mirror verify` passes.

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
