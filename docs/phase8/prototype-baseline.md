# Phase 8 Prototype Baseline — What the Research Prototype Established

The facts, method and numbers from the research prototype that seeded Phase 8, restated in
this repo's terms. This is the **reproduction target** for M1–M3 (`decisions.md` O6) and the
reference for MEPS and Synthea details. Where it describes the prototype's behaviour, it
describes what was built, not what to build: the contract is [`prd.md`](./prd.md) and
[`design.md`](./design.md), and known prototype defects are listed in `design.md` §11.

**Provenance.** The prototype was built in an earlier research session and handed over on
2026-10-17 as a draft PRD, a preliminary design and developer notes with source code. Those
raw documents are **not kept in this repo** (`decisions.md` O5): their content that matters is
here, in `prd.md` (requirements, with the original `FR-*` IDs) and in `design.md`. The repo
owner holds the originals.

---

## 1. Definitions

| Term | Definition |
|---|---|
| Label `label_hosp_12m` | 1 if the person had at least one inpatient discharge in calendar year 2 of their MEPS panel (`IPDISY2 > 0`), else 0 |
| Features | Calendar-year-1 information only |
| Year 1, year 2 | The two calendar years of a MEPS two-year longitudinal panel (Panel 27 = 2022, 2023) |
| AUROC | Probability a random hospitalized person ranks above a random non-hospitalized one; 0.5 is chance |
| AUPRC | Average precision; chance equals the event rate (~0.088) |
| Brier score | Mean squared error of predicted probabilities; lower is better |
| Top-k% PPV / sensitivity | Share hospitalized among the k% highest-risk; share of all events captured there |
| Calibration | Predicted vs observed rate, by risk decile |
| Comparison model | Logistic regression on age and any year-1 inpatient stay; shown beside the main score |

## 2. Data source choices

**Training and testing: MEPS** (AHRQ Medical Expenditure Panel Survey), two-year
longitudinal panels 21–27 (2016–2023). The only real, de-identified, free, US, person-level
data found with a true 12-month prospective outcome. ICD-10-era panels only.

**MEPS use terms are ambiguous for commercial use.** The data use wording says data "may not
be used for any purpose other than for the purpose for which they were supplied". Written
confirmation from AHRQ is outstanding (`decisions.md` O23). The intended business model sells
the platform (pipeline, calibration, retraining on customer data) rather than MEPS-trained
weights alone, which reduces dependence on the answer.

**Rejected:**

| Source | Why |
|---|---|
| CPRD (UK) | ~£20,600–£83,850 per year; public-health research use only |
| OpenSAFELY (UK) | UK-based users only; aggregate outputs only |
| UK data generally | US and UK coding and care patterns differ |
| MIMIC-IV and other credentialed sets | Approved access, restricted use; MIMIC's agreement bans sending data to online services such as LLM APIs |
| Health and Retirement Study | Research and statistical purposes only |
| MCBS public file | No utilization data, so no hospitalization label |

**Synthea** — pipeline and service testing only, never accuracy (outcomes are rule-simulated).
Software Apache 2.0; published synthetic data public domain.

**Code systems:** CPT not used (AMA licence). ICD-10-CM free in the US. SNOMED CT and the NLM
SNOMED CT → ICD-10-CM map free in the US with a UMLS licence.

**Regulatory posture:** a non-time-critical risk score shown to clinicians with its basis
visible — likely outside FDA device rules or under enforcement discretion per the FDA clinical
decision support guidance. Needs counsel's review before launch.

**Benchmark:** QAdmissions (UK) reports AUROC 0.77–0.78 and top-decile PPV of 42% for
*emergency* admission — a different outcome, so compare with care.

## 3. MEPS facts

### 3.1 Files

