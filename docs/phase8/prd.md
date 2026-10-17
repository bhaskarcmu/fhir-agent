# Phase 8 PRD — Patient Outcome Prediction (12-Month Hospitalization Risk)

**Status:** DRAFT — first planning pass. Synthesised from a hand-off of a research prototype
built in an earlier session (restated in `prototype-baseline.md`; the raw hand-off documents
are not kept in the repo — O5) and reconciled with this repo's conventions. No code written
yet.
**Companion doc:** [`design.md`](./design.md) — repo layout, components, the feature contract,
the `RiskAssessment` shape, scoring-mode semantics, the FHIR mapping sketch, artifacts, the
agent's tool contract, testing, and the prototype defects found in review.
**Milestone plan:** [`milestone-plan.md`](./milestone-plan.md) — M1–M11, kept as its own
document, same convention as Phase 6 (`phase6/decisions.md` H23) and Phase 7.
**Decision index:** [`decisions.md`](./decisions.md) — `O1`–`O27`.
**Prototype baseline:** [`prototype-baseline.md`](./prototype-baseline.md) — data choices,
MEPS/Synthea facts, the prototype's method and the numbers to reproduce. §11 below lists every
deviation from the prototype's plan.
**Extends:** Phase 1 (`fhir-service`, `client/clinical` — extended additively), Phase 6
(`agent-platform` — the new agent is built on it). Reads the Synthea data pipeline already in
`data/`.
**Owner:** repo owner.

---

## 1. Problem statement

Primary-care teams in value-based contracts — especially risk-bearing practices serving
Medicare patients — are paid to keep patients out of hospital. They need a ranked list of who
is most likely to be admitted in the next year, with reasons, so care managers can reach out
early. Commercial risk scores exist but are proprietary, expensive, and trained on data nobody
can inspect.

Phase 8 adds the platform's first **machine-learned** clinical capability: an inspectable,
reproducible model, trained only on free, open, US data, that estimates each adult's
probability of at least one inpatient stay in the next 12 months — and returns it the way the
rest of this platform returns clinical judgements, as a FHIR `RiskAssessment` (O3).

It is a different kind of clinical logic from everything before it. `triage-service`'s rules
are deterministic and hand-auditable; a gradient-boosting model is deterministic at inference
but not hand-auditable. Two consequences shape this PRD: every score ships **beside a simple,
hand-checkable comparison score** and its top reasons, and every reported metric must be
**reproducible from public data with one command per stage**.

## 2. Decisions already made (see `decisions.md`)

| Topic | Decision |
|---|---|
| What is predicted | Any inpatient stay in the 12 months after the as-of date, adults 18+ (O1). |
| Where the model runs | One new service, `outcome-prediction-service/` (O2). |
| What it returns | FHIR `RiskAssessment` with `probabilityDecimal`; Phase 8's own models, `triage-service` untouched (O3). |
| Phase numbering | The prototype's planned stages → milestones M1–M11 + Phase 8b (O4). |
| Hand-off documents | Not kept; their content restated in `prototype-baseline.md` and here (O5). |
| Order of work | Reproduce the prototype's numbers before changing any logic (O6). |
| Training data | MEPS longitudinal panels 21–27 (2016–2023), carried over from the prototype; commercial use still unconfirmed (O23). |
| Input path | FHIR from `fhir-service` via `client/clinical`, this phase (O8, O9). |
| Agent | New `outcome-prediction-agent/` on `agent-platform`; `mcp-agent` untouched; self-hosted LLM by default (O15, O16). |
| Exposure | Internal-only; no Kong route (O14). |

## 3. Goals

- **G1 — Reproduce the prototype.** Rebuild the MEPS modelling table (56,360 adults, 4,820
  events), the gradient-boosting model (temporal-test AUROC 0.769) and the comparison model
  (0.708) inside this repo, within the prototype's tolerances (`prototype-baseline.md` §5), with tests.
