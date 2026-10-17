# Machine learning patient outcome prediction

## Turn 1

### Prompt

I want to use Machine Learning to predict patient outcomes sich as likelihood of hospitalization. I want to start a brand new phase for this. Tell me what phase number it should be.

### Claude response

It should be **Phase 8**.

The repo's phases currently go up to Phase 7. Each one has a folder in [docs/](docs/) (`phase2` through `phase7`), and nothing higher is mentioned anywhere. Phase 7 (Medication Reconciliation) only has its planning docs so far: the PRD, design, decisions and milestone plan came in with PR #63. None of its code has been written yet.

Because Phase 7 is still unbuilt, Phase 8 can be planned now, but it shouldn't depend on anything Phase 7 will deliver. Two things to settle early:

- **Where the model runs.** The agent must not contain clinical logic, so the hospitalization-risk model should live in a service like `triage-service`, or in a new one. The agent would only call it.
- **What it returns.** Predictions could come back as FHIR `RiskAssessment` resources with a probability attached, the same format the existing drug-allergy triage uses.

I can set up `docs/phase8/` with a PRD, design, decisions and milestone plan in the same format as Phase 7, on a feature branch with a PR.

## Turn 2

### Prompt

Decisions:

Where the model runs: New service
What it returns: Predictions could come back as FHIR resources, such as RiskAssessment with a probability attached, the same format the existing drug-allergy triage uses.

===============

Internalize the above, then I will upload some work that will be like receiving a handoff from another team

### Claude response

I've noted both Phase 8 decisions:

- **Where the model runs:** a new, dedicated prediction service. Not `triage-service`, and not the agent, which only calls it.
- **What it returns:** predictions come back as FHIR `RiskAssessment` resources with a probability attached, the same format the drug-allergy triage uses.

I also saved them to project memory, since no `docs/phase8/` exists yet to record them.

Go ahead and upload the handoff. I'll review it against these two decisions and the repo's conventions, and point out any gaps or conflicts before anything goes into `docs/phase8/`.

## Turn 3

### Prompt

I will give you three markdowns as inline prompts. This will also help with my record keeping system. Ask for these three parts one at a time:

1. Draft PRD (WIP)
2. Preliminary Design (not actual design, needs LOTS more exploration and iterations)
3. Developer notes

### Claude response

Please paste **Part 1: the draft PRD (WIP)**.

I'll take it in as it is, without reviewing it yet. Once all three parts are in, I'll review them together. After the PRD, I'll ask for the preliminary design.

## Turn 4

### Prompt

<pasted_content id="62de">
# Product Requirements Document: 12-Month Hospitalization Risk Service

Version: 0.1 (research prototype complete, production build not started)
Date: October 16, 2026
Owner: Product and engineering lead (the user)
Audience: the product owner, and Claude Code working in a fresh session. Claude Code should read this document first, then `02_Preliminary_Design.md`, then `03_Developer_Notes.md`.

---

## 1. Summary

Build a production-ready cloud service that estimates each adult patient's probability of at least one inpatient hospital stay in the next 12 months. Train and test it only on free, open, US-based data that permits later commercialization. The first target customer type is a chain of US primary care clinics, especially risk-bearing practices that serve Medicare patients.

A research prototype already exists and was built in an earlier session. It is described in section 9. The immediate job for Claude Code is to reproduce that prototype in a GitHub repository, with tests, and then extend it as described in the phases below.

## 2. Problem

Primary care teams in value-based contracts are paid to keep patients out of the hospital. They need a ranked list of who is most likely to be hospitalized in the next year, so care managers can reach out early. Commercial risk scores exist but are proprietary and expensive, and they are often trained on data the vendor cannot share. The user wants to own a model and pipeline whose training data and code can be inspected, reproduced and commercialized.

## 3. Users

| User | Need |
|---|---|
| Care manager or nurse | A ranked list of patients, with the reasons each one is high risk |
| Primary care clinician | A per-patient risk score at the point of care, easy to sanity check |
| Population health or analytics lead | Calibrated risk for budgeting and staffing; performance reports by subgroup |
| Customer IT or data engineering team | A documented input schema and a way to send records (FHIR or claims) |
| Product owner (the user) | A reproducible pipeline, clear licensing position, and a path to sell the platform |

## 4. Goals and non-goals

### Goals

1. Predict 12-month hospitalization risk for adults (18 and older).
2. Use only free, open, US-based data for training and testing.
3. Keep the freedom to commercialize later.
4. Use AI tools (Claude Code) to do the engineering work.
5. Run as a cloud service with an API.
6. Accept real medical records or claims from a customer, convert them into the model's input schema automatically, and score them.
7. Show both a complex model score and a simple, hand-checkable comparison score.

### Non-goals (for now)