Stata files: `https://meps.ahrq.gov/data_files/pufs/h{n}/h{n}dta.zip` (contains `h{n}.dta`).
Documentation: `https://meps.ahrq.gov/data_stats/download_data/pufs/h{n}/h{n}doc.shtml`.
The folder-less form (`…/pufs/h252dta.zip`) returns 404. Extract with Python `zipfile`; don't
assume an `unzip` binary. First download is ~40 MB.

| Panel | Years | File | Persons in file | Adults kept | Events |
|---|---|---|---|---|---|
| 21 | 2016–2017 | HC-202 | 15,617 | 11,174 | 880 |
| 22 | 2017–2018 | HC-210 | 14,541 | 10,613 | 940 |
| 23 | 2018–2019 | HC-217 | 14,067 | 10,447 | 989 |
| 24 | 2019–2020 | HC-225 | 9,797 | 7,533 | 592 |
| 25 | 2020–2021 | HC-234 | 6,078 | 4,730 | 377 |
| 26 | 2021–2022 | HC-244 | 6,741 | 5,350 | 453 |
| 27 | 2022–2023 | HC-252 | 8,292 | 6,513 | 589 |
| **Total** | | | | **56,360** | **4,820 (8.6%)** |

**Exclude HC-245**: a Panel 24 three-year file (5,565 persons). It has `IPDISY2` and looks
like a longitudinal file, but duplicates Panel 24 people.

2022 event files examined (also `h{n}dta.zip`):

| File | Content | Rows | Columns |
|---|---|---|---|
| HC-241 | Medical Conditions | 83,173 | 33 |
| HC-239A | Prescribed Medicines | 232,605 | 65 |
| HC-239D | Hospital Inpatient Stays | 1,933 | 50 |
| HC-239G | Office-Based Visits | 151,263 | 46 |
| HC-239I | Condition-event link | not downloaded | |
| HC-239B/C/E/F/H | Dental, other medical, ER, outpatient, home health | not downloaded | |

For other years, look file numbers up on the MEPS data files page and verify each by
downloading and checking `PANEL` or the year in variable labels. Never guess a file number.

### 3.2 Variable naming

- `Y1` / `Y2` suffix: panel year 1 / year 2 (`IPDISY1`, `IPDISY2`).
- Trailing digit 1–5: interview round (`RTHLTH1`, `ADBMI2`, `OFTSMK3`).
- `X` suffix: edited or imputed. `_M18`: question modified in 2018 (`DIABDXY1_M18`).
- **Round 3 ends in year 2 for almost everyone** — in HC-252, 6,518 of 6,546 adults, mostly
  January–April. Treat round-3 items as possible leakage.
- Self-administered questionnaire items are round 2, ~63–67% valid among adults (`ADBMI2`,
  `K6SUM2`, `VPCS2`). Diabetes-care items (`DS*`, round 3) are sparse — e.g. 350 adults for
  `DSA1C3` in HC-252.

### 3.3 Coding

| Pattern | Meaning |
|---|---|
| Yes/no | 1 = yes, 2 = no (not 0/1) — recode |
| Exceptions | `DIED`, `INST`: 0 = no, 1 = yes |
| Missing | -1 inapplicable, -2 determined in previous round, -7 refused, -8 don't know, -9 not ascertained, -15 cannot be computed |
| Strings | Missing is the string `-15` (e.g. `ICD10CDX`) |
| Income | Can be truly negative (business losses) — not missing |
| Age | Top-coded at 85 |
| Money | Person totals int32 whole dollars; event-level float64. MEPS money is **payments**, not charges |

2,622 of 2,648 HC-252 variables carry value labels, including counts and amounts, because the
labels describe the negative codes.

### 3.4 Storage types

| File | Storage counts |
|---|---|
| HC-252 | 1,603 int8, 611 int16, 383 int32, 25 float64, 26 strings (21 str2, 2 str3, 2 str9, 1 str10) |
| HC-241 | 20 int8, 4 int16, 1 float64, 8 strings |
| HC-239A | 20 int8, 20 int16, 1 int32, 13 float64, 11 strings |
| HC-239D | 12 int8, 6 int16, 1 int32, 27 float64, 4 strings |
| HC-239G | 23 int8, 6 int16, 1 int32, 13 float64, 3 strings |