- **G2 — A reproducible training pipeline.** Download, build, train, evaluate: one command per
  stage, fixed seeds, pinned versions, recorded data checksums, machine-readable and readable
  reports.
- **G3 — One versioned feature contract.** Every source — MEPS for training, Synthea CSV for
  reproduction, FHIR in production — is converted to the same versioned schema (`meps25-v1`
  first). The model only ever sees that schema.
- **G4 — Score a real FHIR patient.** Given a patient in `fhir-service` and an as-of date, derive
  the contract features from their FHIR record and return a `RiskAssessment`.
- **G5 — Leakage-proof scoring.** Scoring mode never reads a record dated after `as_of`, and a
  test proves it (O10).
- **G6 — Explainable output.** Every result carries the main probability, the comparison-model
  probability, a population percentile, the model and contract versions, top contributing
  features, and references to the FHIR resources it was derived from.
- **G7 — Grounded conversational access.** A clinician can ask, in natural language, for a
  patient's hospitalization risk and its reasons; the agent relays the service's output and
  introduces no fact of its own.
- **G8 — A better label and model (second half of the phase).** An unplanned-stay label that
  excludes childbirth/pregnancy stays, richer condition and drug features, panel-grouped
  tuning, and specific attention to adults 65+.

## 4. Non-goals

- **The agent never computes, adjusts, or infers a risk score.** Same boundary as every agent
  in this repo (CLAUDE.md: "the agent orchestrates but holds no clinical logic").
- **No real patient data reaches any LLM or online service.** Development uses MEPS public
  files and Synthea only (O16).
- **No free-text features.** The training data has none.
- **Not a real-time or emergency tool.** A yearly planning score.
- **No diagnosis or treatment recommendation.**
- **No customer data in this repository,** for training or fixtures.
- **No UK or other non-US data sources.** (Rejected with reasons in `prototype-baseline.md` §2.)
- **No CPT codes** (AMA licence).
- **Synthea results are never evidence of accuracy.** Every report that includes them says so.
- **No qualitative band (high/moderate/low)** until thresholds are clinically signed off (O24).
- **No changes to `triage-service`, `mcp-agent`, or the Kong gateway.**

## 5. Users and triggers

| User | Need | Served by |
|---|---|---|
| Care manager / nurse | Ranked patients, with reasons | Scoring API + percentile + top reasons (worklist UI deferred, §8) |
| Primary-care clinician | One patient's risk, easy to sanity-check | Agent (G7) or API; comparison score beside the main score |
| Population-health lead | Calibrated risk; subgroup performance | Evaluation reports (FR-E*) |
| Customer IT / data engineering | A documented input schema | Feature contract + FHIR adapter |
| Repo owner | Reproducible pipeline, licence position, a sellable platform | G1–G2, O13, O23 |

- **Trigger A — single patient, on demand.** `patient_id` + optional `as_of` (default: today).
  Via the API directly, or via `outcome-prediction-agent`.
- **Trigger B — contract rows.** Pre-built feature rows in the contract schema (from an
  external ETL, or tests). Same model, same response type.
- **Population batch** (a whole customer panel) is deferred to Phase 8b (§8).

## 6. Functional requirements

The prototype's requirement IDs are **kept** for traceability. Status: **In** (this phase,
milestone shown), **Changed** (in, but altered — see §11), **8b** (deferred to Phase 8b),
**Out**. New, repo-specific requirements use the `FR-F*` (FHIR) and `FR-A*` (agent) prefixes.

### Data (MEPS)

| ID | Requirement | Status |
|---|---|---|
| FR-D1 | Download MEPS longitudinal panels 21–27 from AHRQ, cache locally, record SHA-256s; never commit raw data | In — M1 |
| FR-D2 | Build the modelling table: 25 features, label, panel, person ID, survey design variables | In — M1 |
| FR-D3 | Variable dictionary for any MEPS Stata file | In — M1 |
| FR-D4 | Unplanned-stay label `label_unplanned_12m` excluding childbirth/pregnancy (`RSNINHOS` 4/5/6), optionally planned stays | In — M9 |
| FR-D5 | Condition and drug features (Medical Conditions, Prescribed Medicines files) | In — M10 |
| FR-D6 | Optional survey-only feature group (function, PHQ-2, K6, VR-12, BMI) | In — M10, as a separately reported experiment; never in the FHIR contract |
| FR-D7 | Exclude or separately test round-3 items (leakage risk) | In — M9 |

