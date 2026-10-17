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

## Turn 6

### Prompt

<pasted_content id="62de">
# Developer Notes: Reproducing and Extending the Hospitalization Risk Prototype

Version: 0.1
Date: October 16, 2026
For: Claude Code in a new session, inside an Ona (Gitpod) workspace with VS Code.
Read first: `01_PRD.md` (what and why), `02_Preliminary_Design.md` (how it fits together).

This file is self-contained. It lists every step taken in the original session, the exact URLs, the problems hit and how they were solved, the expected outputs, and the full source code of every working script (Appendix A).

---

## 1. Ground rules for Claude Code

1. Never commit raw data (`*.dta`, `*.zip`, Synthea output) or model binaries. Add them to `.gitignore` first.
2. Never send real patient data to any LLM or online service. MEPS public files and Synthea data are fine.
3. Reproduce the prototype numbers before changing any logic (PRD section 11 has tolerances).
4. Do not claim exact MEPS variable names you have not verified in a file. Use `inspect_meps.py` to check.
5. Keep year 1 features and year 2 label strictly separate. No year 2 variable may become a feature.
6. Writing style for docs in this repo: plain sentences, no em dashes or long dashes, no emojis.

## 2. Environment

The original session used:

| Item | Version |
|---|---|
| Python | 3.14.3 |
| pandas | 3.0.6 |
| scikit-learn | 1.9.1 |
| numpy | 2.5.4 |
| Java (for Synthea only) | Eclipse Temurin 17 JRE |

Python 3.12 or later with pandas 2.2 or later and scikit-learn 1.5 or later should also work. Pin whatever versions you use in `pyproject.toml` and record them in model metadata. Pickled models are not portable across scikit-learn versions; always retrain rather than copying a `.pkl` between environments.

Setup commands:

```bash
python -m pip install pandas numpy scikit-learn
# Optional, only for the API phase:
python -m pip install fastapi uvicorn pydantic
```

Environment quirks found in the original session:

- No `unzip` binary. Use Python `zipfile`.
- No `pyarrow`, so `to_parquet` failed. Use CSV, or install pyarrow.
- No Java. A JRE was downloaded from Adoptium (section 6.1).
- Background processes started with `&` or `nohup` were killed when the shell command ended. Run Synthea in the foreground with a timeout. In Ona this is not usually a problem, but foreground is safer.

## 3. Step-by-step reproduction

All prototype scripts live in two folders: `meps/` and `synthea/`. Copy the code from Appendix A into these paths. Run commands from inside the folder shown.

| Step | Folder | Command | Expected output |
|---|---|---|---|
| 1. Build MEPS dataset | `meps/` | `python build_meps_hosp12.py` | `(56360, 31) events: 4820 rate: 0.086` |
| 2. Variable dictionary | `meps/` | `python inspect_meps.py h252.dta h252_dictionary.csv` | `2648 variables ...` and `{'int8': 1603, 'int16': 611, 'int32': 383, 'float64': 25, 'str2': 21, 'str3': 2, 'str9': 2, 'str10': 1}` |
| 3. Train and save model | `meps/` | `python train_model.py` | `temporal test AUROC 0.769` and the 25-feature list |
| 4. Full evaluation | `meps/` | `python evaluate_model.py` | See section 5 |
| 5. Get Java and Synthea | `synthea/` | See section 6.1 | `synthea.jar` runs `-h` |
| 6. Generate synthetic patients | `synthea/` | See section 6.2 | `You've just generated 3712 patients!` |
| 7. Convert to MEPS schema | `synthea/` | `python ehr_to_meps.py az/csv 2023 az_meps_2023.csv` | `2913 adults, year1=2023, hospitalized in year2: 138 (4.7%)` |
| 8. Score with MEPS model | `synthea/` | `python score.py ../meps/meps_hosp12_model.pkl az_meps_2023.csv az_scored.csv` | `scored 2913 / mean risk 0.105 / actual rate 0.047 / AUROC 0.656` |

Step 1 downloads about 40 MB on first run and caches `h*.dta` next to the script. Steps 6 to 8 depend on the Synthea version (the `master-branch-latest` jar changes over time), so exact counts may differ. Treat them as sanity checks, not exact targets.

## 4. MEPS facts you need

### 4.1 Files and URLs

URL pattern for Stata files: `https://meps.ahrq.gov/data_files/pufs/h{n}/h{n}dta.zip` (the zip contains `h{n}.dta`). Documentation pages: `https://meps.ahrq.gov/data_stats/download_data/pufs/h{n}/h{n}doc.shtml`.

Note: `https://meps.ahrq.gov/data_files/pufs/h252dta.zip` (without the folder) returns 404. Use the folder form.

| Panel | Years | File | Persons in file | Adults kept | Events |
|---|---|---|---|---|---|
| 21 | 2016 to 2017 | HC-202 | 15,617 | 11,174 | 880 |
| 22 | 2017 to 2018 | HC-210 | 14,541 | 10,613 | 940 |
| 23 | 2018 to 2019 | HC-217 | 14,067 | 10,447 | 989 |
| 24 | 2019 to 2020 | HC-225 | 9,797 | 7,533 | 592 |
| 25 | 2020 to 2021 | HC-234 | 6,078 | 4,730 | 377 |
| 26 | 2021 to 2022 | HC-244 | 6,741 | 5,350 | 453 |
| 27 | 2022 to 2023 | HC-252 | 8,292 | 6,513 | 589 |

HC-245 is a Panel 24 three-year file (5,565 persons). It looks like a longitudinal file and has `IPDISY2`, but it duplicates Panel 24 people. Exclude it.

2022 event files checked in the session (each also a `h{n}dta.zip`):

| File | Content | Rows | Columns |
|---|---|---|---|
| HC-241 | 2022 Medical Conditions | 83,173 | 33 |
| HC-239A | 2022 Prescribed Medicines | 232,605 | 65 |
| HC-239D | 2022 Hospital Inpatient Stays | 1,933 | 50 |
| HC-239G | 2022 Office-Based Visits | 151,263 | 46 |
| HC-239I | 2022 condition-event link file | not downloaded | |
| HC-239B, C, E, F, H | dental, other medical, ER, outpatient, home health | not downloaded | |