Key strings: `DUPERSID` str10; `CONDIDX` str13; `EVNTIDX` str16; `RXRECIDX` str19; `LINKIDX`
str16; `DRUGIDX` str13; `ICD10CDX` declared str8, always 3 characters (281 distinct in 2022);
`CCSR1X`–`CCSR4X` str6 (e.g. `CIR007`); `RXNDC` str11 with leading zeros (8,649 distinct);
`RXNAME` str50 (1,585 distinct, abbreviated); `RXDRGNAM` str60 (max 47 used); `RXFORM`,
`RXFRMUNT`, `RXSTRENG`, `RXSTRUNT` str50 (short codes; strength is text). Multum classes `TC1`,
`TC1S1`, `TC1S1_1` are int16.

pandas' `StataReader` exposes storage types only through the private `_typlist`/`_lbllist`
attributes after `read()` — codes `b` int8, `h` int16, `l` int32, `f` float32, `d` float64, an
integer N = strN. Stable in pandas 2.x and 3.x, but private: pin and test.

### 3.5 What MEPS does not have

No free text (condition verbatims were coded by AHRQ and not released; "other, specify" is
code 91 only), no lab values, no vitals except BMI, no procedure codes, no full ICD-10 codes,
no exact dates (month and year only), no geography finer than 4 census regions, no provider
identity.

## 4. The prototype's method

### 4.1 Dataset build

- Per panel, read the `.dta` with `convert_categoricals=False` and select: `DUPERSID, PANEL,
  SEX, RACETHX, REGIONY1, AGEY1X, INSCOVY1, POVCATY1, IPDISY1, IPNGTDY1, ERTOTY1, OBTOTVY1,
  OPTOTVY1, HHTOTDY1, RXTOTY1, TOTEXPY1, IPDISY2, LONGWT, VARSTR, VARPSU`.
- Diagnosis flags from prefixes `HIBPDX, CHDDX, ANGIDX, MIDX, OHRTDX, STRKDX, EMPHDX, DIABDX,
  ARTHDX, ASTHDX, CHOLDX`: the first column (sorted) starting with the prefix and containing
  `Y1`; recoded `== 1` → 1, everything else → 0.
- Keep `AGEY1X >= 18`, `IPDISY1 >= 0`, `IPDISY2 >= 0`. Label = `IPDISY2 > 0`; drop `IPDISY2`;
  lower-case column names. Output shape `(56360, 31)`.

### 4.2 Training

- Features: every column except `dupersid, panel, label_hosp_12m, longwt, varstr, varpsu` —
  the 25 contract features in contract order (`design.md` §3).
- Categoricals `sex, racethx, regiony1, inscovy1, povcaty1`: clipped at 0 (negative MEPS codes
  → category 0), cast to int.
- `HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, random_state=0,
  categorical_features=<indices of the five>)`.
- Validation model: panels 21–25; test: 26–27. Release model refit on all panels.
- Comparison model: `LogisticRegression(max_iter=1000)` on `[agey1x, ipdisy1 > 0]`, panels
  21–25.

### 4.3 Evaluation

Bootstrap 95% CIs: 500 resamples of the test set, `numpy.random.default_rng(0)`. Top-k: sort
by descending score, take `int(n × k)`. Deciles: `pandas.qcut(p, 10)`. Survey-weighted AUROC:
`sample_weight=LONGWT`. Null Brier: training-panel event rate as a constant prediction.
Permutation importance: `n_repeats=5, random_state=0, scoring='roc_auc'` on the test panels.

### 4.4 Environment used

Python 3.14.3, pandas 3.0.6, scikit-learn 1.9.1, numpy 2.5.4; Temurin 17 JRE for Synthea.
Python 3.11+ with pandas 2.2+ and scikit-learn 1.5+ is expected to work; small metric
differences can come from library versions. Pickled models are not portable across
scikit-learn versions — retrain, never copy a `.pkl`.