### Model

| ID | Requirement | Status |
|---|---|---|
| FR-M1 | `HistGradientBoostingClassifier` (300 iter, lr 0.05, seed 0, 5 native categoricals) | In — M2 |
| FR-M2 | Comparison model: logistic regression on age + any year-1 stay | Changed — M2: also persisted in the artifact (O18) |
| FR-M3 | Temporal validation: train panels 21–25, test 26–27 | In — M2 |
| FR-M4 | Release model on all panels, with feature list, categories, library versions, data hash | Changed — M2: plus SHA-256 manifest verified before load (O17) |
| FR-M5 | Panel-grouped CV tuning on training panels only | In — M10 |
| FR-M6 | Separate or specially tuned model for 65+ | In — M10 |
| FR-M7 | Recalibration on a customer's own data | 8b — needs customer outcomes |
| FR-M8 | Per-patient explanations (top contributing features) | In — M6 |

### Evaluation

| ID | Requirement | Status |
|---|---|---|
| FR-E1 | AUROC, AUPRC, Brier, mean predicted vs actual, PPV/sensitivity at top 5/10/20% with bootstrap 95% CIs | In — M2 |
| FR-E2 | Calibration by risk decile | In — M2 |
| FR-E3 | Subgroup AUROC by age band, sex, prior hospitalization | In — M2 |
| FR-E4 | Permutation importance on test panels | In — M2 |
| FR-E5 | Survey-weighted AUROC (`LONGWT`) | In — M2 |
| FR-E6 | Fairness metrics by race/ethnicity and insurance type | In — M10 |

### ETL

| ID | Requirement | Status |
|---|---|---|
| FR-T1 | Synthea CSV → 25-feature schema for a chosen year 1, plus year-2 label in training mode | In — M3 (reproduction harness, O8) |
| FR-T2 | Score converted rows with the saved model | In — M3 |
| FR-T3 | Training mode (builds label) separate from scoring mode (no label, no future data) | Changed — M3: scoring mode defined by `as_of`, with a mandatory leakage test (O10) |
| FR-T4 | Versioned code lists from the NLM SNOMED CT → ICD-10-CM map, 3-character | In — M11 |
| FR-T5 | FHIR R4 US Core and claims-file adapters into one transform | Changed — FHIR via `fhir-service` in M5 (FR-F1–F4); claims-file adapter deferred (§8) |
| FR-T6 | Data-quality report: missing/impossible values, unknown codes, drift vs MEPS | In — M5 |

### FHIR path (new)

| ID | Requirement | Status |
|---|---|---|
| FR-F1 | `client/clinical` gains domain methods for encounters, medication history and claim/EOB cost, additively; every existing test passes unmodified | In — M4 |
| FR-F2 | A FHIR extractor builds the canonical tables (`design.md` §7) from `client/clinical` for one patient and an `as_of` date | In — M5 |
| FR-F3 | For patients generated in one Synthea run, the FHIR path and the CSV path produce identical contract rows, or every difference is listed and explained | In — M5 |
| FR-F4 | Every derived feature records which FHIR resources contributed, so the `RiskAssessment.basis` can cite them | In — M5 |

### Service

| ID | Requirement | Status |
|---|---|---|
| FR-S1 | REST API: score one patient or a batch of contract rows | Changed — M6: patient-by-ID endpoint added; responses are `RiskAssessment` / `Bundle` (O3) |
| FR-S2 | Return main risk, comparison risk, percentile, model version, top reasons | Changed — M6: carried inside the `RiskAssessment` (`design.md` §4) |
| FR-S3 | Health and model-metadata endpoints | In — M6 |
| FR-S4 | Batch job scoring a whole population from object storage | 8b |
| FR-S5 | Input-drift and performance monitoring | 8b |

