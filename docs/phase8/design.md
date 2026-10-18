# Phase 8 Design — Patient Outcome Prediction

Architecture, component breakdown, and the technical sketches `milestone-plan.md` builds
against. Status and requirements live in [`README.md`](./README.md) and [`prd.md`](./prd.md).
The research prototype's method, data facts and reproduction numbers are in
[`prototype-baseline.md`](./prototype-baseline.md); where the two disagree, this document
wins.

## 1. Repo layout

```
outcome-prediction-service/       # NEW (O2) — training pipeline, ETL, scoring API; no conversational logic
  pyproject.toml                  # requires-python >=3.11; scikit-learn pinned exactly (O12)
  README.md                       # service-level detail, per docs/README.md conventions
  src/outcome_prediction/
    meps/
      download.py                 # FR-D1: fetch h{n}dta.zip, extract with zipfile, record SHA-256
      build.py                    # FR-D2: modelling table + label(s)
      dictionary.py               # FR-D3: variable dictionary (not inspect.py: would shadow stdlib `inspect`)
    model/
      __init__.py                 # contract features/order, split, hyperparameters — one definition
      fit.py                      # fit_validation (21–25) / fit_release (all panels); importable by the lab
      train.py                    # FR-M1–M4: evaluate, refit, write artifact + reports
      evaluate.py                 # FR-E1–E6: metrics.json + model_report.md
      artifact.py                 # write/verify artifact dir + SHA-256 manifest (O17); percentiles
    contract.py                   # feature contracts (meps25-v1, later v2), Pydantic, feature order
    etl/
      canonical.py                # the five canonical tables (§7)
      extract/synthea_csv.py      # reproduction/parity harness (O8)
      extract/fhir.py             # NEW vs. the prototype: canonical tables from client/clinical (M6)
      transform/to_contract.py    # canonical → contract rows; training vs scoring mode (§6)
      codelists/                  # M13: versioned ICD-10-CM prefix lists per flag + the SNOMED map (O73)
    fhir/
      risk_assessment.py          # Phase 8's own RiskAssessment/Bundle models + builder (O3, §4)
    api.py                        # FastAPI app (§5)
    tools.py                      # the tool surface outcome-prediction-agent may call (§9)
    tests/                        # repo convention (src/<pkg>/tests); synthetic Stata fixtures built in conftest
      fixtures/                   # tiny committed Synthea sample + synthetic contract rows (no MEPS)
  models/                         # gitignored — built artifacts
  data/                           # gitignored — MEPS cache, Synthea CSV/FHIR outputs

outcome-prediction-lab/           # NEW (O28, O29) — experimentation workbench; research-only deps
  pyproject.toml                  # depends on outcome-prediction-service; MLflow pinned (O30)
  src/outcome_prediction_lab/
    cli.py                        # run / compare / confirm / card / promote (§12)
    targets.py                    # label definitions: outcome × form (O34)
    search.py                     # panel-grouped CV + hyperparameter search on training panels only
    holdout.py                    # ledger check — refuses unlogged test-panel evaluation (O32)
    scorecard.py                  # target scorecard template + ML-criteria fill (O36)
    modelcard.py                  # model card from tracked metadata (O39)
    promote.py                    # writes the promotion record the service requires (O33)
  rounds/NNN-<slug>/              # COMMITTED: README (pre-registration), configs/, report.md, metrics.json, scorecards
  holdout-ledger.md               # COMMITTED, append-only
  notebooks/                      # optional; committed with outputs stripped (O38)
  mlruns/                         # gitignored — local MLflow store (O30)

outcome-prediction-agent/         # NEW (O15) — conversational layer, own top-level package
  src/outcome_prediction_agent/
    agent.py                      # tool-use loop on agent-platform (Phase 6)
    explain.py                    # grounded narration of a RiskAssessment (FR-A2, FR-A3)

client/clinical/                  # extended additively (O9, FR-F1)
e2e/test_outcome_prediction_acceptance.py   # M9
```