## 5. Numbers to reproduce

### 5.1 Dataset (M1) — exact

56,360 rows, 4,820 events, per-panel counts as §3.1. HC-252 dictionary: 2,648 variables, storage
counts as §3.4.

### 5.2 Model (M2) — within tolerance

`n_train 44497`, `n_test 11863`, `events_test 1042`, rate 0.0878.

| Measure | Comparison model | Gradient boosting |
|---|---|---|
| AUROC [95% CI] | 0.708 [0.691, 0.725] | 0.769 [0.754, 0.786] |
| **Tolerance** | **0.700–0.716** | **0.760–0.778** |
| AUPRC [95% CI] | 0.225 [0.206, 0.250] | 0.265 [0.242, 0.290] |
| Brier (null 0.0801) | 0.0751 | 0.0725 |
| Mean predicted | 0.0902 | 0.0917 |
| Top 5% PPV / sens | 0.331 / 0.188 | 0.383 / 0.218 |
| Top 10% PPV / sens | 0.266 / 0.303 | 0.293 / 0.333 |
| Top 20% PPV / sens | 0.202 / 0.460 | 0.231 / 0.525 |
| Survey-weighted AUROC | | 0.780 |

Calibration deciles (predicted / actual), lowest to highest: 0.016/0.008, 0.023/0.013,
0.034/0.025, 0.045/0.041, 0.056/0.056, 0.071/0.072, 0.089/0.095, 0.117/0.107, 0.162/0.169,
0.304/0.292.

| Subgroup (GBM) | n | Events | Rate | AUROC | Mean predicted |
|---|---|---|---|---|---|
| 18–44 | 4,362 | 193 | 0.044 | 0.761 | 0.054 |
| 45–64 | 3,965 | 273 | 0.069 | 0.739 | 0.079 |
| 65+ | 3,536 | 576 | 0.163 | 0.695 | 0.152 |
| Male | | | 0.070 | 0.794 | |
| Female | | | 0.103 | 0.743 | |
| No prior stay | 10,972 | | 0.073 | 0.744 | |
| Prior stay | 891 | | 0.273 | 0.694 | |

Permutation importance (AUROC drop): `agey1x` 0.0397, `sex` 0.0165, `rxtoty1` 0.0123, `hibpdx`
0.0057, `obtotvy1` 0.0057, `ipngtdy1` 0.0054, `totexpy1` 0.0053, `ertoty1` 0.0045, `povcaty1`
0.0045, `arthdx` 0.0024.

Comparison model coefficients (panels 21–25): intercept -4.047, age 0.0280 per year, prior stay
1.3055 — each 10 years × 1.32 odds; a prior stay × 3.7. Predicted risk without/with prior
stay: age 30 3.9%/13.0%; 50 6.6%/20.7%; 70 11.0%/31.4%; 85 15.9%/41.0%.

**Childbirth in the label** (all panels): ages 18–44, men 2.2% vs women 7.4%; 45–64, 7.4% vs
7.6%; 65+, 16.0% vs 16.0%. The motivation for M9.

## 6. Synthea harness (prototype run)

### 6.1 Generation

Seed 42, 3,000 requested (3,712 written, including deceased), ages 18–90, end date
2024-12-31, Arizona, CSV export only, `-Xmx6g`, ~10 minutes, run in the foreground with a
timeout (backgrounded runs were killed). The prototype used `master-branch-latest`; Phase 8
uses the repo's pinned v4.0.0 (O11), so its counts will differ. Synthea's public 108-patient
Massachusetts CSV sample is a usable quick fixture.

### 6.2 Format facts

- Conditions, encounter reasons, procedures: SNOMED CT. Medications: RxNorm. Observations:
  LOINC. Immunizations: CVX. No ICD-10 in the CSV export.