### Agent (new)

| ID | Requirement | Status |
|---|---|---|
| FR-A1 | `outcome-prediction-agent` resolves a patient by name (via the service's tools), calls the risk tool, and narrates the result | In — M7 |
| FR-A2 | Every number or reason the agent states is present in the tool output; it never computes, rounds into a band, or compares against thresholds of its own | In — M7 |
| FR-A3 | Every narration states that the score is a planning aid, not a diagnosis, and names the model version | In — M7 |

## 7. Non-functional requirements

| Area | Requirement |
|---|---|
| Reproducibility | Fixed seeds; exact `scikit-learn` pin, other deps pinned per repo convention; data checksums recorded; one module CLI per stage (O12). |
| Privacy | No PHI in the repo, logs, fixtures or traces. Log patient references only. Development data is MEPS public files and Synthea only. |
| Toolchain | Python `>=3.11`, FastAPI + Pydantic, pandas, scikit-learn — matching `triage-service`. Synthea v4.0.0 on Java 21 (O11). |
| Observability | OpenTelemetry, same instrumentation pattern as `triage-service` (Phase 6). Spans carry model ID and contract version, never feature values. |
| Performance | One patient from contract rows under 100 ms; 100,000 contract rows under 10 minutes on one standard VM (carried over; the FHIR fetch path is measured, not targeted, this phase). |
| Integrity | The service refuses an artifact whose manifest doesn't verify (O17). |
| Additivity | `docker compose up` (no profile) unchanged; Phase 1 independence CI job unchanged; `phase8` profile and CI job added (O12). |
| Licensing | MEPS and Synthea recorded in `data/reference/README.md`; new third-party code in `NOTICE` (O13). |

## 8. Out of scope / deferred (explicit)

| Deferred | Where | Why it's safe to defer now |
|---|---|---|
| Cloud deployment, BAA-covered hosting | Phase 8b | Every prior phase proved locally first (Phase 2b, 3b). |
| Recalibration on customer data (FR-M7) | Phase 8b | Needs a customer year with known outcomes; nothing to calibrate against yet. |
| Monitoring (FR-S5) | Phase 8b | Needs production traffic. |
| Population batch from object storage (FR-S4) | Phase 8b | Contract-row batch scoring (Trigger B) covers testing needs. |
| First real-data validation | Phase 8b | Customer data never enters this repo. |
| Claims-file adapter | Not scheduled | Depends on O26. CMS Synthetic RIF (`prototype-baseline.md` §8) is the test source when it's picked up. |
| Persisting `RiskAssessment` to `fhir-service` | Not scheduled | O20. |
| Kong edge route | Phase 8b | Infra change (O14). |
| Worklist UI | Not scheduled | Same posture as other phases' UI deferrals. |
| Qualitative risk bands | Not scheduled | O24. |

## 9. Acceptance criteria

1. **Dataset (M1):** the build produces exactly 56,360 rows and 4,820 events, with the per-panel
   counts in `prototype-baseline.md` §3.1.
2. **Model (M2):** gradient-boosting test AUROC in [0.760, 0.778]; comparison model in
   [0.700, 0.716]. FR-E1–E5 written to `metrics.json` and a Markdown report.
3. **Dictionary (M1):** HC-252 lists 2,648 variables (1,603 int8, 611 int16, 383 int32,
   25 float64, 26 strings).
4. **Synthea CSV (M3):** the 25 features with correct types and codes; schema and sanity checks
   only, never exact counts.
5. **Leakage (M3, M5):** adding or removing records dated after `as_of` changes no feature.
6. **Parity (M5):** FR-F3 holds for a Synthea run exported as CSV and FHIR.
7. **Service (M6):** a patient in `fhir-service` returns a valid FHIR R4 `RiskAssessment` with
   `probabilityDecimal`, the comparison score, percentile, model and contract versions, top
   reasons, and `basis` references that resolve.
8. **Agent (M7):** a natural-language request returns a narration in which every number and
   reason traces to the tool output; adversarial prompts asking it to "adjust" or "band" the
   score fail closed.
9. **End to end (M8):** `e2e/test_outcome_prediction_acceptance.py` passes against real running
   services under the `phase8` profile.
10. **Additivity (all):** Phase 1 independence job still passes unmodified.

Later-milestone targets (M9–M10), carried over from the prototype's plan: MEPS test AUROC ≥ 0.78
(all adults) and ≥ 0.73 (65+); mean predicted within 1 percentage point of actual; top-decile
PPV on the unplanned label reported against QAdmissions' 42% with the outcome difference stated.

## 10. Open questions

Resolved in this pass: see `decisions.md` O1–O22.

Still open: O23 (MEPS commercial use, a legal question), O24 (qualitative bands), O25
(non-portable features), O26 (FHIR vs claims as primary customer input), O27 (code-list
sign-off). Carried over unchanged from the prototype's plan: which cloud hosts production
(Phase 8b), and any-stay vs unplanned-stay as the product's headline label (decided after M9's
numbers exist).

