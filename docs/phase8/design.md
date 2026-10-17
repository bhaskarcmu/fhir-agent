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
      inspect.py                  # FR-D3: variable dictionary
    model/
      train.py                    # FR-M1–M4: validation model (21–25) + release model (all panels)
      evaluate.py                 # FR-E1–E6: metrics.json + model_report.md
      artifact.py                 # write/verify artifact dir + SHA-256 manifest (O17)
    contract.py                   # feature contracts (meps25-v1, later v2), Pydantic, feature order
    etl/
      canonical.py                # the five canonical tables (§7)
      extract/synthea_csv.py      # reproduction/parity harness (O8)
      extract/fhir.py             # NEW vs. the prototype: canonical tables from client/clinical (M5)
      transform/to_contract.py    # canonical → contract rows; training vs scoring mode (§6)
      codelists/                  # M11: versioned ICD-10-CM 3-char lists per flag
    fhir/
      risk_assessment.py          # Phase 8's own RiskAssessment/Bundle models + builder (O3, §4)
    api.py                        # FastAPI app (§5)
    tools.py                      # the tool surface outcome-prediction-agent may call (§9)
  tests/
    fixtures/                     # tiny committed Synthea sample + synthetic contract rows (no MEPS)
  models/                         # gitignored — built artifacts
  data/                           # gitignored — MEPS cache, Synthea CSV/FHIR outputs

outcome-prediction-agent/         # NEW (O15) — conversational layer, own top-level package
  src/outcome_prediction_agent/
    agent.py                      # tool-use loop on agent-platform (Phase 6)
    explain.py                    # grounded narration of a RiskAssessment (FR-A2, FR-A3)

client/clinical/                  # extended additively (O9, FR-F1)
e2e/test_outcome_prediction_acceptance.py   # M8
```

Not created: a separate `hosp-risk/` repo, a Makefile, a second devcontainer, a second CI
workflow, `LICENSES.md` (`prd.md` §11 V2, V7). `mcp-agent/`, `triage-service/` and
`gateway/` are untouched.

**Dependency direction.** `outcome-prediction-agent` → `outcome-prediction-service` (HTTP, via
`tools.py`'s contract) and → `agent-platform`. It does **not** import `client/clinical`,
`triage-service`, or any model code. `outcome-prediction-service` → `client/clinical` → the
FHIR server. Nothing in earlier phases depends on anything in Phase 8.

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

## 3. The feature contract `meps25-v1`

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

`meps25-v2` (M9) pairs the contract with `label_unplanned_12m`; feature changes from O25/FR-D5
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
    outcome: SNOMED CT 32485007 "Hospital admission (procedure)"                 # O22, verify in M6
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
- Batches return a FHIR `Bundle` of type `collection`.

## 5. API

Matches `triage-service`'s route style (no `/v1` prefix; `/health` at root):

| Method and path | Purpose |
|---|---|
| `GET /health` | Liveness; reports whether an artifact is loaded and verified |
| `GET /model` | Model ID, contract version, training summary, headline metrics, library versions |
| `POST /risk/hospitalization-12m` | Trigger A: `{patient_id, as_of?}` → fetch via `client/clinical`, transform, score → `RiskAssessment` |
| `POST /risk/hospitalization-12m/contract-rows` | Trigger B: `{contract_version, rows: [{patient_ref, features}]}` (1–1,000) → `Bundle` |

Internal-only, no Kong route (O14). Port: the next free one in the `800x` range, assigned in M6.
Compose: a `phase8` profile service that depends on `fhir`, plus a read-only volume for the
artifact directory.

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

**Mandatory test** (planned by the prototype, now load-bearing): for a fixture patient,
add and remove records dated after `as_of` — including a long-running prescription whose stop
date and dispense count are only known later — and assert identical contract rows.

## 7. Canonical model and the FHIR mapping sketch (O21 — unvalidated)

Canonical tables carried over from the prototype's design (`person`, `coverage`,
`encounter`, `condition`, `medication_fill`), with one added column on each: `source_ref` (the
FHIR `Type/id`, or the CSV row ID) — what makes FR-F4's `basis` possible.

The FHIR extractor's sketch — **every row to be confirmed against real Synthea v4.0.0 output in
M5**, recording what was found, as Phase 7 does for RxNav (R11):

| Canonical | FHIR source (via `client/clinical`) | Known risk |
|---|---|---|
| `person` | `Patient` (gender, birthDate, deceased, address.state; race/ethnicity from US Core extensions) | Income and household size absent → `povcaty1` defaulted with a warning; ZIP-level income is a later contract version |
| `encounter` | `Encounter.class` + `period` | Synthea maps several CSV classes to `AMB`; office vs hospital-outpatient (`obtotvy1` vs `optotvy1`) may need `Encounter.type`/`serviceType`, or a documented merge |
| `condition` | `Condition` code (SNOMED) + onset | Description regex (prototype) until M11's code lists |
| `medication_fill` | `MedicationDispense` if present; else `MedicationRequest` + `dispenseRequest`, truncated at `as_of` | Synthea's FHIR may not carry a dispense count; the fallback rule is decided and documented in M5 |
| `coverage` | `Coverage`, or `ExplanationOfBenefit.insurance` | Which one Synthea v4.0.0 populates is unverified |
| cost (`totexpy1`) | `ExplanationOfBenefit` payment/total, else `Claim.total` | Charges vs MEPS payments (O25) |

Synthea runs for Phase 8 (O11) override `exporter.csv.export=true` and
`exporter.years_of_history` on the command line so both formats and enough history come from
one run; the shared `data/synthea/synthea.properties` is not edited.

## 8. Model artifacts (O17, O18)

```
models/<model_id>/
  model.joblib          # GBM
  comparison.joblib     # logistic regression (O18)
  metadata.json         # features + order, categoricals, contract version, training panels,
                        # row/event counts, data checksums, library versions, git commit, metrics,
                        # training-population score distribution (for percentiles)
  MANIFEST.sha256       # verified before any deserialisation; mismatch → refuse to start
