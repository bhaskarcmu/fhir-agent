# outcome-prediction-lab

Phase 8's experimentation workbench: research **rounds** that explore what to predict and how,
without eroding the test set. Runbook: [`docs/phase8/experimentation-protocol.md`](../docs/phase8/experimentation-protocol.md).
Decisions: `docs/phase8/decisions.md` O28–O51.

Imports `outcome-prediction-service` (dataset build, model definitions, MEPS download) — one
implementation, not a fork (O29). Nothing in the service imports the lab.

## Install

Needs **Python 3.12+** (`shap` ≥ 0.52 requires it); the service it imports still supports 3.11.
CI runs the lab in its own `phase8 lab (python 3.12)` job.

```bash
python -m pip install -e "outcome-prediction-service[dev]" -e "outcome-prediction-lab[dev]"
python -m pip install -e "outcome-prediction-lab[tracking]"   # optional: MLflow (local SQLite store)
```

## The command line

```bash
outcome-prediction-lab run        <round> <config> [...]          # CV on training panels only
outcome-prediction-lab compare    <round>                         # table of a round's runs
outcome-prediction-lab confirm    <round> <config> --record "why" # ONE logged look at test panels 26–27
outcome-prediction-lab card       <round> <config>                # model card
outcome-prediction-lab scorecard  <round> <config> [--criteria person.json]
outcome-prediction-lab promote    <round> <config> --decision O<n>
outcome-prediction-lab explain    <round> <config> --patient ID | --sample N [--write] | --all
outcome-prediction-lab drug-names <round>                         # drug-name text experiment
outcome-prediction-lab notebooks-check | notebooks-strip <file>
```

A config (`rounds/<round>/configs/<name>.json`) says only *what* to model:

```json
{"name": "ref-codes-lsa", "label": "admit_nonobstetric_y2", "task": "binary",
 "features": "portable+knowledge", "model": "gbm", "params": "tuned", "text": ["lsa"],
 "baseline_inputs": ["agey1x", "ipdisy1"]}
```

`text` combines representations: `lsa` / `ae` / `dae` (code tokens), `desc_lsa` (code descriptions as
words), `drug_char_lsa` (drug names as character n-grams); sparse `tfidf` / `desc_tfidf` /
`drug_char_tfidf` for `"model": "lr"`. Keys naming panels or splits are refused.

## Rounds

| Round | Question | Report |
|---|---|---|
| 001 | What to predict, and how (prototype objective, 7 new targets, concepts) | [`rounds/001-what-and-how/report.md`](./rounds/001-what-and-how/report.md) |
| 002 | Text on code descriptions and drug names; self-explanatory narratives; the CLI | [`rounds/002-text-and-explanations/report.md`](./rounds/002-text-and-explanations/report.md) |

Round 001 predates the CLI and runs as a script (`python -m outcome_prediction_lab.round_001 <stage>`);
round 002 onwards use the CLI.

## What's in the package

| Module | What it does |
|---|---|
| `cli.py` | The command line |
| `runs.py` | Config-driven runs, compare, confirm (ledger-guarded), model cards, scorecards, promotion |
| `data.py` | The lab table: 56,360 adults from 28 MEPS files; person-ID normalisation; code "documents"; drug names; year-2 labels |
| `vocabulary.py` | Plain-language names for every ICD-10, CCSR and drug-class code (O49) |
| `knowledge.py` | Hospital Frailty Risk Score and Charlson/Elixhauser tables, vendored from comorbidipy (MIT) |
| `features.py` | Honest missing-value encoding; feature sets; pipelines and text representations, refit per fold |
| `evaluate.py` | Leave-one-panel-out CV; metrics; paired bootstrap |
| `holdout.py` | The ledger and its guard |
| `narrate.py` | Self-explanatory per-patient narratives with comparison groups (O50) |
| `explain.py` | Round 001's SHAP importance, surrogate tree, value-of-information items |
| `drugnames.py` | Character n-grams vs words for mapping messy drug names to classes |
| `notebooks.py` | Notebook output check and strip (O38) |
| `round_001.py` | Round 001's stages |

## Data

The lab reads MEPS through `outcome_prediction.meps.download`, so every file is verified against
the committed manifest and fetched from the archive, AHRQ or a mirror as needed. Its table is
cached at `outcome-prediction-service/data/processed/lab_table.joblib` (gitignored).

## Tests

```bash
pytest outcome-prediction-lab/src/outcome_prediction_lab/tests -q
```

Unit tests only (synthetic data): ledger guard, ID normalisation, targets, knowledge scores, honest
encoding, autoencoder, bootstrap, vocabulary parsing, narratives, the runs engine end to end
(config guard, CV, confirm guard, card, scorecard, promotion refusals), notebook check.