Not created: a separate `hosp-risk/` repo, a Makefile, a second devcontainer, a second CI
workflow, `LICENSES.md` (`prd.md` §11 V2, V7). `mcp-agent/`, `triage-service/` and
`gateway/` are untouched.

**Dependency direction.** `outcome-prediction-agent` → `outcome-prediction-service` (HTTP, via
`tools.py`'s contract) and → `agent-platform`. It does **not** import `client/clinical`,
`triage-service`, or any model code. `outcome-prediction-service` → `client/clinical` → the
FHIR server. `outcome-prediction-lab` → `outcome-prediction-service` (imports its `meps`,
`model` and `contract` modules — one implementation, not a fork); the service never imports
the lab (O29). Nothing in earlier phases depends on anything in Phase 8.

## 2. Component responsibilities

| Component | Responsibility | Consumes | Produces |
|---|---|---|---|
| `meps/*` | Acquire, check, and shape MEPS public files | AHRQ URLs | Cached `.dta` + checksums; modelling table; dictionaries |
| `model/train.py` | Fit the GBM and comparison model | Modelling table | Artifact directory (§8) |
| `model/evaluate.py` | Temporal-test metrics | Modelling table, validation model | `metrics.json`, `model_report.md` |
| `contract.py` | Single source of truth for feature names, types, allowed values, order | — | Pydantic models; validators |
| `etl/extract/*` | Source-specific reading only — no feature logic | Synthea CSV, or `client/clinical` | Canonical tables |
| `etl/transform/to_contract.py` | All feature logic, once, for every source | Canonical tables, `as_of`, mode | Contract rows (+ label in training mode) + per-feature provenance |
| `fhir/risk_assessment.py` | Build FHIR output | Scores, explanations, provenance | `RiskAssessment` / `Bundle` |
| `api.py` | HTTP surface, artifact loading, validation | Requests | §5 |
| `tools.py` | The *only* functions the agent can reach | — | §9 |

The prototype's first principle ("one feature contract") is enforced structurally: extractors may
not compute features; only `to_contract.py` does, so a mapping fix lands once for every source.

## 3. The feature contracts — `meps25-v1` (prototype) and `meps-portable-v2` (production)

**Production uses `meps-portable-v2`** (O52), defined once in `outcome_prediction/contract.py`: each
input's FHIR source, reliability tier and MEPS origin; the outcome-observability table (O54); the
ICD-10 chapter map. Below is the prototype's `meps25-v1`, kept because M2's reproduced model uses it.

Carried over unchanged from the prototype (field reference: `prototype-baseline.md` §7): 25
required integer features, MEPS codes,
negatives rejected at the API, and this exact column order:

```
sex, racethx, regiony1, agey1x, inscovy1, povcaty1, ipdisy1, ipngtdy1, ertoty1, obtotvy1,
optotvy1, hhtotdy1, rxtoty1, totexpy1, hibpdx, chddx, angidx, midx, ohrtdx, strkdx, emphdx,
diabdx, arthdx, asthdx, choldx
```

Two interpretation changes, both from review (§11):

- In scoring mode, every `*y1` feature means **the 12 months ending at `as_of`** (O10). The
  names keep MEPS' `y1` suffix because the model was trained on them; the window is documented
  in `contract.py`, not encoded in the name.
- `regiony1 = 0` for an unknown or non-US state, as the contract always said; the prototype's
  default to South (3) is not carried over.

`meps25-v2` (M10) pairs the contract with `label_unplanned_12m`; feature changes from O25/FR-D5
arrive as a new contract version, never as an edit to an existing one. The service serves one
contract version per loaded artifact and rejects requests that name another.

## 4. The `RiskAssessment` (O3)

Phase 8 defines its own Pydantic models — a superset of `triage-service`'s, which has no
numeric probability. Shape:

```
RiskAssessment
  status: final
  subject: Patient/{id}                       # or identifier, for contract-row scoring
  occurrenceDateTime: as_of
  method: CodeableConcept                     # model id, e.g. gbm-meps25-<date>; system http://fhir-agent.local/outcome-prediction/model
  basis: [Encounter/…, Condition/…, MedicationRequest/…, ExplanationOfBenefit/…]   # FR-F4; empty for contract rows
  prediction[0]:
    outcome: SNOMED CT 32485007 "Hospital admission (procedure)"                 # O22, verify in M7
    probabilityDecimal: 0.31
    whenPeriod: { start: as_of, end: as_of + 12 months }
    rationale: "Top factors: age, prior inpatient stay, prescription fills."      # templated from top_reasons
    extension:
      - url: …/comparison-probability   valueDecimal: 0.29                       # FR-S2 / O18
      - url: …/risk-percentile          valueInteger: 94
      - url: …/contract-version         valueString: meps25-v1
      - url: …/top-reasons              valueString: agey1x                        # repeated, ordered
  note[0]: "12-month planning estimate, not a diagnosis. Trained on MEPS public data; …"
  extension:
      - url: …/input-warning            valueString: …                            # out-of-range inputs, defaults applied
```

- **No `qualitativeRisk`** until thresholds are signed off (O24). This is the deliberate
  difference from `triage-service`'s output.
- **Extensions vs. a second `prediction`.** A second `prediction` element would claim a second
  *outcome*; the comparison model predicts the same outcome with a different method, so it is
  an extension on the one prediction. Extension URLs live under
  `http://fhir-agent.local/StructureDefinition/` (the `http://fhir-agent.local/` namespace
  `triage-service` already uses for its code systems); formal `StructureDefinition`s are not written this phase.
- `rationale` text is **templated** from `top_reasons`, never model-generated — same principle
  as Phase 7 R20.
- **Built in M7** (`fhir/risk_assessment.py`). Also carries a generated `text` narrative (the
  probability, percentile and rationale, HTML-escaped) so the resource passes R4 validation with
  no warnings (`dom-6`). Outcome code `32485007` checked against tx.fhir.org (O22).
- **Top reasons (FR-M8, O67)** come from occlusion: the patient is re-scored with each input set
  to a typical MEPS adult's value (`etl/meps_reference.json`); the inputs whose typical value would
  lower the estimate most (≥ 0.5 points, at most 3) are the reasons. Defaulted inputs and
  race/ethnicity (O50) are never reasons.
- Batches return a FHIR `Bundle` of type `collection`.

## 5. API

Matches `triage-service`'s route style (no `/v1` prefix; `/health` at root):

| Method and path | Purpose |
|---|---|
| `GET /health` | Liveness; reports whether an artifact is loaded and verified |
| `GET /model` | Model ID, contract version, training summary, headline metrics, library versions |
| `POST /risk/hospitalization-12m` | Trigger A: `{patient_id, as_of?}` → fetch via `client/clinical`, transform, score → `RiskAssessment` |
| `POST /risk/hospitalization-12m/contract-rows` | Trigger B: `{contract_version, rows: [{patient_ref, features}]}` (1–1,000) → `Bundle` |

Internal-only, no Kong route (O14). **Port 8005** (8000–8004 are taken; O68). Compose: the
`outcome-prediction` service in the `phase8` profile, depending on `fhir`, with
`outcome-prediction-service/models/` mounted read-only — artifacts never enter the image (O17).

Built in M7 (`api.py`). The patient endpoint reads the 400 days before `as_of` (window + margin)
plus all conditions, through the M6 extractor; a patient who isn't an adult alive on `as_of` gets
422, not an estimate; FHIR read failures are 502. Contract rows: exactly the 25 features, MEPS
codes, no negatives (422 lists every problem); `regiony1 = 0` is accepted with a warning.
Measured (M7, compose stack): one contract row in **26 ms median / 46 ms p95** over HTTP; a
1,000-row batch in 0.98 s; one Synthea patient ~220 ms, dominated by FHIR reads.

## 6. Training mode vs scoring mode (O10)

| | Training mode | Scoring mode |
|---|---|---|
| Who uses it | MEPS build; Synthea CSV reproduction | The API; the FHIR extractor |
| Feature window | Calendar year Y (reproduction) | 12 months ending `as_of` |
| Label | Year Y+1 | None — never computed |
| May read records after the window | Yes, to build the label only | **No — filtered at the extractor boundary** |

The filter is applied once, in the extractor, before any transform runs: canonical tables in
scoring mode contain nothing dated after `as_of`. Records that *span* `as_of` (a medication
active across it, an inpatient stay admitted before and discharged after) are truncated at
`as_of` — never extrapolated from their eventual end.

**Built in M4** (`etl/canonical.py` `as_of_view`, `etl/transform/to_contract.py`): training mode
*is* scoring mode with `as_of` = 31 December of year 1, plus the label — one feature code path, so
the two can't drift. Values only final when a record ends become unknown while it runs (O62):

| Running at `as_of` | Counted as |
|---|---|
| Prescription (no stop yet, or stops later) | Fills elapsed inside the window at the fill rate of the same person's last *ended* record of the same drug, else one a month; cost = fills × per-fill price (known at the start) |
| Inpatient stay | One stay; nights up to `as_of`; no cost (the claim isn't final) |
| Coverage | Counts if it overlaps the window |
| Death after `as_of` | Unknown — the person is alive at `as_of` |

**Mandatory test** (planned by the prototype, now load-bearing): for a fixture patient,
add and remove records dated after `as_of` — including a long-running prescription whose stop
date and dispense count are only known later — and assert identical contract rows.

## 7. Canonical model and the FHIR mapping (O21 → validated in M5–M6: O64, O65)

Canonical tables carried over from the prototype's design (`person`, `coverage`,
`encounter`, `condition`, `medication_fill`), with one added column on each: `source_ref` (the
FHIR `Type/id`, or the CSV row ID) — what makes FR-F4's `basis` possible.

The FHIR extractor (`etl/extract/fhir.py`, built in M6) — each rule **checked against Synthea
v4.0.0 FHIR on HAPI v7.2.0**, the same run's CSV as the reference (O65), as Phase 7 does for
RxNav (R11):

| Canonical | FHIR source (via `client/clinical`) | Found in Synthea v4.0.0 | Rule |
|---|---|---|---|
| `person` | `get_demographics`: Patient gender, birthDate, deceasedDateTime, address.state, US Core race / ethnicity | All present; state is a postal code; **no income** | State code → name; `povcaty1` defaulted to 4 with a warning (O66) |
| `encounter` | `get_encounters`: class + period; cost from `get_care_costs` | Matches CSV one-to-one (ID, start). Class folds CSV classes: AMB = ambulatory + wellness + **outpatient** + urgent care; IMP = inpatient + **SNF**; HH = home + **hospice**. Neither `type` nor place of service separates them | Counted as office / inpatient / home health. Cost = billed total of the encounter's claims (equals the CSV cost for all 4,307) |
| `condition` | `get_condition_history` (paged — 6% of people have > 100) | Onset matches; description = SNOMED display | Onset, else recorded date; diagnosis flags from the versioned code lists (`etl/codelists`, O73) |
| `medication_fill` | `get_medication_dispenses`; else `get_care_costs` pharmacy claims | **No `MedicationDispense`, no `dispenseRequest`, no stop date**; one pharmacy claim per prescription | One fill per dispense; else one fill per pharmacy claim, priced at its billed amount, with a note. Fills undercount by ~6× on Synthea |
| `coverage` | `get_coverage`; else the payer on each claim | **No `Coverage`** | Claim payer for the claim's service period; payer name → ownership (Medicare / Medicaid / Dual Eligible → government; `NO_INSURANCE`; else private) |

**Parity (FR-F3), year 1 = 2023, 20 adults, same run both ways:** 19 of 26 columns identical
(demographics, insurance, every stay and ER count, all 11 diagnosis flags); every other
difference explained *and verified* by `etl/parity.py` — income default (`povcaty1`), office +
outpatient merged (their sum is equal), hospice as home health, a year-2 SNF stay in the label,
prescription fills and costs from claims (the encounter part of spending is equal). Same for
year 1 = 2022.

Synthea runs for Phase 8 (O11) overrideSynthea runs for Phase 8 (O11) override `exporter.csv.export=true` and
`exporter.years_of_history` on the command line so both formats and enough history come from
one run; the shared `data/synthea/synthea.properties` is not edited.

## 8. Model artifacts (O17, O18)

```
models/gbm-meps25-v1-<training-table sha256[:12]>/   # deterministic ID; never overwritten
  model.joblib          # GBM
  comparison.joblib     # logistic regression (O18)
  metadata.json         # features + order, categoricals, contract version, training panels,
                        # row/event counts, data checksums, library versions, git commit, metrics,
                        # training-population score distribution (for percentiles)
  MANIFEST.sha256       # verified before any deserialisation; mismatch → refuse to start
  PROMOTION.json        # from M12: round, decision ID, target/form, contract version, model card hash (O33)
```

From M12, the service also refuses an artifact with no `PROMOTION.json` naming a `decisions.md`
entry. The `meps25-v1` reproduction model is promoted by decision O2/O3 itself, so M7 can run
before the lab's promotion step exists; M12 retrofits its record.

Never committed. CI trains a throwaway model on a committed synthetic contract-row fixture so
service tests run without MEPS; MEPS-dependent tests (M1–M2 reproduction) get the real data
from the `meps_cache` fixture, which populates any missing panel (O44 — superseding the original
self-skip). Percentiles are computed against
the training population this phase; per-customer percentiles arrive with recalibration
(Phase 8b).

## 9. The agent's tool contract (O15)

`tools.py` (in `outcome-prediction-service`) defines exactly what `outcome-prediction-agent`
can call:

| Tool | What it does | What it cannot do |
|---|---|---|
| `find_patient(name)` | Candidate search via `client/clinical`; returns ID, name, birth date | Cannot auto-pick among several candidates — ambiguity goes back to the human |
| `get_hospitalization_risk(patient_id, as_of?)` | Calls the scoring path; returns the `RiskAssessment` | Read-only; no parameters touch features or the model |
| `get_model_card()` | Returns `/model` metadata for "how was this built?" questions | Read-only |

**There is no tool that accepts feature values, a threshold, or a model choice.** The agent
can't "re-score with a different age" or "flag anyone over 20%", because those would put
clinical logic in the agent. `explain.py`'s system prompt allows only facts present in the
returned `RiskAssessment` (FR-A2), plus the fixed planning-aid statement (FR-A3); the
agent-turn output gate follows `agent-platform`'s `output_gate.py` pattern.

**Built in M8 (O69, O70).** The service publishes the tools (`GET /agent-tools`, `POST
/agent-tools/{name}`); the agent offers the model exactly those. Stricter than the paragraph above:
the model never writes the reply. `explain.py` builds it from the tool output, a turn ends on one
of eight outcomes (`ESTIMATE`, `MODEL_CARD`, `CHOOSE_PATIENT`, `NOT_FOUND`, `NO_ESTIMATE`,
`NEEDS_PATIENT`, `OUT_OF_SCOPE`, `UNAVAILABLE`), and `explain.grounded` withholds any reply with a
number the service didn't return.

## 10. Testing strategy

Carried over from the prototype's test plan, mapped to this repo:

| Level | What | Where it runs |
|---|---|---|
| Unit | Every mapping rule, incl. the regression: "Abnormal findings diagnostic imaging heart+coronary circulat" must not set `chddx` | `phase8` CI job |
| Contract | Pydantic rejects missing fields, wrong types, out-of-range codes, wrong contract version | CI |
| Leakage | §6 test, both extractors | CI |
| Parity | FR-F3, on a small committed Synthea CSV + FHIR fixture from one run | CI |
| Artifact | Tampered manifest → service refuses to start | CI |
| Data | Per-panel row counts equal `prototype-baseline.md` §3.1 | CI and local — data populated on demand (O44) |
| Model | Test AUROC within tolerance; metadata has the 25 features in order | CI and local — data populated on demand (O44) |
| Agent | Grounding + adversarial ("adjust the score", "call it high risk") | CI with the self-hosted model, same as Phase 6's adversarial suite |
| End to end | `e2e/test_outcome_prediction_acceptance.py` against the `phase8` stack — brings up what's missing (O71) | Local, like the other e2e suites |

The root `pytest.ini` gains the new test paths; the Phase 1 independence job is unchanged.

## 11. Prototype defects found in review

Recorded here so M4–M7 fix them **after** the reproduction (O6), each with a test:

1. **Prescription-fill leakage** (prototype Synthea ETL, `prototype-baseline.md` §6.3): a missing medication `STOP` is filled with
   the end of year 2, and `DISPENSES` (a lifetime total known only later) is prorated across
   that span — so year-1 `rxtoty1` and `totexpy1` depend on future data. Fixed by §6.
   **Fixed in M4**; the leakage test fails on the reproduced code (`prototype_training_rows`).
2. **Comparison model not saved** (prototype training step): only the GBM is pickled, yet FR-S2 needs
   both scores. Fixed by O18.
3. **Unknown state → South** (prototype Synthea ETL): contradicts the contract's `0 if unknown`.
   Fixed in `to_contract.py`; no effect on the Arizona reproduction run. **Fixed in M4.**
4. **Categorical handling differs between training and scoring**: training clips categoricals
   at 0; the prototype's scoring step doesn't. Moot once the API rejects negatives, but `to_contract.py` applies
   one rule for both modes. **Fixed in M4** (`encode_categoricals`).
5. **Reported metrics belong to a different model object**: the release model is refit on all
   panels, so its own held-out performance is unknown. `metadata.json` says so explicitly and
   carries the validation model's metrics labelled as such.
6. **Diagnosis-column resolution by prefix** (prototype dataset build, `prototype-baseline.md` §4.1): "first column starting
   with the prefix and containing `Y1`" is fragile across panels. M1 logs the resolved column
   per panel per flag into the build report, so a silent mismatch is visible. **M1 finding:**
   every flag resolves to exactly one candidate in all seven panels; the only drift is diabetes,
   `DIABDXY1` in panels 21–22 and `DIABDXY1_M18` from panel 23 (the 2018 question change). A
   test fails if a future file introduces a second candidate.

## 12. The experimentation workbench — `outcome-prediction-lab` (O28–O39)

Built once in M3; used by every round under [`experimentation-protocol.md`](./experimentation-protocol.md).

**What it adds over the service's own training code.** The service trains *the* served model.
The lab trains *many* candidates across outcome × form (O34) — label definitions in
`targets.py`, feature sets as contract versions, model families and search spaces from configs
— and compares them under one evaluation discipline.

**CLI surface** (`cli.py`):

| Command | Does | Guard |
|---|---|---|
| `run <round> <config>` | Train + panel-grouped CV on training panels; log to MLflow (optional) | Refuses configs with keys naming panels or splits |
| `compare <round>` | Cross-validated comparison report across a round's runs, incl. subgroups and calibration | — |
| `confirm <round> <candidate>` | Evaluate one candidate on the test panels | Refuses without a matching `holdout-ledger.md` entry (O32) |
| `card <round> <config>` | Generate a model card (O39) | — |
| `scorecard <round> <config>` | Target scorecard (O36): ML criteria filled, person-scored criteria marked as owed | — |
| `explain <round> <config>` | Self-explanatory per-patient narratives (O50) | Never shows outcomes |
| `fairness <round> <config>` | Subgroup report on the test panels (race/ethnicity, insurance, sex, age band), added to the model card (O57) | Refuses without a `<config>:fairness` ledger entry and a confirmed model |
| `promote <run> --decision O<n>` | Write `PROMOTION.json` into a service artifact | Refuses unless the decision ID exists in `decisions.md` and a model card is present (O33) |

**Prediction forms and evaluation** (O34):

| Form | Example | Primary metrics | Served as |
|---|---|---|---|
| Event probability | any stay, unplanned stay, any ED visit, high-cost member | AUROC, AUPRC, Brier, calibration, top-k PPV | `RiskAssessment.prediction.probabilityDecimal` |
| Expected count | ED visits, hospital nights | Poisson deviance, MAE, calibration of means by decile | Needs an O35 decision |
| Cost | next-year spending | MAE on log scale, top-decile capture | Needs an O35 decision |
| Ordinal tier | none / one / repeated stays | Ordinal-aware metrics | Needs an O35 decision |

Label candidates are read from MEPS year-2 variables only after `dictionary.py` confirms their
names and codes in each panel's file (`prototype-baseline.md` §3, "never guess").

**What the lab deliberately is not.** No feature store, pipeline orchestrator, or hosted
tracking server — a shared MLflow server is a Phase 8b question. No customer data. No
automatic promotion.

## 13. Data provenance and preservation (O41, O42)

```
outcome-prediction-service/
  meps-manifest.json          # COMMITTED: per file — URLs, SHA-256 of zip, .dta, doc page, codebook
  infra/main.tf               # private GCS archive bucket (standalone root module; deferred, not applied)
  src/outcome_prediction/meps/
    manifest.py               # `snapshot`: record originals; `--accept-change` to adopt a re-release
    mirror.py                 # write-once, content-addressed mirrors: gs:// and file://; push / verify
    download.py               # fetch: archive -> AHRQ -> mirrors, manifest-verified
  data/raw/meps/archive/      # gitignored: original zips + docs, the source for `mirror push`
```

**Fetch order** for a manifested file: the original zip in the local archive → AHRQ → each mirror
in `OUTCOME_PREDICTION_MEPS_MIRRORS`. Every candidate is hashed against the manifest; a mismatch
is rejected and recorded in the error, never cached. Unmanifested files (future event files
before they're added) keep the M1 behaviour.

**Mirror layout:** `meps/sha256/<sha256>/<original name>`. Content-addressed keys mean a
re-release lands beside the original rather than replacing it, and `put` refuses to overwrite.

**The bucket** (`infra/main.tf`): private (uniform access, public access prevention enforced),
retention policy (default 10 years, lock is a separate irreversible step), 90-day soft delete,
multi-region `US` by default, `prevent_destroy`, writers create-only. **Deferred** (O41, O43):
until it's wanted, the compose service `gcs-emulator` (fake-gcs-server, profile `phase8`) stands
in for testing — the real client reaches it via `STORAGE_EMULATOR_HOST`, it honours the write-once
precondition (412 on a second create), and CI runs the `gs://` tests against it. It is not a
backup and enforces none of the bucket's protections; preservation is the repo owner's
off-workspace `file://` copy. Verified so far: Terraform
`validate`/`fmt` clean; a `file://` mirror of all 21 originals (121 MB) pushed and verified, and
— with AHRQ simulated as unreachable in a fresh workspace — all seven panels restored from it
and the M1 table rebuilt byte-identical (sha256 `950d8be12078…`, the M2 model ID). The same
end-to-end run through `gs://phase8-reference-data` on the emulator: 21 uploaded, a second push
all "present" (write-once), verify clean, persistence across an emulator restart, AHRQ-down
restore and byte-identical rebuild.