- Encounter classes: ambulatory, wellness, outpatient, emergency, urgentcare, home, inpatient,
  snf, hospice, virtual.
- Dates are ISO 8601 with time zone — make them time-zone-naive before comparing or pandas
  raises `Cannot compare tz-naive and tz-aware`.
- `patients.csv` has `INCOME` and `STATE`, no household size.
- `payers.csv` `OWNERSHIP` is GOVERNMENT, PRIVATE or NO_INSURANCE.

### 6.3 Mapping rules (prototype, training mode, year 1 = calendar year Y)

| Feature | Rule |
|---|---|
| Population | Born on or before 12/31/Y, alive on 12/31/Y, age ≥ 18 |
| `agey1x` | `int((12/31/Y − birth).days / 365.25)`, capped at 85 |
| `sex` | M → 1, F → 2 |
| `racethx` | Hispanic → 1; else white 2, black 3, asian 4, other 5 |
| `regiony1` | State → Northeast 1, Midwest 2, West 4, anything else 3 (**defect** — contract says unknown → 0) |
| `povcaty1` | `INCOME` / HHS poverty guideline (1-person household assumed: 2022 $13,590, 2023 $14,580, 2024 $15,060) × 100: <100 → 1, <125 → 2, <200 → 3, <400 → 4, else 5 |
| `inscovy1` | Any PRIVATE payer overlapping year 1 → 1; else any GOVERNMENT → 2; else 3 |
| `ipdisy1` / `ipngtdy1` | Count / summed rounded nights of inpatient encounters starting in year 1 |
| `ertoty1` | Emergency encounters |
| `obtotvy1` | Ambulatory + wellness + urgentcare + virtual |
| `optotvy1` | Outpatient |
| `hhtotdy1` | Home encounters (one per day) |
| `rxtoty1` | `DISPENSES` prorated by overlap of [START, STOP] with year 1; missing STOP → end of year 2 (**leakage defect**) |
| `totexpy1` | Year-1 `TOTAL_CLAIM_COST` + prorated medication `TOTALCOST`, whole dollars (charges, not payments) |
| Diagnosis flags | Any condition with `START` ≤ 12/31/Y whose lower-cased description matches the pattern below |
| `label_hosp_12m` | Any inpatient encounter starting in year Y+1 |

