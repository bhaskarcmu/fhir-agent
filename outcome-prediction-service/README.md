# outcome-prediction-service

Phase 8's machine-learning service: builds the training data from AHRQ MEPS, and (from later
milestones) trains, evaluates and serves the 12-month hospitalization model as FHIR
`RiskAssessment`s. Planning, decisions and status: [`docs/phase8/`](../docs/phase8/README.md).

**Built so far:** M1 (MEPS acquisition, dataset build, variable dictionary), M2 (training,
evaluation, model artifact), M4 (Synthea CSV harness, `as_of` scoring mode, leakage test) and M6 (FHIR
extractor, CSV ↔ FHIR parity, data-quality report) and M7 (the scoring API).

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

## Synthea harness (M4)

A mechanical pipeline check, **never evidence of accuracy**: simulated patients flow through the same
ETL and model as real ones.

```bash
# Synthea v4.0.0 (downloaded once, SHA-256 verified), seed 42, 3,000 Arizona adults, CSV only (~15 min)
python -m outcome_prediction.etl.synthea generate
#    -> data/raw/synthea/az-3000-s42/csv/
# Contract rows for year 1 = 2023 (+ 2024 label), sanity checks, pipeline-check score with M2's artifact
python -m outcome_prediction.etl.synthea rows --year 2023
# Demo patients (5 requested, seed 42) into a FHIR server — idempotent; generates their FHIR once (M9)
python -m outcome_prediction.etl.synthea seed --fhir http://localhost:8080/fhir
#    -> data/processed/synthea_rows_2023.csv, data/reports/synthea_2023.json
```

Code path: `etl/extract/synthea_csv.py` (reading only) → `etl/canonical.py` (five canonical tables;
`as_of_view` is the scoring-mode boundary) → `etl/transform/to_contract.py` (`scoring_rows(canon,
as_of)`; `training_rows(canon, year)` = scoring rows as of 31 December + the label). The prototype's
mapping is kept as `prototype_training_rows` — reference only, defects marked — so the leakage test
can show it catches them (`docs/phase8/design.md` §6, §11; decisions O61, O62).

## The scoring API (M7)

12-month hospitalization risk as a FHIR R4 `RiskAssessment` (design `docs/phase8/design.md` §4–§5).
Internal only — no Kong route (O14).

```bash
pip install -e client/clinical -e "outcome-prediction-service[api]"
FHIR_GATEWAY_URL=http://localhost:8080/fhir uvicorn outcome_prediction.api:app --port 8005
# or: docker compose --profile phase8 up --build -d fhir outcome-prediction

curl localhost:8005/health                                       # artifact loaded and verified
curl localhost:8005/model                                        # model card facts, labelled metrics
curl -X POST localhost:8005/risk/hospitalization-12m \
     -H 'Content-Type: application/json' -d '{"patient_id": "3208", "as_of": "2024-12-31"}'
curl -X POST localhost:8005/risk/hospitalization-12m/contract-rows \
     -H 'Content-Type: application/json' -d '{"contract_version": "meps25-v1", "rows": [...]}'   # -> Bundle
curl localhost:8005/agent-tools                                  # the agent's only tools (tools.py, O70)
```

The artifact is `OUTCOME_PREDICTION_ARTIFACT`, else the newest `models/gbm-meps25-v1-*`; it is
verified against its manifest at startup and the service won't start on a mismatch. Each
assessment carries the probability, the comparison model's probability, the training-population
percentile, up to three plain-language reasons (O67), the records used (`basis`) and any input
warnings. No high / moderate / low band until thresholds are signed off (O24).

## FHIR path, parity and data quality (M6)

```bash
pip install -e client/clinical                    # the FHIR extractor reads through it
# CSV <-> FHIR parity: the same Synthea run, both extractors (needs a FHIR server loaded with that run)
python -m outcome_prediction.etl.parity --csv <run>/csv --fhir http://localhost:8090/fhir --year 2023
#    -> data/reports/parity_2023.{md,json}         (fails unless every difference is explained)
# Data-quality report vs MEPS (missing / impossible values, unknown codes, drift)
python -m outcome_prediction.etl.quality csv <run>/csv --year 2023
python -m outcome_prediction.etl.quality fhir http://localhost:8090/fhir --year 2023
python -m outcome_prediction.etl.quality reference  # rebuild meps_reference.json (aggregates only) from MEPS
```

`etl/extract/fhir.py` maps FHIR to the same canonical tables as the CSV reader; the rules, and
what Synthea's FHIR does and doesn't carry, are in `docs/phase8/design.md` §7 (O65).
`to_contract.scoring_rows(..., explain=True)` also returns each feature's source records (the
`RiskAssessment.basis`, FR-F4) and the defaults applied.

## Diagnosis code lists (M13)

Each diagnosis flag comes from a versioned ICD-10-CM list in `etl/codelists/<flag>.json` — marked
**unreviewed** until a clinical owner signs off (decisions O27, O73). SNOMED CT conditions are mapped
with Synthea v4.0.0's map (`etl/codelists/maps/`).

```bash
python -m outcome_prediction.etl.codelists check       # every entry exists in CDC ICD-10-CM FY2026
python -m outcome_prediction.etl.codelists build-map   # re-extract the SNOMED map from the pinned jar
```

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

Unit tests use tiny synthetic Stata files, a synthetic modelling table and a committed Synthea
fixture (`tests/fixtures/synthea_csv/`: 7 adults from a 20-patient v4.0.0 run, seed 42, columns
trimmed to what the extractor reads — no Java or download needed). Tests that need
real data or the GCS emulator **populate what's missing instead of skipping**
(`docs/phase8/decisions.md` O44), whether you run one test, a file, or everything:

- the MEPS cache: any missing panel is fetched (local archive → AHRQ → configured mirrors,
  verified against `meps-manifest.json`); a cached file that doesn't match is moved aside as
  `*.mismatch-<time>` and re-fetched, with a warning;
- the GCS emulator: a reachable `STORAGE_EMULATOR_HOST` is reused, otherwise a
  `fake-gcs-server` container is started for the session (needs Docker) and removed after;
- the emulator bucket `phase8-reference-data`: created if absent, topped up if incomplete.

If something can't be obtained, the test **fails** with the reason. To work offline, set
`OUTCOME_PREDICTION_TESTS_OFFLINE=1` — the dependent tests then skip instead. CI runs every
test and caches the original zips, keyed on the manifest.

## Data and licence notes

MEPS public-use files are free US government data; whether their terms allow commercial use
of trained models is unconfirmed (`docs/phase8/decisions.md` O23,
[`data/reference/README.md`](../data/reference/README.md)). No PHI is ever used here.

Synthea (Apache 2.0, MITRE) generates synthetic patients only; the committed fixture is its output,
with identifier-like columns (names, SSNs, addresses) dropped.