- Free-text features (doctor's notes, NLP, sentiment analysis). The training data has no free text. Revisit only when a customer's notes are available.
- Real-time or emergency use. This is a yearly planning tool, not an alarm.
- Diagnosis or treatment recommendations.
- Training on customer data inside this repository. Customer data never enters the repo.
- UK or other non-US data sources.

## 5. Constraints and decisions already made

| Decision | Rationale | Evidence |
|---|---|---|
| Outcome is any inpatient stay in the next calendar year | User's chosen focus | User instruction |
| Data must be open, free and allow commercialization | User's chosen constraint | User instruction |
| Primary training data is MEPS (AHRQ Medical Expenditure Panel Survey) two-year longitudinal panels 21 to 27 (2016 to 2023) | Only real, de-identified, free, US, person-level data found with a true 12-month prospective outcome | [MEPS](https://meps.ahrq.gov) |
| MEPS commercial-use terms are ambiguous and must be confirmed in writing with AHRQ | The data use terms say data "may not be used for any purpose other than for the purpose for which they were supplied" | [MEPS DUA wording](https://meps.ahrq.gov/data_stats/download_data/pufs/h213d/h213ddoc.shtml) |
| Business model: sell the platform (pipeline, calibration, retraining on customer data), not trained weights alone | Reduces dependence on MEPS terms and on synthetic data realism | Earlier critique in this project |
| NHS or UK data rejected | CPRD costs about £20,600 to £83,850 per year and limits use to public-health research ([CPRD pricing](https://www.cprd.com/access-data/pricing)). OpenSAFELY requires UK-based users and returns aggregates only ([OpenSAFELY](https://www.opensafely.org/access-to-opensafely/)). US and UK coding and care patterns differ. | Earlier research |
| MIMIC-IV and other credentialed sets rejected for training | Require approved access and restrict use. MIMIC's agreement bans sending data to online services such as LLM APIs, which conflicts with AI-assisted development | [PhysioNet](https://physionet.org/) |
| Health and Retirement Study rejected | Restricted to research and statistical purposes | [HRS overview](https://hrs.isr.umich.edu/sites/default/files/biblio/OverviewofHRSPublicData.pdf) |
| MCBS public file rejected | Contains no utilization data, so no hospitalization label | [CMS MCBS PUF guide](https://www.cms.gov/files/document/2021-mcbs-puf-data-user-guide.pdf) |
| Synthea used only to test the ETL and service, never to judge accuracy | Its outcomes are simulated by rules; its realism is limited | [Synthea](https://github.com/synthetichealth/synthea), [evaluation 1](https://pmc.ncbi.nlm.nih.gov/articles/PMC6416981/), [evaluation 2](https://pmc.ncbi.nlm.nih.gov/articles/PMC7651916/) |
| CPT procedure codes are not used | CPT requires an AMA license | [AMA CPT licensing](https://www.ama-assn.org/practice-management/cpt/cpt-licensing-frequently-asked-questions-faqs) |
| ICD-10-CM and SNOMED CT are allowed | ICD-10-CM is free in the US. SNOMED CT and the SNOMED to ICD-10-CM map are free in the US with a UMLS license | [NLM map](https://www.nlm.nih.gov/research/umls/mapping_projects/snomedct_to_icd10cm.html) |
| Regulatory posture: non-time-critical risk score shown to clinicians with its basis visible | Likely outside FDA device rules or under enforcement discretion per FDA clinical decision support guidance. Must be reviewed by counsel | [FDA CDS guidance](https://www.fda.gov/media/109618/download) |
| Benchmark: QAdmissions (UK) reports AUROC 0.77 to 0.78 and top-decile PPV of 42% for emergency admission | Published reference point | [BMJ Open](https://bmjopen.bmj.com/content/3/8/e003482) |

## 6. Key definitions

| Term | Definition |
|---|---|
| Label (target) | The known outcome attached to each training example. Here `label_hosp_12m` = 1 if the person had at least one inpatient discharge in calendar year 2 of their MEPS panel (`IPDISY2 > 0`), else 0. |
| Features (inputs) | Information from calendar year 1 only, used to predict the label. |
| Prediction | The model's output: a probability from 0 to 1 that the label is 1. |
| Year 1, year 2 | The two calendar years of a MEPS longitudinal panel. Panel 27 covers 2022 (year 1) and 2023 (year 2). |
| AUROC | Probability that a random hospitalized person is ranked above a random non-hospitalized person. 0.5 is chance. |
| AUPRC | Average precision. Chance equals the event rate (about 0.088). |
| Brier score | Mean squared error of predicted probabilities. Lower is better. |
| Top-decile PPV | Share hospitalized among the 10% with the highest predicted risk. |
| Calibration | Whether predicted risks match observed rates, checked by risk deciles. |
| Simple comparison model | Logistic regression on age and any hospital stay in year 1. Used as a baseline and shown alongside the main score. |

## 7. Data scope

### Training and testing data (MEPS)

- Panels 21 to 27, two-year longitudinal files only. Panel to file: 21 = HC-202, 22 = HC-210, 23 = HC-217, 24 = HC-225, 25 = HC-234, 26 = HC-244, 27 = HC-252.
- HC-245 is a Panel 24 three-year file. It must be excluded to avoid duplicate people.
- Population: adults 18 and older on December 31 of year 1, with non-negative `IPDISY1` and `IPDISY2`.
- Expected result: 56,360 adults, 4,820 hospitalized in year 2 (8.6%).
- Available but not yet used: Medical Conditions files (3-character ICD-10-CM plus CCSR categories), Prescribed Medicines files (NDC, Multum drug classes), event files (hospital stays with reason and ER flag, office visits with services), function, mental health, BMI, social needs, preventive care. Full inventory: `MEPS_feature_inventory.md`, which Claude Code should regenerate (see Developer Notes).

### What MEPS does not have

No free text, no lab values, no vital signs except BMI, no procedure codes, no full ICD-10 codes, no exact dates (month and year only), no geography finer than 4 census regions, no provider identity.

### Test data for the ETL and service

Synthea synthetic medical records, generated locally. Software is Apache 2.0, and published synthetic data is public domain ([Synthea DPG page](https://github.com/synthetichealth/synthea/wiki/DPG)).

## 8. Functional requirements

Priority: P0 = needed to reproduce the prototype, P1 = needed for a first production release, P2 = later.

### Data

| ID | Requirement | Priority |
|---|---|---|
| FR-D1 | Download MEPS longitudinal panels 21 to 27 automatically from AHRQ and cache them locally. Never commit raw data to git. | P0 |
| FR-D2 | Build the modeling table with 25 features, the label, panel, person ID and survey design variables. | P0 |
| FR-D3 | Produce a variable dictionary for any MEPS Stata file: name, label, storage type, range, negative missing codes, value labels, string lengths. | P0 |
| FR-D4 | Exclude childbirth and pregnancy stays from the label (MEPS `RSNINHOS` 4, 5, 6 in the hospital stay files), and optionally planned stays, as a second label `label_unplanned_12m`. | P1 |
| FR-D5 | Add features from the Medical Conditions and Prescribed Medicines files (condition counts, CCSR groups, comorbidity scores, drug-class flags, polypharmacy). | P1 |
| FR-D6 | Add survey-only features (function, self-rated health, PHQ-2, K6, VR-12, BMI) as a separate, optional feature group. | P2 |
| FR-D7 | Exclude round 3 items, or test them separately, because round 3 ends in year 2 for almost everyone. | P1 |

### Model

| ID | Requirement | Priority |
|---|---|---|
| FR-M1 | Train a gradient boosting model (`HistGradientBoostingClassifier`, 300 iterations, learning rate 0.05, random_state 0, native categorical handling for 5 category features). | P0 |
| FR-M2 | Train the simple comparison model (logistic regression, age plus any year-1 stay). | P0 |
| FR-M3 | Temporal validation: train on panels 21 to 25, test on panels 26 to 27. | P0 |
| FR-M4 | Save the final model trained on all panels, with feature list, category list, library versions and training data hash. | P0 |
| FR-M5 | Hyperparameter tuning with panel-grouped cross-validation on training panels only. | P1 |
| FR-M6 | A separate or specially tuned model for adults 65 and older. | P1 |
| FR-M7 | Recalibration on a customer's own recent data (isotonic or Platt scaling). | P1 |
| FR-M8 | Per-patient explanations (top contributing features). | P1 |

### Evaluation

| ID | Requirement | Priority |
|---|---|---|
| FR-E1 | Report AUROC, AUPRC, Brier score, mean predicted vs actual rate, PPV and sensitivity at top 5%, 10% and 20%, with bootstrap 95% confidence intervals. | P0 |
| FR-E2 | Report calibration by risk decile. | P0 |
| FR-E3 | Report subgroup AUROC by age group (18 to 44, 45 to 64, 65 and older), sex, and prior hospitalization. | P0 |
| FR-E4 | Report permutation importance on the test panels. | P0 |
| FR-E5 | Report a survey-weighted AUROC using `LONGWT`. | P0 |
| FR-E6 | Report fairness metrics by race and ethnicity and by insurance type. | P1 |

### ETL (medical records to MEPS schema)

| ID | Requirement | Priority |
|---|---|---|
| FR-T1 | Convert Synthea CSV records into the exact 25-feature MEPS schema for a chosen year 1, plus a year-2 label in training mode. | P0 |
| FR-T2 | Score converted rows with the saved model. | P0 |
| FR-T3 | Separate training mode (builds the label) from scoring mode (no label, no future data). | P1 |
| FR-T4 | Replace description-based diagnosis rules with versioned code lists built from the NLM SNOMED CT to ICD-10-CM map, truncated to 3 characters. | P1 |
| FR-T5 | Add adapters for FHIR R4 US Core bulk export and for claims files, feeding one shared transform step. | P1 |
| FR-T6 | Data quality checks with a report: missing or impossible values, unknown codes, distribution drift vs MEPS. | P1 |

### Service

| ID | Requirement | Priority |
|---|---|---|
| FR-S1 | REST API to score one patient or a batch in the MEPS feature schema. | P1 |
| FR-S2 | Return main risk, comparison-model risk, risk percentile, model version, and top reasons. | P1 |
| FR-S3 | Health and model-metadata endpoints. | P1 |
| FR-S4 | Batch job to score a full customer population from FHIR or claims input. | P1 |
| FR-S5 | Monitoring of input drift and, when outcomes arrive, of performance. | P2 |

## 9. Current state (prototype results to reproduce)

All numbers below were produced in the earlier session and must be reproduced within the tolerances in section 11.

### Dataset

| Panel | Years | Adults | Hospitalized in year 2 |
|---|---|---|---|
| 21 | 2016 to 2017 | 11,174 | 880 |
| 22 | 2017 to 2018 | 10,613 | 940 |
| 23 | 2018 to 2019 | 10,447 | 989 |
| 24 | 2019 to 2020 | 7,533 | 592 |
| 25 | 2020 to 2021 | 4,730 | 377 |
| 26 | 2021 to 2022 | 5,350 | 453 |
| 27 | 2022 to 2023 | 6,513 | 589 |
| Total | | 56,360 | 4,820 (8.6%) |

### Model on test panels 26 to 27 (11,863 adults, 1,042 hospitalized, rate 8.78%)

| Measure | Comparison model | Gradient boosting |
|---|---|---|
| AUROC [95% CI] | 0.708 [0.691, 0.725] | 0.769 [0.754, 0.786] |
| AUPRC [95% CI] | 0.225 [0.206, 0.250] | 0.265 [0.242, 0.290] |
| Brier (null 0.0801) | 0.0751 | 0.0725 |
| Mean predicted risk | 9.0% | 9.2% |
| Top 5% PPV / sensitivity | 0.331 / 0.188 | 0.383 / 0.218 |
| Top 10% PPV / sensitivity | 0.266 / 0.303 | 0.293 / 0.333 |
| Top 20% PPV / sensitivity | 0.202 / 0.460 | 0.231 / 0.525 |
| Survey-weighted AUROC | | 0.780 |

Subgroups (gradient boosting): ages 18 to 44 AUROC 0.761; 45 to 64, 0.739; 65 and older, 0.695 (rate 16.3%); men 0.794; women 0.743; no prior stay 0.744; prior stay 0.694.

Calibration by decile ranged from predicted 1.6% vs actual 0.8% in the lowest decile to predicted 30.4% vs actual 29.2% in the highest.

Top permutation importances (AUROC drop): age 0.040, sex 0.017, prescription fills 0.012, then high blood pressure, office visits, nights in hospital, spending, ER visits and poverty (about 0.005 each).

Known label issue: women aged 18 to 44 are hospitalized at 7.4% vs 2.2% for men, and rates are equal after 45. The label includes childbirth. Fix is FR-D4.

Comparison model coefficients (trained on panels 21 to 25): intercept -4.047, age 0.028 per year, any year-1 stay 1.306. Each 10 years multiplies odds by 1.32; a prior stay multiplies odds by 3.7.

### ETL test on Synthea

3,712 synthetic Arizona patients generated (seed 42, ages 18 to 90, end date 2024-12-31). 2,913 adults qualified for year 1 = 2023. 138 hospitalized in 2024 (4.7%). Mean predicted risk 10.5%. AUROC 0.656. This only proves the pipeline works mechanically; it does not measure real accuracy.

## 10. Non-functional requirements

| Area | Requirement |
|---|---|
| Reproducibility | Fixed random seeds. Pinned library versions. Data file checksums recorded. One command per pipeline stage. |
| Privacy and security | No PHI in the repository, logs or test fixtures. Synthetic data only in development. Production must meet HIPAA: encryption in transit and at rest, access logging, a BAA with the cloud provider. |
| AI tooling and data | Never send real patient data to an LLM or online AI service. MEPS public files and Synthea data are allowed. |
| Licensing | Track the license of every data source and code dependency in `LICENSES.md`. |
| Explainability | Every score returns its top reasons and the comparison score. |
| Performance | Scoring one patient under 100 ms; 100,000 patients in batch under 10 minutes on one standard VM. |
| Portability | Cloud-agnostic container. Development environment runs in Ona (formerly Gitpod) with a dev container. |
| Quality | Unit tests for every transform rule; end-to-end test on a small Synthea sample in CI. |

## 11. Acceptance criteria for reproducing the prototype (Phase 1)

1. `build` produces 56,360 rows and 4,820 events exactly, with the per-panel counts in section 9.
2. Gradient boosting test AUROC 0.769, allowed range 0.760 to 0.778. Comparison model AUROC 0.708, allowed range 0.700 to 0.716. Small differences can come from library versions.
3. All evaluation outputs in FR-E1 to FR-E5 are written to a machine-readable file (JSON) and a readable report (Markdown).
4. Variable dictionary for HC-252 lists 2,648 variables with storage counts 1,603 int8, 611 int16, 383 int32, 25 float64, 26 strings.
5. Synthea ETL produces the 25 features with correct types and value codes; numbers will vary with the Synthea version, so only schema and sanity checks are tested, not exact counts.
6. Tests pass in CI.

## 12. Success metrics for later phases

| Metric | Target |
|---|---|
| AUROC on MEPS test panels, all adults | 0.78 or higher |
| AUROC for adults 65 and older | 0.73 or higher |
| Top-decile PPV, unplanned-stay label | Report; compare against QAdmissions 42% with care, since outcomes differ |
| Calibration | Mean predicted within 1 percentage point of actual on test panels |
| First real-data validation | AUROC and calibration on one customer's historical data, kept separate from training |

## 13. Phases

| Phase | Content | Status |
|---|---|---|
| 0 | Research prototype in a chat session | Done |
| 1 | Reproduce prototype in the GitHub repo with tests and reports | Next |
| 2 | Better label (unplanned stays), richer features, tuning, 65+ model, explanations | Planned |
| 3 | Scoring API, batch job, FHIR and claims adapters, code-list mapping | Planned |
| 4 | Deployment, monitoring, recalibration, first customer validation | Planned |

## 14. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| AHRQ says MEPS cannot be used commercially | Model weights trained on MEPS cannot be sold | Ask AHRQ in writing now. Keep the business model on the platform and on retraining with customer data. |
| Employer IP agreement claims the work | Ownership dispute | Review the employment agreement before building on work time or equipment. |
| Self-report (MEPS) vs records (customer) mismatch | Lower accuracy and miscalibration in production | Use portable features first. Recalibrate per customer. Validate on customer history. |
| Synthea mistaken for evidence of accuracy | Wrong decisions | State clearly in every report that Synthea results are pipeline tests only. |
| Weak performance in 65+ | Poor fit for Medicare-focused customers | FR-M6, plus richer condition and drug features. |
| Label includes childbirth and planned stays | Model partly predicts pregnancy | FR-D4. |
| Regulatory change | Possible device classification | Legal review of FDA CDS guidance before launch. |

## 15. Open questions

1. Will AHRQ confirm commercial use of models trained on MEPS public files?
2. Is the primary customer input FHIR from an EHR, or claims from a payer contract, or both?
3. Which cloud provider will host production?
4. Should the product predict any stay, unplanned stays, or both?
5. Who signs off on clinical code lists?

## 16. Companion documents

Filenames are indicative, not verbatim accurate:
- `02_Preliminary_Design.md`: architecture, schema contract, API, repository layout.
- `03_Developer_Notes.md`: exact steps, URLs, gotchas, expected outputs, and full source code of the prototype.
</pasted_content id="62de">

### Claude response

I've got Part 1 and saved it word for word to `/tmp/claude-1000/-workspaces-fhir-agent/ece4ab01-8424-4908-a0ba-5c09fa9936d4/scratchpad/phase8-handoff/01_PRD.md`. It stays there until we decide where it goes in the repo.

Please paste **Part 2: the preliminary design**.

## Turn 5

### Prompt

<pasted_content id="62de">
# Preliminary Design: 12-Month Hospitalization Risk Service

Version: 0.1
Date: October 16, 2026
Read after: `01_PRD.md`. Implementation details and code: `03_Developer_Notes.md`.

---

## 1. Design principles

1. **One feature contract.** Every data source (MEPS for training, Synthea for testing, FHIR or claims in production) is converted into the same versioned feature schema. The model only ever sees that schema.
2. **Deterministic services decide, AI explains.** The risk score comes from a deterministic, versioned model. Any LLM use is limited to explaining results or helping development, never computing the score, and never with real patient data.
3. **Training and scoring are separate modes.** Training mode may look at year 2 to build the label. Scoring mode must never read data after the scoring date.
4. **Portable features first.** The core model uses features that also exist in claims or medical records. Survey-only features are an optional add-on group.
5. **Reproducible by one command per stage.** Fixed seeds, pinned versions, cached downloads, recorded checksums.
6. **No PHI in the repository.** Real data stays in the customer's environment. Development uses MEPS public files and Synthea only.

## 2. System context

```
                 +-------------------------+
 AHRQ MEPS  ---> |  Training pipeline      |  (offline, in repo, public data only)
 (public files)  |  build -> train -> eval |
                 +-----------+-------------+
                             | model artifact (versioned)
                             v
 Customer        +-------------------------+        +----------------------+
 FHIR / claims ->|  ETL adapters           |  --->  |  Scoring service     |
 (or Synthea)    |  extract -> transform   | rows   |  REST API + batch    |
                 |  -> MEPS feature schema |        |  model + baseline    |
                 +-------------------------+        +----------+-----------+
                                                               |
                                            risk, percentile, reasons, version
                                                               v
                                               Care management worklist / EHR
```

## 3. Components

### 3.1 Data acquisition (`meps/download`)

- Downloads `https://meps.ahrq.gov/data_files/pufs/h{n}/h{n}dta.zip` for each needed file.
- Extracts `h{n}.dta` with Python `zipfile` (do not assume an `unzip` binary).
- Caches under `data/raw/meps/` (git-ignored). Records SHA-256 of each file in `data/raw/meps/checksums.json`.
- Files needed now: HC-202, 210, 217, 225, 234, 244, 252 (longitudinal). Later: yearly Medical Conditions, Prescribed Medicines, Hospital Inpatient Stays, Office-Based Visits, and the condition-event link files for each year 1 from 2016 to 2022.

### 3.2 Dataset builder (`meps/build`)

- Reads each longitudinal file, selects core variables and diagnosis flags, filters to adults with valid year 1 and year 2 hospital counts, builds the label.
- Diagnosis variable names drift across years (for example `DIABDXY1_M18`). Resolve each flag by prefix: first column whose name starts with the prefix and contains `Y1`.
- Diagnosis flags are recoded from MEPS 1 = yes, 2 = no, negatives = missing, to 1 = yes, 0 = everything else.
- Output: `data/processed/meps_hosp12.csv` (CSV, because pyarrow may be missing in some environments; Parquet is acceptable if available).

### 3.3 Variable dictionary (`meps/inspect`)

- Dumps every variable of a MEPS Stata file: name, label, storage type, range of non-negative values, negative missing codes, value labels, string lengths.
- Used to regenerate `MEPS_feature_inventory.md` and the data-types reference.

### 3.4 Training (`model/train`)

- Gradient boosting: scikit-learn `HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, random_state=0, categorical_features=[sex, racethx, regiony1, inscovy1, povcaty1])`.
- Categorical columns are clipped at 0 (MEPS negative codes become category 0) and cast to int.
- Comparison model: `LogisticRegression(max_iter=1000)` on `[agey1x, ipdisy1 > 0]`.
- Validation model: trained on panels 21 to 25. Release model: retrained on all panels.
- Artifact: a directory `models/<model_id>/` with `model.pkl` (or `model.joblib`), `baseline.pkl`, `metadata.json` (feature list, categorical list, training panels, row count, event count, data checksum, library versions, git commit, metrics).

### 3.5 Evaluation (`model/evaluate`)

- Temporal test on panels 26 to 27.
- Metrics: AUROC, AUPRC, Brier, mean predicted vs actual, PPV and sensitivity at top 5, 10 and 20 percent, bootstrap 95% CIs (500 resamples, seed 0), calibration deciles, subgroup AUROC, permutation importance (5 repeats, scoring AUROC), survey-weighted AUROC with `LONGWT`.
- Outputs: `reports/metrics.json` and `reports/model_report.md`.

### 3.6 ETL adapters (`etl/`)

```
etl/
  extract/synthea_csv.py      # reads Synthea CSV export
  extract/fhir_r4.py          # later: FHIR R4 US Core bulk NDJSON
  extract/claims.py           # later: claims files (for example CMS RIF-like)
  canonical.py                # shared intermediate tables (see 3.6.1)
  transform/to_meps.py        # canonical -> MEPS feature schema
  codelists/                  # versioned code lists (ICD-10 3-char -> flag)
```

#### 3.6.1 Canonical intermediate model

Each extractor produces these tables. The transform step only reads these.

| Table | Columns |
|---|---|
| person | person_id, birth_date, death_date, sex, race, ethnicity, state, income (optional), household_size (optional) |
| coverage | person_id, start_date, end_date, payer_type (private, medicare, medicaid, dual, other_public, none) |
| encounter | person_id, encounter_id, start, stop, class (inpatient, emergency, office, outpatient, home, virtual, other), cost_paid (optional), cost_charged (optional), reason (optional) |
| condition | person_id, onset_date, code_system (snomed, icd10cm), code, description |
| medication_fill | person_id, fill_date or (start, stop, dispenses), rxnorm or ndc, cost (optional) |

#### 3.6.2 Mapping rules (current prototype)

| Feature | Rule |
|---|---|
| agey1x | Age in whole years on 12/31 of year 1, capped at 85. Adults only. |
| sex | M = 1, F = 2 |
| racethx | Hispanic ethnicity = 1; else white 2, black 3, asian 4, other 5 |
| regiony1 | State to census region: Northeast 1, Midwest 2, South 3, West 4 |
| povcaty1 | Income as percent of HHS poverty guideline (1-person household assumed): under 100 = 1, 100 to 124 = 2, 125 to 199 = 3, 200 to 399 = 4, 400 and up = 5 |
| inscovy1 | Any private coverage in year 1 = 1; else any public = 2; else 3 |
| ipdisy1 | Count of inpatient encounters starting in year 1 |
| ipngtdy1 | Sum of nights of those stays, from start to stop |
| ertoty1 | Count of emergency encounters |
| obtotvy1 | Count of ambulatory, wellness, urgent care and virtual encounters |
| optotvy1 | Count of hospital outpatient encounters |
| hhtotdy1 | Count of home encounters (one per day) |
| rxtoty1 | Fills in year 1. Synthea: each prescription's dispenses spread evenly over its active period |
| totexpy1 | Sum of year-1 encounter cost plus prorated medication cost, whole dollars |
| 11 diagnosis flags | Any matching condition recorded on or before 12/31 of year 1 |
| label_hosp_12m (training mode only) | Any inpatient encounter starting in year 2 |

Prototype diagnosis rules use SNOMED description patterns. Phase 3 replaces them with code lists: SNOMED CT to ICD-10-CM via the NLM map, truncate to 3 characters, then a reviewed list of 3-character codes per flag.

### 3.7 Scoring service (`service/`)

- Python FastAPI app, served by uvicorn, packaged as a container.
- Loads one model artifact at startup by `MODEL_ID`. Read-only.
- Validates inputs against the feature contract (section 4) with pydantic.

#### Endpoints

| Method and path | Purpose |
|---|---|
| `GET /v1/health` | Liveness and readiness |
| `GET /v1/model` | Model id, version, training data summary, metrics, feature contract version |
| `POST /v1/score` | Score 1 to 1,000 patients given in the feature schema |
| `POST /v1/batch` | Later: submit a job referencing a file in object storage; returns a job id |
| `GET /v1/batch/{id}` | Later: job status and result location |

#### `POST /v1/score` request

```json
{
  "contract_version": "meps25-v1",
  "patients": [
    {"patient_ref": "abc-123", "features": {
      "agey1x": 72, "sex": 2, "racethx": 2, "regiony1": 4, "inscovy1": 2, "povcaty1": 3,
      "ipdisy1": 1, "ipngtdy1": 4, "ertoty1": 2, "obtotvy1": 9, "optotvy1": 1, "hhtotdy1": 0,
      "rxtoty1": 38, "totexpy1": 21000,
      "hibpdx": 1, "chddx": 0, "angidx": 0, "midx": 0, "ohrtdx": 1, "strkdx": 0,
      "emphdx": 0, "diabdx": 1, "arthdx": 1, "asthdx": 0, "choldx": 1}}
  ]
}
```

#### Response

```json
{
  "model_id": "gbm-meps25-2026-10-16",
  "contract_version": "meps25-v1",
  "results": [
    {"patient_ref": "abc-123", "risk_12m": 0.31, "risk_percentile": 94,
     "baseline_risk_12m": 0.29, "top_reasons": ["agey1x", "ipdisy1", "rxtoty1"],
     "warnings": []}
  ]
}
```

- `risk_percentile` is computed against the training population or, after recalibration, against the customer's population.
- `warnings` flags out-of-range inputs (for example spending far outside the training range).

### 3.8 Recalibration (Phase 4)

- Input: one customer year with known outcomes.
- Fit isotonic regression (or Platt scaling if under about 300 events) mapping raw score to observed rate.
- Store as a separate calibrator artifact per customer. Never overwrite the base model.

### 3.9 Monitoring (Phase 4)

- Input drift: compare each feature's distribution with the training data (population stability index).
- Output drift: distribution of scores over time.
- Performance: when year-2 outcomes arrive, recompute AUROC and calibration per customer.

## 4. Feature contract `meps25-v1`

All fields are required integers. Codes follow MEPS. Negative values are not allowed at the API; the ETL must convert missing to a documented default and add a warning.

| Feature | MEPS source | Kind | Allowed values | Notes |
|---|---|---|---|---|
| agey1x | AGEY1X | integer | 18 to 85 | Top-coded at 85 |
| sex | SEX | category | 1 male, 2 female | |
| racethx | RACETHX | category | 1 Hispanic, 2 NH white, 3 NH black, 4 NH Asian, 5 NH other or multiple | |
| regiony1 | REGIONY1 | category | 1 Northeast, 2 Midwest, 3 South, 4 West | 0 if unknown |
| inscovy1 | INSCOVY1 | category | 1 any private, 2 public only, 3 uninsured | |
| povcaty1 | POVCATY1 | ordered category | 1 poor, 2 near poor, 3 low, 4 middle, 5 high income | |
| ipdisy1 | IPDISY1 | count | 0 and up | Hospital discharges |
| ipngtdy1 | IPNGTDY1 | count | 0 and up | Nights in hospital |
| ertoty1 | ERTOTY1 | count | 0 and up | ER visits |
| obtotvy1 | OBTOTVY1 | count | 0 and up | Office-based visits incl. telehealth |
| optotvy1 | OPTOTVY1 | count | 0 and up | Hospital outpatient visits |
| hhtotdy1 | HHTOTDY1 | count | 0 and up | Home health days |
| rxtoty1 | RXTOTY1 | count | 0 and up | Prescription fills incl. refills |
| totexpy1 | TOTEXPY1 | integer dollars | 0 and up | MEPS = payments, not charges |
| hibpdx | HIBPDXY1 | flag | 0, 1 | High blood pressure |
| chddx | CHDDXY1 | flag | 0, 1 | Coronary heart disease |
| angidx | ANGIDXY1 | flag | 0, 1 | Angina |
| midx | MIDXY1 | flag | 0, 1 | Heart attack |
| ohrtdx | OHRTDXY1 | flag | 0, 1 | Other heart disease |
| strkdx | STRKDXY1 | flag | 0, 1 | Stroke |
| emphdx | EMPHDXY1 | flag | 0, 1 | Emphysema |
| diabdx | DIABDXY1 or DIABDXY1_M18 | flag | 0, 1 | Diabetes |
| arthdx | ARTHDXY1 | flag | 0, 1 | Arthritis |
| asthdx | ASTHDXY1 | flag | 0, 1 | Asthma |
| choldx | CHOLDXY1 | flag | 0, 1 | High cholesterol |

Feature order in the model matrix (must match exactly): sex, racethx, regiony1, agey1x, inscovy1, povcaty1, ipdisy1, ipngtdy1, ertoty1, obtotvy1, optotvy1, hhtotdy1, rxtoty1, totexpy1, hibpdx, chddx, angidx, midx, ohrtdx, strkdx, emphdx, diabdx, arthdx, asthdx, choldx.

## 5. Repository layout

```
hosp-risk/
  README.md
  LICENSES.md                 # data and dependency licenses
  pyproject.toml              # pinned dependencies
  Makefile                    # make data, make train, make eval, make etl-test, make serve
  .devcontainer/              # Ona (Gitpod) environment: Python 3.12+, Java 17 JRE for Synthea
  .gitignore                  # data/, models/*.pkl, synthea outputs
  docs/
    01_PRD.md
    02_Preliminary_Design.md
    03_Developer_Notes.md
    MEPS_feature_inventory.md
    EHR_to_MEPS_mapping.md
  data/                       # git-ignored
    raw/meps/  raw/synthea/  processed/
  src/hosprisk/
    meps/download.py  meps/build.py  meps/inspect.py
    model/train.py  model/evaluate.py  model/artifact.py
    etl/extract/synthea_csv.py  etl/transform/to_meps.py  etl/codelists/
    service/app.py  service/schemas.py
  tests/
    test_build.py  test_transform_rules.py  test_contract.py  test_service.py
    fixtures/synthea_tiny/    # a few synthetic patients, committed
  reports/                    # generated metrics and reports
  models/                     # generated artifacts (git-ignored except metadata)
```

The prototype scripts in `03_Developer_Notes.md` use a flat `meps/` and `synthea/` layout. Phase 1 may first run them as-is to confirm the numbers, then refactor into `src/hosprisk/` without changing logic.

## 6. Technology choices

| Need | Choice | Reason |
|---|---|---|
| Language | Python 3.12 or later | Data and ML ecosystem |
| Data frames | pandas | Reads Stata files directly |
| Models | scikit-learn | Prototype uses it; stable, free |
| API | FastAPI + pydantic + uvicorn | Typed validation, OpenAPI docs |
| Synthetic data | Synthea jar, Java 17 JRE | Apache 2.0, public-domain outputs |
| Container | Docker | Cloud-agnostic |
| CI | GitHub Actions | Repo host |
| Dev environment | Ona (Gitpod) dev container | User's plan |

## 7. Testing strategy

| Level | What |
|---|---|
| Unit | Each mapping rule (age cap, race codes, region map, poverty bands, insurance precedence, encounter class counts, diagnosis patterns). Include the regression case: "Abnormal findings diagnostic imaging heart+coronary circulat" must not set `chddx`. |
| Data | Build output row counts per panel equal the PRD table. No negative values in feature columns except where documented. |
| Model | Test AUROC inside the PRD tolerance. Metadata contains the 25 features in the exact order. |
| Contract | Pydantic schema rejects missing fields, wrong types, out-of-range codes. |
| End to end | Tiny Synthea fixture runs through ETL and the API and returns 25-feature rows and valid probabilities. |
| Leakage | Scoring mode with a cutoff date returns identical features when records after the cutoff are added or removed. |

## 8. Security and compliance outline

- Development uses only MEPS public files and Synthea. Both are allowed to be processed with AI tools.
- Production runs in the customer's or a HIPAA-eligible cloud account under a BAA.
- Encryption in transit (TLS) and at rest. No PHI in logs; log patient references as opaque IDs.
- Access controlled by service accounts; audit log of every scoring request.
- Model artifacts are signed or checksummed; the service refuses unknown artifacts.

## 9. Known design gaps to resolve

1. Spending (`totexpy1`) is not portable: MEPS has payments, medical records have charges. Options: drop it, or convert to a within-population rank.
2. Household size is rarely in medical records, so `povcaty1` is weak outside MEPS. Consider area-level income from ZIP code in a later contract version.
3. Medical records from one health system miss outside care. Claims capture it better. The ETL should accept both and prefer claims for counts and labels.
4. The label includes childbirth and planned stays. Contract `meps25-v2` should pair with the unplanned-stay label.
</pasted_content id="62de">

### Claude response

I've got Part 2 and saved it word for word to `/tmp/claude-1000/-workspaces-fhir-agent/ece4ab01-8424-4908-a0ba-5c09fa9936d4/scratchpad/phase8-handoff/02_Preliminary_Design.md`.

Please paste **Part 3: the developer notes**.

<details>
<summary>Execution details — 6 tool events</summary>

### Turn 1 activity

- **Bash** `cd /workspaces/fhir-agent; ls docs 2>/dev/null; grep -rhoiE "phase ?[0-9]+" --include=*.md . | tr 'A-Z' 'a-z' | tr -d ' ' | sort | uniq -c | sort -k2 -V; git branch -a | grep -i phase`

### Turn 2 activity

- **Write** `/home/vscode/.claude/projects/-workspaces-fhir-agent/memory/phase8-ml-outcome-prediction.md`
- **Bash** `cd /home/vscode/.claude/projects/-workspaces-fhir-agent/memory; echo "- [Phase 8 ML outcome prediction](phase8-ml-outcome-prediction.md) — new service, RiskAssessment output; decided 2026-10-17" >> ME…`

### Turn 4 activity

- **Bash** `mkdir -p /tmp/claude-1000/-workspaces-fhir-agent/ece4ab01-8424-4908-a0ba-5c09fa9936d4/scratchpad/phase8-handoff`
- **Write** `/tmp/claude-1000/-workspaces-fhir-agent/ece4ab01-8424-4908-a0ba-5c09fa9936d4/scratchpad/phase8-handoff/01_PRD.md`

### Turn 5 activity

- **Write** `/tmp/claude-1000/-workspaces-fhir-agent/ece4ab01-8424-4908-a0ba-5c09fa9936d4/scratchpad/phase8-handoff/02_Preliminary_Design.md`

</details>

---

## Archive metadata

- **Source:** Claude Code
- **Session ID:** `ece4ab01-8424-4908-a0ba-5c09fa9936d4`
- **Created:** 17 October 2026, 15:37 UTC
- **Last updated:** 17 October 2026, 15:59 UTC
- **Turns:** 5
- **Status:** Complete