**Risks carried over from the prototype's plan** (`prototype-baseline.md` §9) — AHRQ declining commercial use, an employer
IP claim, survey-vs-records mismatch, Synthea mistaken for accuracy evidence, weak 65+
performance, childbirth in the label, regulatory change — all stand; their mitigations map to
O23, M5/M10, FR-A3 and M9–M10 respectively. The FDA clinical-decision-support position (a
non-time-critical score with its basis visible) still needs counsel's review before any launch.

## 11. Deviations from the prototype's plan

| # | Prototype's plan | This phase does | Why |
|---|---|---|---|
| V1 | Its own stage numbering | Milestones M1–M11 + Phase 8b | O4 |
| V2 | Standalone repo `hosp-risk/`, own `docs/`, Makefile, `.devcontainer`, CI | `outcome-prediction-service/` in this monorepo; existing devcontainer, CI workflow, compose; module CLIs | O2, O12 |
| V3 | `/v1/score` returns custom JSON | `RiskAssessment` (and `Bundle` for batches) | O3 |
| V4 | FHIR and claims adapters "later" | FHIR via `fhir-service` this phase; claims deferred | O8, O26 |
| V5 | Synthea `master-branch-latest`, Java 17 from Adoptium | Repo-pinned Synthea v4.0.0, Java 21 | O11 |
| V6 | Python 3.12+ | `>=3.11`, matching every package and CI | O12 |
| V7 | `LICENSES.md` | `NOTICE` + `data/reference/README.md` | O13 |
| V8 | Copy prototype scripts into `meps/` and `synthea/` | Not committed; implemented from `prototype-baseline.md` §4 and §6.3, checked against §5 | O7 |
| V9 | Release artifact saves the GBM only | Comparison model persisted too | O18 |
| V10 | Prescription fills prorate over a stop date defaulted to the end of year 2 | Scoring mode reads nothing after `as_of` | O10, `design.md` §11 |
| V11 | Unknown state → South (3) | Unknown → 0, as the contract specifies | `design.md` §11 |
| V12 | Model-improvement work before the service | Service and agent first (on `meps25-v1`), then the model | `milestone-plan.md` sequencing |
| V13 | Docs: no em dashes, no emojis | Repo house style | O19 |
| V14 | "Year 1" is a calendar year | An explicit `as_of`, trailing 12 months (calendar year only for reproduction) | O10 |

## 12. Provenance

This PRD synthesises the research prototype's hand-off (restated in `prototype-baseline.md`)
with the repo owner's two scoping decisions — a new service, and
FHIR `RiskAssessment` output — and a direct audit of this repo's code and earlier phases'
documents. The prototype is the input; this document is the contract.