```

Never committed. CI trains a throwaway model on a committed synthetic contract-row fixture so
service tests run without MEPS; MEPS-dependent tests (M1–M2 reproduction) self-skip when the
cache is absent, like `provider-registry-service`'s DB tests. Percentiles are computed against
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

## 10. Testing strategy

Carried over from the prototype's test plan, mapped to this repo:

| Level | What | Where it runs |
|---|---|---|
| Unit | Every mapping rule, incl. the regression: "Abnormal findings diagnostic imaging heart+coronary circulat" must not set `chddx` | `phase8` CI job |
| Contract | Pydantic rejects missing fields, wrong types, out-of-range codes, wrong contract version | CI |
| Leakage | §6 test, both extractors | CI |
| Parity | FR-F3, on a small committed Synthea CSV + FHIR fixture from one run | CI |
| Artifact | Tampered manifest → service refuses to start | CI |
| Data | Per-panel row counts equal `prototype-baseline.md` §3.1 | Local; self-skips without MEPS cache |
| Model | Test AUROC within tolerance; metadata has the 25 features in order | Local; self-skips |
| Agent | Grounding + adversarial ("adjust the score", "call it high risk") | CI with the self-hosted model, same as Phase 6's adversarial suite |
| End to end | `e2e/test_outcome_prediction_acceptance.py` against the `phase8` stack | Local, like the other e2e suites |

The root `pytest.ini` gains the new test paths; the Phase 1 independence job is unchanged.

## 11. Prototype defects found in review

Recorded here so M3–M6 fix them **after** the reproduction (O6), each with a test:

1. **Prescription-fill leakage** (prototype Synthea ETL, `prototype-baseline.md` §6.3): a missing medication `STOP` is filled with
   the end of year 2, and `DISPENSES` (a lifetime total known only later) is prorated across
   that span — so year-1 `rxtoty1` and `totexpy1` depend on future data. Fixed by §6.
2. **Comparison model not saved** (prototype training step): only the GBM is pickled, yet FR-S2 needs
   both scores. Fixed by O18.
3. **Unknown state → South** (prototype Synthea ETL): contradicts the contract's `0 if unknown`.
   Fixed in `to_contract.py`; no effect on the Arizona reproduction run.
4. **Categorical handling differs between training and scoring**: training clips categoricals
   at 0; the prototype's scoring step doesn't. Moot once the API rejects negatives, but `to_contract.py` applies
   one rule for both modes.
5. **Reported metrics belong to a different model object**: the release model is refit on all
   panels, so its own held-out performance is unknown. `metadata.json` says so explicitly and
   carries the validation model's metrics labelled as such.
6. **Diagnosis-column resolution by prefix** (prototype dataset build, `prototype-baseline.md` §4.1): "first column starting
   with the prefix and containing `Y1`" is fragile across panels. M1 logs the resolved column
   per panel per flag into the build report, so a silent mismatch is visible.
