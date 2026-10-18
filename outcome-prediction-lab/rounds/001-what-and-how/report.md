# Round 001 report — what to predict, and how

**Status:** complete (iteration 1). **Pre-registration:** [`README.md`](./README.md). **All numbers:**
[`metrics.json`](./metrics.json), [`explanations.json`](./explanations.json). **Test-panel looks:**
11, all logged in [`../../holdout-ledger.md`](../../holdout-ledger.md) before scoring.

Training panels 21–25 (44,497 adults) for every choice, via leave-one-panel-out cross-validation
(CV); test panels 26–27 (11,863 adults) scored once, for finalists named beforehand.

## 1. Headline

- **On the prototype's exact objective, the new portable model is better: AUROC 0.769 → 0.788
  (+0.019, 95% CI +0.011 to +0.027), AUPRC 0.265 → 0.307 (+0.042, CI +0.023 to +0.061)**, top-10%
  PPV 29% → 33%, and calibration (Brier) 0.0725 → 0.0703. The prototype reproduced exactly (0.769)
  on the same people, so the comparison is like for like.
- **But most of that gain is the model spotting pregnancies.** Codes like Z34 ("supervision of
  normal pregnancy") in year 1 predict childbirth admissions in year 2 — real prediction, not
  leakage, but exactly the label flaw the prototype documented. Where pregnancy can't drive it
  (non-obstetric admissions; men only), the code features add only ≈ +0.002 AUROC.
- **The better question is "non-obstetric admission"**: it scores higher (AUROC 0.795 on test) on
  a label that means what a care manager means.
- **Seven new targets** were predicted; every one beats its simple baseline on the test panels.
- **Of the concepts tried, the useful ones were:** code features (TF-IDF → LSA), honest missing
  values plus missingness augmentation, knowledge scores (small), and SHAP explanations. The
  autoencoders worked but didn't beat the simpler LSA; random forest ≈ gradient boosting;
  tuning and monotonic constraints changed almost nothing.

## 2. What we predicted

| Target | Definition (year 2) | Rate | Status |
|---|---|---|---|
| Any stay (prototype) | ≥ 1 inpatient discharge | 8.8% | Prototype objective |
| **Non-obstetric admission** | admission beginning in year 2, excluding giving birth / being born / pregnancy complications (`RSNINHOS` 4–6) | 7.9% | Recommended headline label |
| Admission via the ER | admission beginning in year 2 that started in the ER (`EMERROOM`) | 4.9% | Closest MEPS proxy for "unplanned" |
| Any ED visit | ≥ 1 emergency-room visit | 15.5% | New |
| ED visit count | number of ER visits (Poisson model) | mean 0.24 | New, count form |
| High-cost member | top 10% of year-2 spending *within the panel* | 10.0% | New |
| Spending | year-2 total spending (model on log dollars) | mean $9,783 | New, cost form |
| Death | died during year 2 | 1.1% | **Learning only** — never for promotion |
| Loss of insurance | insured in year 1, uninsured in year 2 | 1.0% | **Learning only** |

Admission labels count stays that **began** in year 2; the prototype's label counts year-2
discharges, which includes stays admitted in year 1 (they agree for 99.9% of people).

## 3. The prototype's objective, improved (test panels 26–27)

| Model | AUROC | AUPRC | Brier | Top-10% PPV | Top-10% sensitivity | AUROC 65+ |
|---|---|---|---|---|---|---|
| Prototype (reproduced) | 0.769 | 0.265 | 0.0725 | 29.3% | 33.3% | 0.695 |
| **New, portable** | **0.788** | **0.307** | **0.0703** | **33.1%** | **37.7%** | 0.705 |
| New + survey items (not portable) | 0.789 | 0.307 | 0.0702 | 33.8% | 38.5% | 0.706 |

Paired bootstrap vs the prototype (same people, 500 resamples): **AUROC +0.019 [+0.011, +0.027]**,
AUPRC +0.042 [+0.023, +0.061] — better in 100% of resamples. **65+: +0.010 [−0.001, +0.021]** —
better in 96% of resamples, but the interval touches zero; the 65+ weakness is not solved.

**Where the gain comes from** (CV, panels 21–25):

| Step | AUROC | AUPRC |
|---|---|---|
| Prototype | 0.768 | 0.262 |
| + honest missing-value encoding | 0.769 | 0.263 |
| + Medicare/Medicaid flags, code counts | 0.770 | 0.266 |
| + knowledge scores (frailty, Charlson, Elixhauser) | 0.772 | 0.266 |
| + tuning | 0.774 | 0.268 |
| **+ TF-IDF → LSA code representation** | **0.789** | **0.319** |
| + survey items (not portable) | 0.793 | 0.316 |

The pregnancy check: the LSA step adds +0.016 on the prototype's label, but **+0.002 on
non-obstetric admissions and +0.0015 among men**. A per-patient explanation shows it directly:
the very-high-risk test patient's top drivers are PRG029 (a CCSR pregnancy category) and Z34.

## 4. New targets (test panels 26–27)

| Target | Model | Simple baseline | Model gain (95% CI) | What it means |
|---|---|---|---|---|
| Non-obstetric admission | AUROC 0.795, AUPRC 0.277 | 0.756 (age + prior stays) | +0.039 [+0.028, +0.049] | The best-defined admission target here |
| Admission via ER | AUROC 0.788, AUPRC 0.190 | 0.754 | +0.035 [+0.022, +0.048] | Rare (4.9%), so low precision |
| Any ED visit | AUROC 0.739, top-10% PPV 45% | 0.682 (age + prior ER) | +0.057 [+0.047, +0.067] | Biggest lift over its baseline |
| ED visit count | Spearman 0.30; deviance 0.78 (null 0.97) | 0.22; 0.88 | top 10% hold 36% of ER visits | Counts are noisy; ranking is modest |
| High-cost member | AUROC 0.850, AUPRC 0.477 | 0.826 (age + last year's spend) | +0.024 [+0.018, +0.029] | Highest discrimination of all |
| Spending | R² (log) 0.53, Spearman 0.74 | 0.45, 0.68 | top 10% hold 37.0% vs 36.6% of spend | Ranks people better, but last year's spend already finds the big spenders |
| Death (learning) | AUROC 0.881, AUPRC 0.122 | 0.859 (age alone) | +0.022 [+0.001, +0.044] | Age does most of the work; 127 deaths in test |
| Loss of insurance (learning) | AUROC 0.871, AUPRC 0.057 | 0.798 | +0.073 [+0.044, +0.101] | 111 events; 65+ number meaningless (1 event — Medicare) |

How to read AUROC vs AUPRC here: AUROC answers "does the model rank people correctly?" and is
comparable across targets; AUPRC answers "of the people it flags, how many are real?" and
depends heavily on how rare the outcome is — so 0.19 for ER admissions (rate 4.9%) is roughly
four times better than chance, while 0.48 for high cost (rate 10%) is roughly five times.

## 5. Which concepts were used — and which helped

| Concept | Used how | Result | Verdict |
|---|---|---|---|
| **TF-IDF** (your #1) | Each patient's year-1 ICD-10 codes, CCSR categories and drug classes as a "document" | Sparse TF-IDF + logistic regression: 0.753 → **0.777**; compressed with LSA + gradient boosting: **0.789** | **Useful** — the single biggest gain, though mostly via pregnancy codes |
| **LSA** (TruncatedSVD) | TF-IDF → 32 dimensions | Best code representation, 17 s per CV | **Useful** — the winner |
| **Autoencoder** (your #2) | TF-IDF → 64 → **16** → 64 → TF-IDF, sklearn MLP | 0.786 — nearly LSA, ~8× slower (143 s vs 17 s per CV) | Works; **not better than linear LSA** here |
| **Denoising autoencoder** | Same, 20% of inputs hidden in training | 0.786 | Same as plain; no gain |
| **Random forest** (your #3) | 400 trees, min leaf 20 | 0.772 (gradient boosting 0.772); 65+ 0.707 vs 0.701 | **Equal**, not better; slightly better for 65+ than gradient boosting without codes |
| **Per-patient explanations** (your #3) | SHAP on the gradient-boosted model; templated text; code pattern traced to the patient's own codes | Readable, exact in log-odds; revealed the pregnancy effect | **Useful** — see §6 |
| **Single decision tree** (the "readable" model) | Depth 4 | Test AUROC **0.732** vs 0.788 | Readable rules cost **0.056 AUROC** |
| **Surrogate tree** | Depth 3, imitating the model | Fidelity R² 0.57 | Good for a picture of the logic, not a faithful explanation |
| **Missing values** (your #4) | Honest encoding (refused / don't know → missing, not "no") | +0.001 (MEPS is pre-imputed) | **Necessary for correctness**, small on MEPS |
| Missingness in production | Income + spending absent at scoring time | Unaware model: AUPRC 0.268 → 0.260, calibration worse; median imputation worst; MICE recovers most; **training with missingness augmentation recovers fully** (0.269) | **Useful: augmentation is the fix** |
| Missing-data action items | Value of information: re-score over plausible incomes | e.g. "Record household income: this estimate ranges from 23% to 28%" | Works; sensible, small effects |
| **Feature importance** (your #5) | Mean \|SHAP\| + direction | Learned code pattern 0.48 ≫ age 0.16 > spending 0.13 > body systems 0.12 > Medicare 0.11 > Elixhauser count 0.10 > high blood pressure 0.10 | **Useful**; directions all as expected |
| Knowledge scores (frailty, Charlson, Elixhauser) | Published code lists → scores | +0.001 on top of code counts; Elixhauser count ranks 6th | **Small** — LSA learns the same signal from the raw codes |
| Monotonic constraints | Risk can't fall with more prior stays / frailty | 0.787 vs 0.789 | **No gain** (data already monotone) |
| Tuning | 16-point grid | +0.002 | **Negligible** |
| Survey items | Self-rated health, function, distress, etc. | +0.003 on top of codes | Small, and **not portable** |

## 6. Interpretation, by example (test patients)

> **High risk (23%, model baseline 6%).** Raised most by: their overall pattern of diagnosis and drug
> codes (odds ×1.37); 10 distinct diagnosis codes (×1.24); $18,212 of health spending last year
> (×1.24). Lowered most by: 0 ER visits last year (×0.94); 0 nights in hospital (×0.95). Codes driving
> the code pattern (approximate): rx215 (×1.33), rx347 (×1.10), SYM016 (×1.03).

> **Very high risk (57%).** Raised most by: the code pattern (odds ×14.7) … Codes driving it:
> **PRG029 (×2.82), Z34 (×2.80)** — a pregnancy, not frailty.

Surrogate tree (depth 3, R² 0.57) — the model's logic in one picture: first split on **number of
distinct diagnoses (> 7.5)**, then **nights in hospital last year (> 2.5)**, then **ER visits
(> 1.5)** or coronary heart disease; leaf risks from ~0% to ~50%.

**Why a random forest can't simply be "read":** one decision tree gives one readable path; a
forest averages hundreds, and the model above is built the same way. What *can* be read is the
per-patient breakdown (SHAP), which works for both.

## 7. Bugs and data issues found during the round

- **MEPS person-ID formats changed over time** (8-digit vs 10-digit panel-prefixed, even for the same
  person in different files). Before normalising, Panel 22 silently had *no* conditions or drugs.
- **Panel 21 used the SF-12v2, not the VR-12**: not substituted, treated as missing. Adult BMI is absent
  from four panels and was dropped.
- **The 2016 prescriptions file exists only as SAS transport**, at a folder-less URL (now in the manifest).
- **An evaluation bug** (missingness hooks not passed) produced a false "no effect" result; caught
  because the numbers were identical to four decimals, fixed, re-run.

## 8. Limitations

- MEPS is self-report: the published range for self-report models is 0.61–0.74 (Wallace 2014); we are
  above it, so further big AUROC gains on MEPS are unlikely.
- Condition codes are 3-character and only for conditions linked to a year-1 event; ~8% suppressed.
- Drug classes are numeric Multum codes (`rx215`) — not yet translated to names.
- Charlson/Elixhauser are approximate at 3 characters; the frailty score is exact.
- None of this has met customer data; portability is argued (codes, coverage exist in FHIR/claims), not shown.
- Not yet tried: TF-IDF on code *descriptions*, character n-grams on drug names, "potentially
  preventable admission" (needs full ICD-10 codes MEPS doesn't release), PyTorch autoencoders.

## 9. How a healthcare business could use these models

- **Care-management worklist (non-obstetric admission).** Each month, rank the panel and give care
  managers the top 10%: about 3 in 10 of them would otherwise be admitted, and the list catches
  ~37% of all such admissions. Each name comes with its templated reasons and a "record household
  income" prompt where data is missing.
- **ED-utilisation outreach (any ED visit).** The largest lift over the simple rule: flag likely
  frequent ED users for same-day-access and after-hours options. Nearly half of the top 10% will
  visit the ED in the next year.
- **Budgeting and risk-contract planning (high cost, spending).** Finance and population-health
  leads use calibrated spend predictions to size reserves and staffing; the high-cost flag
  (AUROC 0.85) feeds complex-care enrolment. Note: last year's spend alone already finds most big
  spenders — the model's value is better ranking below the very top.
- **Coverage-retention outreach (loss of insurance — learning only for now).** A benefits team
  could prioritise re-enrolment help; promotion would need a fairness review first, because
  income and insurance type drive it.
- **Serious-illness conversations (death — learning only, never promoted as-is).** Shown to teach
  rare-event evaluation; any real use (e.g. prompting advance-care-planning conversations) needs
  clinical governance, not a model release.