Description patterns (stand-ins until M11's code lists): `hibpdx` `hypertension`; `chddx`
`ischemic heart disease|coronary artery`; `angidx` `angina`; `midx` `myocardial infarction`;
`ohrtdx` `heart failure|atrial fibrillation|cardiomyopathy|valve|arrhythmia`; `strkdx`
`stroke|cerebrovascular accident|cerebral infarction`; `emphdx` `emphysema|chronic
obstructive`; `diabdx` `(?<!pre)diabetes`; `arthdx` `arthritis|osteoarthritis`; `asthdx`
`asthma`; `choldx` `hyperlipidemia|hypercholesterolemia|hypertriglyceridemia`.

**Regression case:** bare `coronary` matched "Abnormal findings diagnostic imaging
heart+coronary circulat (finding)". The narrowed pattern must never match it.

### 6.4 Results and lessons

- Year 1 = 2023: 2,913 adults; 138 hospitalized in 2024 (4.7%); mean predicted 10.5%; AUROC
  0.656. **A mechanical pipeline check, not an accuracy measure.**
- Even after the `coronary` fix, 25.1% of Synthea adults have coronary heart disease vs 5.6%
  in MEPS — the simulator, not the mapping.
- MEPS vs Synthea: median spending $1,728 vs $15,082 (payments vs charges); mean fills 12.6 vs
  33.8; arthritis 27% vs 12%; asthma 13% vs 4%; any home health 4.4% vs 0.4%; year-1
  hospitalization 7.9% vs 4.7%.
- Dropping spending, fills and home health: Synthea AUROC 0.651 → 0.673; MEPS AUROC
  0.766 → 0.768 (`decisions.md` O25).

## 7. Feature contract `meps25-v1` — field reference

All required integers, MEPS codes, no negatives at the API (the ETL converts missing to a
documented default and adds a warning). Column order is in `design.md` §3.

| Feature | MEPS source | Allowed values | Notes |
|---|---|---|---|
| `agey1x` | AGEY1X | 18–85 | Top-coded at 85 |
| `sex` | SEX | 1 male, 2 female | |
| `racethx` | RACETHX | 1 Hispanic, 2 NH white, 3 NH black, 4 NH Asian, 5 NH other/multiple | |
| `regiony1` | REGIONY1 | 1 Northeast, 2 Midwest, 3 South, 4 West | 0 if unknown |
| `inscovy1` | INSCOVY1 | 1 any private, 2 public only, 3 uninsured | |
| `povcaty1` | POVCATY1 | 1 poor, 2 near poor, 3 low, 4 middle, 5 high | Ordered |
| `ipdisy1` | IPDISY1 | ≥ 0 | Hospital discharges |
| `ipngtdy1` | IPNGTDY1 | ≥ 0 | Nights in hospital |
| `ertoty1` | ERTOTY1 | ≥ 0 | ER visits |
| `obtotvy1` | OBTOTVY1 | ≥ 0 | Office-based visits incl. telehealth |
| `optotvy1` | OPTOTVY1 | ≥ 0 | Hospital outpatient visits |
| `hhtotdy1` | HHTOTDY1 | ≥ 0 | Home-health days |
| `rxtoty1` | RXTOTY1 | ≥ 0 | Fills incl. refills |
| `totexpy1` | TOTEXPY1 | ≥ 0 dollars | Payments, not charges |
| `hibpdx` | HIBPDXY1 | 0/1 | High blood pressure |
| `chddx` | CHDDXY1 | 0/1 | Coronary heart disease |
| `angidx` | ANGIDXY1 | 0/1 | Angina |
| `midx` | MIDXY1 | 0/1 | Heart attack |
| `ohrtdx` | OHRTDXY1 | 0/1 | Other heart disease |
| `strkdx` | STRKDXY1 | 0/1 | Stroke |
| `emphdx` | EMPHDXY1 | 0/1 | Emphysema |
| `diabdx` | DIABDXY1 or DIABDXY1_M18 | 0/1 | Diabetes |
| `arthdx` | ARTHDXY1 | 0/1 | Arthritis |
| `asthdx` | ASTHDXY1 | 0/1 | Asthma |
| `choldx` | CHOLDXY1 | 0/1 | High cholesterol |

## 8. Pointers for M9–M11

- **Unplanned-stay label (M9):** yearly Hospital Inpatient Stays files (HC-239D for 2022 and
  equivalents), using the year-2 calendar year's file per panel. `RSNINHOS`: 1 surgery, 2
  treatment/therapy, 3 diagnostic tests only, 4 give birth (mother), 5 to be born (baby), 6
  pregnancy complications, 91 other. `EMERROOM` 1 = began in ER. Dates month/year only
  (`IPBEGMM`, `IPBEGYR`). Link on `DUPERSID`.
- **Condition features (M10):** Medical Conditions `ICD10CDX` (3 characters) and
  `CCSR1X`–`CCSR4X`; ~10% of codes suppressed as `-15`; only conditions linked to an event that
  year are present.
- **Drug features (M10):** Prescribed Medicines `RXNDC`, `TC1`, `TC1S1`, `TC1S1_1`, `RXDAYSUP`
  (999 = as needed; missing not imputed). Multum classes changed across years — check when
  pooling.
- **Event files are yearly:** for panel P with year 1 = Y, use year-Y files filtered to
  `PANEL == P`.
- **Tuning (M10):** panel-grouped CV within 21–25; 26–27 never touched.
- **Code lists (M11):** NLM SNOMED CT → ICD-10-CM map (UMLS licence). For a later claims
  adapter, CMS Synthetic RIF files carry ICD-10-CM, HCPCS and NDC.
- Area-level enrichment candidates (later contract versions): AHRQ Community-Level Health
  Database; CDC PLACES.

## 9. Risks (from the prototype's planning)

| Risk | Mitigation |
|---|---|
| AHRQ declines commercial use of MEPS-trained models | Ask in writing now (O23); sell the platform and retraining, not weights |
| Employer IP agreement claims the work | Repo owner reviews their employment agreement before building on work time or equipment |
| Survey (MEPS) vs records (customer) mismatch | Portable features first (O25); recalibrate per customer (Phase 8b); validate on customer history |
| Synthea mistaken for accuracy evidence | Every report says Synthea results are pipeline tests only |
| Weak 65+ performance | M10 |
| Childbirth and planned stays in the label | M9 |
| Regulatory change | Counsel reviews the FDA CDS position before launch |

## 10. Reference URLs

| Topic | URL |
|---|---|
| MEPS home | https://meps.ahrq.gov |
| MEPS data files list | https://meps.ahrq.gov/mepsweb/data_stats/download_data_files.jsp |
| HC-252 documentation | https://meps.ahrq.gov/data_stats/download_data/pufs/h252/h252doc.shtml |
| HC-241 conditions | https://meps.ahrq.gov/data_stats/download_data/pufs/h241/h241doc.shtml |
| HC-239A prescriptions | https://meps.ahrq.gov/data_stats/download_data/pufs/h239a/h239adoc.shtml |
| HC-239D hospital stays | https://meps.ahrq.gov/data_stats/download_data/pufs/h239d/h239ddoc.shtml |
| HC-239G office visits | https://meps.ahrq.gov/data_stats/download_data/pufs/h239g/h239gdoc.shtml |
| MEPS conditions coding (ICD-10, CCSR) | https://meps.ahrq.gov/data_files/publications/mr36/mr36ug.shtml |
| MEPS data-use wording example | https://meps.ahrq.gov/data_stats/download_data/pufs/h213d/h213ddoc.shtml |
| Synthea | https://github.com/synthetichealth/synthea |
| Synthea data licensing | https://github.com/synthetichealth/synthea/wiki/DPG |
| Synthea CSV dictionary | https://github.com/synthetichealth/synthea/wiki/CSV-File-Data-Dictionary |
| Synthea evaluations | https://pmc.ncbi.nlm.nih.gov/articles/PMC6416981/, https://pmc.ncbi.nlm.nih.gov/articles/PMC7651916/ |
| NLM SNOMED CT → ICD-10-CM map | https://www.nlm.nih.gov/research/umls/mapping_projects/snomedct_to_icd10cm.html |
| AMA CPT licensing | https://www.ama-assn.org/practice-management/cpt/cpt-licensing-frequently-asked-questions-faqs |
| QAdmissions | https://bmjopen.bmj.com/content/3/8/e003482 |
| FDA CDS guidance | https://www.fda.gov/media/109618/download |
| CPRD pricing | https://www.cprd.com/access-data/pricing |
| OpenSAFELY access | https://www.opensafely.org/access-to-opensafely/ |
| PhysioNet (MIMIC) | https://physionet.org/ |
| HRS public data overview | https://hrs.isr.umich.edu/sites/default/files/biblio/OverviewofHRSPublicData.pdf |
| MCBS PUF guide | https://www.cms.gov/files/document/2021-mcbs-puf-data-user-guide.pdf |
| CMS Synthetic RIF guide | https://data.cms.gov/sites/default/files/2023-05/d51e1218-68c3-4c7c-9598-0b81f22fe903/User%20Guide%20-%20CMS%20Synthetic%20RIF%20Files%20May%202023_AM508_v2.pdf |
| AHRQ Community-Level Health Database | https://www.ahrq.gov/data/innovations/clh-data.html |
| CDC PLACES | https://www.cdc.gov/places/about/index.html |
