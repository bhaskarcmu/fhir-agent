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

<details>
<summary>Execution details — 5 tool events</summary>

### Turn 1 activity

- **Bash** `cd /workspaces/fhir-agent; ls docs 2>/dev/null; grep -rhoiE "phase ?[0-9]+" --include=*.md . | tr 'A-Z' 'a-z' | tr -d ' ' | sort | uniq -c | sort -k2 -V; git branch -a | grep -i phase`

### Turn 2 activity

- **Write** `/home/vscode/.claude/projects/-workspaces-fhir-agent/memory/phase8-ml-outcome-prediction.md`
- **Bash** `cd /home/vscode/.claude/projects/-workspaces-fhir-agent/memory; echo "- [Phase 8 ML outcome prediction](phase8-ml-outcome-prediction.md) — new service, RiskAssessment output; decided 2026-10-17" >> ME…`

### Turn 4 activity

- **Bash** `mkdir -p /tmp/claude-1000/-workspaces-fhir-agent/ece4ab01-8424-4908-a0ba-5c09fa9936d4/scratchpad/phase8-handoff`
- **Write** `/tmp/claude-1000/-workspaces-fhir-agent/ece4ab01-8424-4908-a0ba-5c09fa9936d4/scratchpad/phase8-handoff/01_PRD.md`

</details>

---

## Archive metadata

- **Source:** Claude Code
- **Session ID:** `ece4ab01-8424-4908-a0ba-5c09fa9936d4`
- **Created:** 17 October 2026, 15:37 UTC
- **Last updated:** 17 October 2026, 15:57 UTC
- **Turns:** 4
- **Status:** Complete