For other years, find file numbers on the [MEPS data files page](https://meps.ahrq.gov/mepsweb/data_stats/download_data_files.jsp). Do not guess file numbers; verify each by downloading and checking `PANEL` or the year in variable labels.

### 4.2 Variable naming

- Suffix `Y1` = year 1 of the panel, `Y2` = year 2. Example: `IPDISY1`, `IPDISY2`.
- Suffix digits `1` to `5` = interview round. Example: `RTHLTH1` (round 1), `ADBMI2` (round 2), `OFTSMK3` (round 3).
- Suffix `X` = edited or imputed. `_M18` = question modified in 2018. Example: `DIABDXY1_M18`.
- Rounds 1 to 3 cover year 1, but round 3 ends in year 2 for almost everyone: in HC-252, 6,518 of 6,546 adults had round 3 end in 2023, mostly January to April. Treat round 3 items as possible leakage.
- Self-administered questionnaire (SAQ) items are round 2 and have about 63% to 67% valid values among adults (BMI `ADBMI2`, K6 `K6SUM2`, VR-12 `VPCS2`). Diabetes care items (prefix `DS`, round 3) have very few valid values, for example 350 adults for `DSA1C3` in HC-252.

### 4.3 Coding

| Pattern | Meaning |
|---|---|
| Yes or no | 1 = yes, 2 = no. Not 0 and 1. Recode. |
| Exceptions | `DIED`, `INST`: 0 = no, 1 = yes |
| Missing codes | -1 inapplicable, -2 determined in previous round, -7 refused, -8 don't know, -9 not ascertained, -15 cannot be computed |
| Strings | Missing is the string `-15` (for example in `ICD10CDX`) |
| Income | Can be truly negative (business losses). Do not treat as missing. |
| Age | Top-coded at 85 |
| Money | Person totals are int32 whole dollars; event-level money is float64 dollars and cents. MEPS money is payments, not charges. |

Value labels in Stata files: 2,622 of 2,648 HC-252 variables have value labels, including counts and amounts, because labels describe the negative codes.

### 4.4 Storage types (from the Stata files)

| File | Storage counts |
|---|---|
| HC-252 | 1,603 int8, 611 int16, 383 int32, 25 float64, 26 strings |
| HC-241 | 20 int8, 4 int16, 1 float64, 8 strings |
| HC-239A | 20 int8, 20 int16, 1 int32, 13 float64, 11 strings |
| HC-239D | 12 int8, 6 int16, 1 int32, 27 float64, 4 strings |
| HC-239G | 23 int8, 6 int16, 1 int32, 13 float64, 3 strings |

Key strings: `DUPERSID` str10; `CONDIDX` str13; `EVNTIDX` str16; `RXRECIDX` str19; `LINKIDX` str16; `DRUGIDX` str13; `ICD10CDX` declared str8 but always 3 characters (281 distinct in 2022); `CCSR1X` to `CCSR4X` str6 (for example `CIR007`); `RXNDC` str11 with leading zeros (8,649 distinct); `RXNAME` str50 (1,585 distinct, abbreviated); `RXDRGNAM` str60 (max 47 used); `RXFORM`, `RXFRMUNT`, `RXSTRENG`, `RXSTRUNT` str50 (short codes; strength is text). Multum classes `TC1`, `TC1S1`, `TC1S1_1` are int16 codes.

Reading storage types: pandas `StataReader` exposes them through the private attributes `_typlist` and `_lbllist` after `read()`. Codes: `b` int8, `h` int16, `l` int32, `f` float32, `d` float64, an integer N means strN. See `inspect_meps.py`.

### 4.5 No free text

MEPS public files contain no free text. The longest strings are IDs and drug names. Condition verbatims were coded to ICD-10 by AHRQ coders and not released. "Other (specify)" answers appear only as code 91. Text methods such as sentiment analysis do not apply. TF-IDF can be applied to bags of codes (ICD-10 3-character, CCSR, NDC) if useful.

## 5. Expected evaluation output (step 4)

```
n_train 44497 n_test 11863 events_test 1042 rate 0.0878
baseline: AUROC 0.708 [0.691,0.725] AUPRC 0.225 [0.206,0.250] Brier 0.0751 meanpred 0.0902 top10 PPV/sens 0.266 0.303 top5 0.331 0.188 top20 0.202 0.460
gbm: AUROC 0.769 [0.754,0.786] AUPRC 0.265 [0.242,0.290] Brier 0.0725 meanpred 0.0917 top10 PPV/sens 0.293 0.333 top5 0.383 0.218 top20 0.231 0.525
weighted AUROC 0.78 Brier null 0.0801
Calibration deciles (pred / actual): 0.016/0.008, 0.023/0.013, 0.034/0.025, 0.045/0.041, 0.056/0.056,
                                     0.071/0.072, 0.089/0.095, 0.117/0.107, 0.162/0.169, 0.304/0.292
18-44 4362 193 rate 0.044 AUROC 0.761 meanpred 0.054
45-64 3965 273 rate 0.069 AUROC 0.739 meanpred 0.079
65+ 3536 576 rate 0.163 AUROC 0.695 meanpred 0.152
male AUROC 0.794 rate 0.070
female AUROC 0.743 rate 0.103
no prior hosp: n 10972 rate 0.073 AUROC 0.744
prior hosp: n 891 rate 0.273 AUROC 0.694
Permutation importance (top): agey1x 0.0397, sex 0.0165, rxtoty1 0.0123, hibpdx 0.0057, obtotvy1 0.0057,
  ipngtdy1 0.0054, totexpy1 0.0053, ertoty1 0.0045, povcaty1 0.0045, arthdx 0.0024
```

Childbirth check (all panels): hospitalization rate by sex for ages 18 to 44 is 2.2% men vs 7.4% women; 45 to 64 is 7.4% vs 7.6%; 65 and older is 16.0% vs 16.0%.

Comparison model fitted on panels 21 to 25: intercept -4.047, age 0.0280, prior stay 1.3055. Predicted risks: age 30 without/with prior stay 3.9%/13.0%; 50: 6.6%/20.7%; 70: 11.0%/31.4%; 85: 15.9%/41.0%.

## 6. Synthea

### 6.1 Install

```bash
# Java 17 JRE (no root needed)
curl -sSL -o /tmp/jre.tgz "https://api.adoptium.net/v3/binary/latest/17/ga/linux/x64/jre/hotspot/normal/eclipse"
mkdir -p ~/jre && tar xzf /tmp/jre.tgz -C ~/jre
export JAVA=$(ls -d ~/jre/*/bin)/java

# Synthea jar (about 197 MB)
cd synthea
curl -sSL -o synthea.jar https://github.com/synthetichealth/synthea/releases/download/master-branch-latest/synthea-with-dependencies.jar
$JAVA -jar synthea.jar -h
```

In an Ona dev container, prefer adding a Java 17 feature to `.devcontainer/devcontainer.json` instead.

For reproducibility, consider pinning a tagged release (for example v3.x) instead of `master-branch-latest`, and record the version used.

### 6.2 Generate

```bash
cd synthea
timeout 1500 $JAVA -Xmx6g -jar synthea.jar -s 42 -p 3000 -a 18-90 -e 20241231 \
  --exporter.baseDirectory=./az/ --exporter.csv.export=true \
  --exporter.fhir.export=false --exporter.hospital.fhir.export=false \
  --exporter.practitioner.fhir.export=false Arizona > az.log 2>&1
```

Took about 10 minutes for 3,712 records (Synthea reports more than `-p` because it also writes deceased patients). Output CSVs land in `az/csv/`. The small public sample (`https://synthetichealth.github.io/synthea-sample-data/downloads/latest/synthea_sample_data_csv_latest.zip`, 108 patients, Massachusetts) is useful as a quick test fixture.

### 6.3 Synthea format facts

- Conditions, encounter reasons, procedures: SNOMED CT. Medications: RxNorm. Observations: LOINC. Immunizations: CVX. No ICD-10 in CSV export.
- Encounter classes seen: ambulatory, wellness, outpatient, emergency, urgentcare, home, inpatient, snf, hospice, virtual.
- Dates are ISO 8601 with time zone (UTC). Convert to time-zone-naive before comparing with naive timestamps, or pandas raises `Cannot compare tz-naive and tz-aware`.
- `patients.csv` has `INCOME` and `STATE`; no household size.
- `payers.csv` `OWNERSHIP` is GOVERNMENT, PRIVATE or NO_INSURANCE. Payers include Medicare, Medicaid, Dual Eligible and private brands.
- Data dictionary: [Synthea CSV File Data Dictionary](https://github.com/synthetichealth/synthea/wiki/CSV-File-Data-Dictionary).

### 6.4 ETL lessons

- Bug found: the pattern `coronary` matched "Abnormal findings diagnostic imaging heart+coronary circulat (finding)". Fixed to `ischemic heart disease|coronary artery`. Keep a unit test for it.
- Even after the fix, 25.1% of Synthea adults have coronary heart disease vs 5.6% in MEPS. This is the simulator, not the mapping.
- Other large mismatches (MEPS vs Synthea): median spending $1,728 vs $15,082 (payments vs charges); mean prescription fills 12.6 vs 33.8; arthritis 27% vs 12%; asthma 13% vs 4%; any home health 4.4% vs 0.4%; year-1 hospitalization 7.9% vs 4.7%.
- Dropping spending, prescriptions and home health changed Synthea AUROC only slightly (0.651 to 0.673) and did not change MEPS AUROC (0.766 to 0.768).
- Synthea AUROC says nothing about real-world accuracy.

## 7. Phase 1 task list for Claude Code

1. Create the repo layout in `02_Preliminary_Design.md` section 5, with `.gitignore` covering `data/`, `*.dta`, `*.zip`, `*.pkl`, `synthea/az/`, `synthea.jar`.
2. Add the dev container: Python 3.12+, Java 17.
3. Copy Appendix A scripts into `meps/` and `synthea/` as-is. Run steps 1 to 8 in section 3. Confirm numbers against sections 3 and 5.
4. Refactor into `src/hosprisk/` modules with a CLI or Makefile targets, keeping logic identical. Re-run and confirm numbers again.
5. Make evaluation write `reports/metrics.json` and `reports/model_report.md`.
6. Write tests listed in design section 7, including the `coronary` regression test and a tiny committed Synthea fixture.
7. Add GitHub Actions CI that runs unit tests and the tiny end-to-end test (do not download all of MEPS in CI unless cached).
8. Regenerate `docs/MEPS_feature_inventory.md` from the dictionary output and the AHRQ documentation pages, verifying every variable name you list.

## 8. Phase 2 and later pointers

- Unplanned-stay label: use yearly Hospital Inpatient Stays files (HC-239D for 2022 and equivalents for other years). `RSNINHOS` codes: 1 operation or surgery, 2 treatment or therapy, 3 diagnostic tests only, 4 give birth (mother), 5 to be born (baby), 6 pregnancy-related complications, 91 other. `EMERROOM` 1 = stay began in ER. Dates are month and year only (`IPBEGMM`, `IPBEGYR`). Link stays to people with `DUPERSID`, and use the year-2 calendar year's file for each panel.
- Condition features: Medical Conditions file `ICD10CDX` (3 characters) and `CCSR1X` to `CCSR4X`. About 10% of codes are suppressed as `-15`. Only conditions linked to an event that year are included.
- Drug features: Prescribed Medicines `RXNDC`, `TC1`, `TC1S1`, `TC1S1_1`, `RXDAYSUP` (999 = as needed; missing not imputed). Multum classes changed over years; check when pooling.
- Event files are yearly. For panel P with year 1 = Y, use year-Y event files filtered to `PANEL == P`.
- Tuning: use panel-grouped cross-validation within panels 21 to 25. Keep 26 to 27 untouched as the test set.
- For production code lists: [NLM SNOMED CT to ICD-10-CM map](https://www.nlm.nih.gov/research/umls/mapping_projects/snomedct_to_icd10cm.html) (UMLS license, free in the US). [CMS Synthetic RIF](https://data.cms.gov/sites/default/files/2023-05/d51e1218-68c3-4c7c-9598-0b81f22fe903/User%20Guide%20-%20CMS%20Synthetic%20RIF%20Files%20May%202023_AM508_v2.pdf) offers synthetic claims with ICD-10-CM, HCPCS and NDC for testing a claims adapter.

## 9. Reference URLs used in the session

| Topic | URL |
|---|---|
| MEPS home | https://meps.ahrq.gov |
| MEPS data files list | https://meps.ahrq.gov/mepsweb/data_stats/download_data_files.jsp |
| HC-252 documentation | https://meps.ahrq.gov/data_stats/download_data/pufs/h252/h252doc.shtml |
| HC-241 conditions documentation | https://meps.ahrq.gov/data_stats/download_data/pufs/h241/h241doc.shtml |
| HC-239A prescriptions documentation | https://meps.ahrq.gov/data_stats/download_data/pufs/h239a/h239adoc.shtml |
| HC-239D hospital stays documentation | https://meps.ahrq.gov/data_stats/download_data/pufs/h239d/h239ddoc.shtml |
| HC-239G office visits documentation | https://meps.ahrq.gov/data_stats/download_data/pufs/h239g/h239gdoc.shtml |
| MEPS conditions coding (ICD-10, CCSR) | https://meps.ahrq.gov/data_files/publications/mr36/mr36ug.shtml |
| MEPS DUA wording example | https://meps.ahrq.gov/data_stats/download_data/pufs/h213d/h213ddoc.shtml |
| Synthea repo | https://github.com/synthetichealth/synthea |
| Synthea licensing of data | https://github.com/synthetichealth/synthea/wiki/DPG |
| Synthea CSV dictionary | https://github.com/synthetichealth/synthea/wiki/CSV-File-Data-Dictionary |
| QAdmissions benchmark | https://bmjopen.bmj.com/content/3/8/e003482 |
| FDA CDS guidance | https://www.fda.gov/media/109618/download |
| AHRQ Community-Level Health Database | https://www.ahrq.gov/data/innovations/clh-data.html |
| CDC PLACES | https://www.cdc.gov/places/about/index.html |

---

# Appendix A: Prototype source code

These are the exact scripts that produced the results above. Place them at the paths shown.


## A.1 `meps/build_meps_hosp12.py`

```python
"""Build a real, de-identified 12-month hospitalization dataset from MEPS
two-year longitudinal panels (AHRQ, U.S. civilian noninstitutionalized population).

Design: features from calendar year 1 of each panel, label = any inpatient
discharge in calendar year 2 (a true 12-month prospective window).
Only ICD-10-era panels (2016+) are used.

Source: https://meps.ahrq.gov  (free download, no registration).
Read the MEPS Data Use Agreement before any commercial use.
"""
import io, zipfile, urllib.request
from pathlib import Path
import pandas as pd

# panel -> MEPS longitudinal file number (two-year files only)
PANELS = {21: 202, 22: 210, 23: 217, 24: 225, 25: 234, 26: 244, 27: 252}
BASE = "https://meps.ahrq.gov/data_files/pufs/h{n}/h{n}dta.zip"
DATA = Path(__file__).parent

CORE = ["DUPERSID", "PANEL", "SEX", "RACETHX", "REGIONY1", "AGEY1X", "INSCOVY1",
        "POVCATY1", "IPDISY1", "IPNGTDY1", "ERTOTY1", "OBTOTVY1", "OPTOTVY1",
        "HHTOTDY1", "RXTOTY1", "TOTEXPY1", "IPDISY2", "LONGWT", "VARSTR", "VARPSU"]
# self-reported "ever diagnosed" flags; names drift slightly by year, resolved by prefix
DX = ["HIBPDX", "CHDDX", "ANGIDX", "MIDX", "OHRTDX", "STRKDX", "EMPHDX",
      "DIABDX", "ARTHDX", "ASTHDX", "CHOLDX"]


def load_panel(panel: int, n: int) -> pd.DataFrame:
    dta = DATA / f"h{n}.dta"
    if not dta.exists():
        raw = urllib.request.urlopen(BASE.format(n=n)).read()
        zipfile.ZipFile(io.BytesIO(raw)).extract(f"h{n}.dta", DATA)
    df = pd.read_stata(dta, convert_categoricals=False)
    out = df[CORE].copy()
    for d in DX:
        src = sorted(c for c in df.columns if c.startswith(d) and "Y1" in c)[0]
        out[d.lower()] = (df[src] == 1).astype(int)
    return out


def build() -> pd.DataFrame:
    df = pd.concat([load_panel(p, n) for p, n in PANELS.items()], ignore_index=True)
    # adults present and observed in both years (negative values are MEPS missing codes)
    df = df[(df.AGEY1X >= 18) & (df.IPDISY1 >= 0) & (df.IPDISY2 >= 0)].copy()
    df["label_hosp_12m"] = (df.IPDISY2 > 0).astype(int)
    df = df.drop(columns=["IPDISY2"])
    df.columns = [c.lower() for c in df.columns]
    return df


if __name__ == "__main__":
    t = build()
    t.to_csv(DATA / "meps_hosp12.csv", index=False)
    print(t.shape, "events:", int(t.label_hosp_12m.sum()),
          f"rate: {t.label_hosp_12m.mean():.3f}")
```

## A.2 `meps/inspect_meps.py`

```python
"""Dump every variable in a MEPS Stata file with label, storage type, value range,
missing codes, value labels and string lengths. Used to build the feature inventory
and the data-types reference.

Usage: python inspect_meps.py h252.dta h252_dictionary.csv
"""
import sys
import pandas as pd
from pandas.io.stata import StataReader

STORAGE = {'b': 'int8', 'h': 'int16', 'l': 'int32', 'f': 'float32', 'd': 'float64'}
src, out = sys.argv[1], sys.argv[2]
with StataReader(src) as r:
    df = r.read(convert_categoricals=False)
    types = dict(zip(r._varlist, r._typlist))      # private attrs: stable in pandas 2.x and 3.x
    lblnames = dict(zip(r._varlist, r._lbllist))
    vlabels = r.value_labels()
    vlab = r.variable_labels()
rows = []
for v in df.columns:
    t = types[v]
    st = STORAGE.get(t, f"str{t}") if not isinstance(t, int) else f"str{t}"
    s = df[v]
    row = {'variable': v, 'label': vlab.get(v, ''), 'storage': st}
    if st.startswith('str'):
        x = s.dropna().astype(str); x = x[x.str.len() > 0]
        row.update(max_len=int(x.str.len().max()) if len(x) else 0, n_unique=int(x.nunique()),
                   examples='; '.join(map(str, x.unique()[:5])))
    else:
        pos, neg = s[s >= 0], sorted(s[s < 0].unique().tolist())
        row.update(min=pos.min() if len(pos) else None, max=pos.max() if len(pos) else None,
                   n_unique=int(pos.nunique()), negative_codes=' '.join(map(str, neg[:8])))
        vl = vlabels.get(lblnames.get(v, ''), {})
        row['value_labels'] = '; '.join(f"{k}={lab}" for k, lab in vl.items() if k >= 0)[:500]
    rows.append(row)
pd.DataFrame(rows).to_csv(out, index=False)
print(f"{len(rows)} variables written to {out}")
print(pd.DataFrame(rows).storage.value_counts().to_dict())
```

## A.3 `meps/train_model.py`

```python
"""Train the 12-month hospitalization model on MEPS and save it."""
import pandas as pd, numpy as np, pickle
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
t = pd.read_csv('meps_hosp12.csv')
CAT = ['sex','racethx','regiony1','inscovy1','povcaty1']
FEATS = [c for c in t.columns if c not in ('dupersid','panel','label_hosp_12m','longwt','varstr','varpsu')]
X = t[FEATS].copy()
for c in CAT: X[c] = X[c].clip(lower=0).astype(int)
tr, te = (t.panel <= 25).values, (t.panel >= 26).values
params = dict(max_iter=300, learning_rate=0.05, random_state=0,
              categorical_features=[FEATS.index(c) for c in CAT])
m = HistGradientBoostingClassifier(**params).fit(X[tr], t.label_hosp_12m[tr])
print('temporal test AUROC', round(roc_auc_score(t.label_hosp_12m[te], m.predict_proba(X[te])[:,1]),3))
final = HistGradientBoostingClassifier(**params).fit(X, t.label_hosp_12m)   # all panels for deployment
pickle.dump({'model': final, 'features': FEATS, 'categorical': CAT}, open('meps_hosp12_model.pkl','wb'))
print('features', FEATS)
```

## A.4 `meps/evaluate_model.py`

```python
"""Detailed evaluation of the MEPS 12-month hospitalization model on held-out panels 26-27."""
import pandas as pd, numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.inspection import permutation_importance
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
t = pd.read_csv('meps_hosp12.csv')
CAT = ['sex','racethx','regiony1','inscovy1','povcaty1']
F = [c for c in t.columns if c not in ('dupersid','panel','label_hosp_12m','longwt','varstr','varpsu')]
X = t[F].copy()
for c in CAT: X[c] = X[c].clip(lower=0).astype(int)
y = t.label_hosp_12m.values
tr, te = (t.panel <= 25).values, (t.panel >= 26).values
m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, random_state=0,
        categorical_features=[F.index(c) for c in CAT]).fit(X[tr], y[tr])
p = m.predict_proba(X[te])[:, 1]; yt = y[te]; w = t.longwt.values[te]
B = np.c_[t.agey1x, t.ipdisy1 > 0]
pb = LogisticRegression(max_iter=1000).fit(B[tr], y[tr]).predict_proba(B[te])[:, 1]

rng = np.random.default_rng(0); idx = np.arange(len(yt))
def ci(f, *a):
    v = [f(*(x[s] for x in a)) for s in (rng.choice(idx, len(idx)) for _ in range(500))]
    return np.percentile(v, [2.5, 97.5])
def topk(yy, pp, q=0.10):
    k = int(len(yy) * q); o = np.argsort(-pp)[:k]; return yy[o].mean(), yy[o].sum() / yy.sum()
print("n_train", tr.sum(), "n_test", te.sum(), "events_test", yt.sum(), f"rate {yt.mean():.4f}")
for name, pp in [("baseline", pb), ("gbm", p)]:
    a = roc_auc_score(yt, pp); lo, hi = ci(roc_auc_score, yt, pp)
    ap = average_precision_score(yt, pp); alo, ahi = ci(average_precision_score, yt, pp)
    print(f"{name}: AUROC {a:.3f} [{lo:.3f},{hi:.3f}] AUPRC {ap:.3f} [{alo:.3f},{ahi:.3f}] Brier {brier_score_loss(yt,pp):.4f} meanpred {pp.mean():.4f}",
          "top10 PPV/sens %.3f %.3f" % topk(yt, pp), "top5 %.3f %.3f" % topk(yt, pp, .05), "top20 %.3f %.3f" % topk(yt, pp, .2))
print("weighted AUROC", round(roc_auc_score(yt, p, sample_weight=w), 3), "Brier null", round(brier_score_loss(yt, np.full_like(p, y[tr].mean())), 4))
d = pd.DataFrame({'y': yt, 'p': p}); d['dec'] = pd.qcut(d.p, 10, labels=False) + 1
print(d.groupby('dec').agg(n=('y','size'), pred=('p','mean'), actual=('y','mean')).round(3).to_string())
age = t.agey1x.values[te]
for lab, s in [("18-44", age < 45), ("45-64", (age >= 45) & (age < 65)), ("65+", age >= 65)]:
    print(lab, s.sum(), yt[s].sum(), f"rate {yt[s].mean():.3f} AUROC {roc_auc_score(yt[s], p[s]):.3f} meanpred {p[s].mean():.3f}")
sx = t.sex.values[te]
for lab, s in [("male", sx == 1), ("female", sx == 2)]:
    print(lab, f"AUROC {roc_auc_score(yt[s], p[s]):.3f} rate {yt[s].mean():.3f}")
prior = t.ipdisy1.values[te] > 0
print("no prior hosp: n", (~prior).sum(), f"rate {yt[~prior].mean():.3f} AUROC {roc_auc_score(yt[~prior], p[~prior]):.3f}")
print("prior hosp: n", prior.sum(), f"rate {yt[prior].mean():.3f} AUROC {roc_auc_score(yt[prior], p[prior]):.3f}")
pi = permutation_importance(m, X[te], yt, scoring='roc_auc', n_repeats=5, random_state=0)
imp = pd.Series(pi.importances_mean, index=F).sort_values(ascending=False)
print((imp).round(4).to_string())
```

## A.5 `synthea/ehr_to_meps.py`

```python
"""Convert Synthea CSV medical records into the MEPS feature schema used by
the 12-month hospitalization model (meps/train_model.py).

Year 1 (feature year) = calendar year Y. Year 2 (label year) = Y + 1.
The same logic applies to real EHR or claims data once their codes are mapped
(see the mapping notes in EHR_to_MEPS_mapping.md).

Usage: python ehr_to_meps.py <synthea_csv_dir> <year1> <out.csv>
"""
import sys
import numpy as np
import pandas as pd

SRC, Y = sys.argv[1], int(sys.argv[2])
OUT = sys.argv[3]
Y1_START, Y1_END = pd.Timestamp(f"{Y}-01-01"), pd.Timestamp(f"{Y}-12-31 23:59:59")
Y2_START, Y2_END = pd.Timestamp(f"{Y+1}-01-01"), pd.Timestamp(f"{Y+1}-12-31 23:59:59")

pat = pd.read_csv(f"{SRC}/patients.csv")
enc = pd.read_csv(f"{SRC}/encounters.csv", parse_dates=["START", "STOP"])
con = pd.read_csv(f"{SRC}/conditions.csv", parse_dates=["START"])
med = pd.read_csv(f"{SRC}/medications.csv", parse_dates=["START", "STOP"])
ptr = pd.read_csv(f"{SRC}/payer_transitions.csv", parse_dates=["START_DATE", "END_DATE"])
pay = pd.read_csv(f"{SRC}/payers.csv")
for df in (enc, con, med, ptr):                 # drop time zones so all dates compare cleanly
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]) and getattr(df[c].dt, "tz", None) is not None:
            df[c] = df[c].dt.tz_localize(None)

# ---------- population: adults alive on 12/31 of year 1, alive or dead in year 2 ----------
pat["BIRTHDATE"] = pd.to_datetime(pat.BIRTHDATE)
pat["DEATHDATE"] = pd.to_datetime(pat.DEATHDATE)
ref = pd.Timestamp(f"{Y}-12-31")
pat = pat[(pat.BIRTHDATE <= ref) & (pat.DEATHDATE.isna() | (pat.DEATHDATE > ref))].copy()
age = ((ref - pat.BIRTHDATE).dt.days / 365.25).astype(int)
pat["agey1x"] = age.clip(upper=85)                         # MEPS top-codes age at 85
pat = pat[pat.agey1x >= 18]
out = pd.DataFrame({"person_id": pat.Id.values, "agey1x": pat.agey1x.values})

# ---------- demographics ----------
out["sex"] = pat.GENDER.map({"M": 1, "F": 2}).values      # MEPS: 1 male, 2 female
def racethx(r, e):                                          # MEPS RACETHX codes
    if e == "hispanic": return 1
    return {"white": 2, "black": 3, "asian": 4}.get(r, 5)
out["racethx"] = [racethx(r, e) for r, e in zip(pat.RACE, pat.ETHNICITY)]
WEST = {"Arizona", "California", "Colorado", "Idaho", "Montana", "Nevada", "New Mexico", "Utah",
        "Wyoming", "Alaska", "Hawaii", "Oregon", "Washington"}
NE = {"Connecticut", "Maine", "Massachusetts", "New Hampshire", "Rhode Island", "Vermont",
      "New Jersey", "New York", "Pennsylvania"}
MW = {"Illinois", "Indiana", "Michigan", "Ohio", "Wisconsin", "Iowa", "Kansas", "Minnesota",
      "Missouri", "Nebraska", "North Dakota", "South Dakota"}
out["regiony1"] = [4 if s in WEST else 1 if s in NE else 2 if s in MW else 3 for s in pat.STATE]

# Poverty category from income. Household size is unknown in Synthea, so a
# 1-person household is assumed (2023 HHS poverty guideline, 48 states: $14,580).
FPL = {2022: 13590, 2023: 14580, 2024: 15060}.get(Y, 14580)
pct = pat.INCOME.values / FPL * 100
out["povcaty1"] = np.select([pct < 100, pct < 125, pct < 200, pct < 400], [1, 2, 3, 4], 5)

# ---------- insurance during year 1 (MEPS INSCOVY1: 1 any private, 2 public only, 3 uninsured) ----------
own = dict(zip(pay.Id, pay.OWNERSHIP.str.upper()))
p1 = ptr[(ptr.START_DATE <= ref) & (ptr.END_DATE.isna() | (ptr.END_DATE >= pd.Timestamp(f"{Y}-01-01")))].copy()
p1["own"] = p1.PAYER.map(own)
def inscov(s):
    s = set(s)
    if "PRIVATE" in s: return 1
    if "GOVERNMENT" in s: return 2
    return 3
ins = p1.groupby("PATIENT").own.apply(inscov)
out["inscovy1"] = out.person_id.map(ins).fillna(3).astype(int)

# ---------- utilization in year 1 ----------
e1 = enc[(enc.START >= Y1_START) & (enc.START <= Y1_END)]
def count(cls):
    return out.person_id.map(e1[e1.ENCOUNTERCLASS.isin(cls)].groupby("PATIENT").size()).fillna(0).astype(int)
ip1 = e1[e1.ENCOUNTERCLASS == "inpatient"].copy()
ip1["nights"] = ((ip1.STOP - ip1.START).dt.total_seconds() / 86400).round().clip(lower=0)
out["ipdisy1"] = out.person_id.map(ip1.groupby("PATIENT").size()).fillna(0).astype(int)
out["ipngtdy1"] = out.person_id.map(ip1.groupby("PATIENT").nights.sum()).fillna(0).astype(int)
out["ertoty1"] = count(["emergency"])
out["obtotvy1"] = count(["ambulatory", "wellness", "urgentcare", "virtual"])   # office-based incl. telehealth
out["optotvy1"] = count(["outpatient"])                                        # hospital outpatient dept
out["hhtotdy1"] = count(["home"])                                              # one home visit = one day

# Prescription fills in year 1: spread each prescription's dispenses evenly over its active period
m = med.copy()
m["STOP"] = m.STOP.fillna(Y2_END)
dur = (m.STOP - m.START).dt.total_seconds().clip(lower=86400)
ov = (np.minimum(m.STOP, Y1_END) - np.maximum(m.START, Y1_START)).dt.total_seconds().clip(lower=0)
m["fills_y1"] = m.DISPENSES * ov / dur
m["cost_y1"] = m.TOTALCOST * ov / dur
out["rxtoty1"] = out.person_id.map(m.groupby("PATIENT").fills_y1.sum()).fillna(0).round().astype(int)

# Total expenditure (MEPS = payments, here = claim cost) in whole dollars
cost = e1.groupby("PATIENT").TOTAL_CLAIM_COST.sum().add(m.groupby("PATIENT").cost_y1.sum(), fill_value=0)
out["totexpy1"] = out.person_id.map(cost).fillna(0).round().astype(int)

# ---------- "ever diagnosed" flags: any matching condition recorded by end of year 1 ----------
c1 = con[con.START <= pd.Timestamp(f"{Y}-12-31")]
desc = c1.DESCRIPTION.str.lower()
RULES = {   # SNOMED description patterns standing in for a SNOMED -> ICD-10-CM -> MEPS map
    "hibpdx": r"hypertension",
    "chddx":  r"ischemic heart disease|coronary artery",   # not "coronary" alone: it also matches imaging findings
    "angidx": r"angina",
    "midx":   r"myocardial infarction",
    "ohrtdx": r"heart failure|atrial fibrillation|cardiomyopathy|valve|arrhythmia",
    "strkdx": r"stroke|cerebrovascular accident|cerebral infarction",
    "emphdx": r"emphysema|chronic obstructive",
    "diabdx": r"(?<!pre)diabetes",
    "arthdx": r"arthritis|osteoarthritis",
    "asthdx": r"asthma",
    "choldx": r"hyperlipidemia|hypercholesterolemia|hypertriglyceridemia",
}
for col, pat_re in RULES.items():
    ids = set(c1.PATIENT[desc.str.contains(pat_re, regex=True)])
    out[col] = out.person_id.isin(ids).astype(int)

# ---------- label: any inpatient admission in year 2 ----------
ip2 = enc[(enc.ENCOUNTERCLASS == "inpatient") & (enc.START >= Y2_START) & (enc.START <= Y2_END)]
out["label_hosp_12m"] = out.person_id.isin(set(ip2.PATIENT)).astype(int)

out.to_csv(OUT, index=False)
print(f"{len(out)} adults, year1={Y}, hospitalized in year2: {out.label_hosp_12m.sum()} "
      f"({out.label_hosp_12m.mean():.1%})")
```

## A.6 `synthea/score.py`

```python
"""Score MEPS-schema rows (from ehr_to_meps.py) with the model trained on MEPS."""
import sys, pickle, pandas as pd, numpy as np
from sklearn.metrics import roc_auc_score
b = pickle.load(open(sys.argv[1], 'rb')); s = pd.read_csv(sys.argv[2])
X = s[b['features']].copy()
for c in b['categorical']: X[c] = X[c].astype(int)
s['risk_12m'] = b['model'].predict_proba(X)[:, 1]
s.to_csv(sys.argv[3], index=False)
y = s.get('label_hosp_12m')
print(f"scored {len(s)} | mean risk {s.risk_12m.mean():.3f}" + (f" | actual rate {y.mean():.3f} | AUROC {roc_auc_score(y, s.risk_12m):.3f}" if y is not None and y.nunique() > 1 else ""))
```

# Appendix B: Prompt to start Claude Code

Paste this as the first message in Claude Code, after placing the three documents in `docs/`:

> Read docs/01_PRD.md, docs/02_Preliminary_Design.md and docs/03_Developer_Notes.md in full. Then do Phase 1 from Developer Notes section 7. First copy the Appendix A scripts into meps/ and synthea/ unchanged and reproduce the expected outputs in sections 3 and 5. Report any number outside the PRD tolerances before changing code. Do not commit data or model binaries. Ask before any action that sends data outside this workspace.
</pasted_content id="62de">

### Claude response

I have all three parts, saved word for word in `/tmp/claude-1000/-workspaces-fhir-agent/ece4ab01-8424-4908-a0ba-5c09fa9936d4/scratchpad/phase8-handoff/`. Below is my review against your two decisions and this repo. Nothing has been written to the repo yet.

## Where the handoff conflicts with this repo

1. **Phase numbers clash.** The handoff calls its own stages Phase 0 to 4, while this repo already uses phase numbers up to 7. I'd turn them into milestones inside Phase 8 (M1 reproduce the prototype, M2 improve the model, M3 service and adapters, M4 deploy and recalibrate), the way Phases 6 and 7 do.
2. **It assumes its own standalone repo.** It plans a separate `hosp-risk/` repo with its own docs, dev container, Makefile and CI. Here that becomes:
   - one new top-level service folder (say `risk-model-service/`, name to be decided), laid out like `triage-service/`;
   - docs in `docs/phase8/`;
   - the existing dev container and `.github/workflows/tests.yml`, rather than new ones.
3. **The output format conflicts with your decision.** The handoff's `/v1/score` returns custom JSON. You chose FHIR `RiskAssessment`, like the one [triage-service/src/triage/main.py](triage-service/src/triage/main.py) returns. A possible mapping:
   - the risk goes in `prediction.probabilityDecimal`;
   - "hospital admission" is the predicted outcome, over a 12-month window;
   - the model ID goes in `method`;
   - `basis` points to the patient records used.

   The comparison-model risk, the percentile and the top reasons would need extensions or a second prediction entry. That is a design item to settle.
4. **The ETL ignores what the repo already has.** The handoff starts from Synthea CSV and leaves FHIR "for later." This repo already generates Synthea patients as FHIR records ([data/scripts/generate.sh](data/scripts/generate.sh)), stores them in `fhir-service`, and reads them through `client/clinical`. Converting FHIR records into the model's input should come first, not later. `claims-service` may be able to feed the claims adapter.
5. **The agent's role isn't covered.** The handoff never mentions the agent. Under the repo rule, the model and all transforms live in the new service, and `mcp-agent` only gets a tool that calls it. Adding a gateway route means changing infrastructure config, so I'll ask before doing that.

## Problems in the prototype

These need fixing when the prototype is turned into the service:

- **Future data leaks into the prescription count.** `ehr_to_meps.py` fills a missing medication stop date with the end of year 2, and it spreads `DISPENSES` over a period that runs past the cutoff. The prescription count therefore uses future data, which breaks the handoff's own rule that scoring must never see future data. This one matters most.
- **The comparison model is never saved.** `train_model.py` saves only the gradient boosting model, but the API must return the comparison-model score too (requirement FR-S2).
- **Unknown states default to the wrong region.** Unknown or non-US states map to South (3), but the feature contract says 0.
- **"Year 1" doesn't fit live scoring.** The model is built on calendar years. Scoring a patient on any given date needs a definition such as "the 12 months before the as-of date," and it isn't specified yet.
- **The reported metrics aren't the shipped model's.** The released model is retrained on all panels, so the reported numbers come from a different model object. The model's metadata should say so.

## What to settle before production (these don't block M1)

- **MEPS commercial use:** AHRQ still has to confirm this in writing. It's a legal question, not an engineering one.
- **Spending feature:** `totexpy1` can't be compared across sources, because MEPS records payments and medical records hold charges.
- **Clinical sign-off:** someone has to approve the clinical code lists.
- **Writing style:** the handoff bans em dashes in docs, but this repo's docs use them. I'll follow the repo unless you say otherwise.

## Proposed next step

On a feature branch, with a PR:

- Put the three files, unchanged, in `docs/phase8/handoff/` as your record. They contain no patient data.
- Write repo-format `docs/phase8/` documents (`README`, `prd`, `design`, `decisions`, `milestone-plan`) that pull in the handoff, your two decisions and the points above.

Should I go ahead?

## Turn 7

### Prompt

You mentioned 5 areas where the handoff conflicts with this repo. This existing repo conventions, with its 7 phases MUST be followed. I liked the suggestions I saw so far in your responses above, such as converting phases to milestones. Dig even deeper to resolve inconsistencies; prepare a docs PR with folder structure and codumenttion style matching the earlier phases in this repo

### Claude response

*[Claude has not completed this turn yet.]*

<details>
<summary>Execution details — 21 tool events</summary>

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

### Turn 6 activity

- **Bash** `cd /workspaces/fhir-agent; ls; ls docs/phase7 docs/phase6; ls .github/workflows 2>/dev/null; grep -n "requires-python" */pyproject.toml client/*/pyproject.toml 2>/dev/null; grep -rln "RiskAssessment"…`
- **Write** `/tmp/claude-1000/-workspaces-fhir-agent/ece4ab01-8424-4908-a0ba-5c09fa9936d4/scratchpad/phase8-handoff/03_Developer_Notes.md`
- **Bash** `cd /workspaces/fhir-agent; grep -n "RiskAssessment\|probability\|basis\|method\|prediction" triage-service/src/triage/main.py | head -30; echo ---; head -30 data/scripts/generate.sh; echo ---; ls clai…`

### Turn 7 activity

- **Bash** `cd /workspaces/fhir-agent; wc -l docs/phase*/*.md docs/README.md README.md; ls docs/phase2 docs/phase3 docs/phase4 docs/phase5; cat docs/README.md`
- **Bash** `cd /workspaces/fhir-agent; cat docs/phase7/README.md docs/phase7/decisions.md; head -30 docs/phase2/source-prd.md; head -40 docs/phase2/README.md`
- **Read** `/workspaces/fhir-agent/docs/phase7/prd.md`
- **Read** `/workspaces/fhir-agent/docs/phase7/milestone-plan.md`
- **Read** `/workspaces/fhir-agent/docs/phase7/design.md`
- **Bash** `cd /workspaces/fhir-agent; sed -n 1,200p triage-service/src/triage/models.py | grep -n "class\|: " | head -60; echo ---; ls client/clinical/src/*/ 2>/dev/null || find client/clinical -name "*.py" -not…`
- **Bash** `cd /workspaces/fhir-agent; sed -n 80,135p triage-service/src/triage/main.py; echo ---; grep -n "def \|class " client/clinical/src/fhir_clinical_client/fhir_client.py`
- **Bash** `cd /workspaces/fhir-agent; sed -n 42,111p client/clinical/src/fhir_clinical_client/fhir_client.py; sed -n 354,383p client/clinical/src/fhir_clinical_client/fhir_client.py`
- **Bash** `cd /workspaces/fhir-agent; ls .devcontainer 2>/dev/null && grep -n "image\|java\|python\|version" .devcontainer/devcontainer.json; echo ---; grep -n "name:\|run:\|pytest\|pip install" .github/workflow…`
- **Bash** `cd /workspaces/fhir-agent; grep -n "exporter\|csv\|fhir" data/scripts/generate.sh | head -20; echo ---; grep -n "^  [a-z].*:$" docker-compose.yml; echo ---; head -40 NOTICE; echo ---; ls mcp-agent/src…`
- **Bash** `cd /workspaces/fhir-agent; sed -n 36,90p .github/workflows/tests.yml; sed -n 120,200p .github/workflows/tests.yml | grep -n "name:\|run:\|pip\|pytest" ; grep -n "profiles" docker-compose.yml | head; g…`
- **Bash** `cd /workspaces/fhir-agent; grep -n "exporter" data/synthea/synthea.properties; echo ---; sed -n 1,30p triage-service/src/triage/main.py | grep -n import; cat triage-service/pyproject.toml | sed -n 1,4…`

</details>

---

## Archive metadata

- **Source:** Claude Code
- **Session ID:** `ece4ab01-8424-4908-a0ba-5c09fa9936d4`
- **Created:** 17 October 2026, 15:37 UTC
- **Last updated:** 17 October 2026, 16:09 UTC
- **Turns:** 7
- **Status:** Incomplete
