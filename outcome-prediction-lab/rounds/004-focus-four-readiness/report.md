# Round 004 report — readiness of the four focus predictions

**Status:** complete. **Pre-registration:** [`README.md`](./README.md), written before any run.
**Run through the CLI:** [`configs/`](./configs/), [`runs/`](./runs/). **Test-panel looks:** 5, all
pre-registered and logged in [`../../holdout-ledger.md`](../../holdout-ledger.md): one confirmation
(`er-admit-v2`) and four fairness looks. No 65+ specialist met the bar, so none was looked at.
Decisions: O56–O58.

## 1. Headline

**All four focus predictions now have a production-contract (`meps-portable-v2`) model, a subgroup
fairness report and a 65+ check.** On the untouched test panels (26–27, n = 11,863):

| Prediction | Production model | AUROC (all adults) | AUROC (65+) | 65+ baseline | Calibration (mean predicted vs rate) |
|---|---|---|---|---|---|
| Admission through the ER | `004/er-admit-v2` (records only) — **new** | **0.785** | 0.729 | 0.685 | 0.051 vs 0.049 |
| Non-obstetric hospital stay | `003/nonobstetric-v2` | 0.795 | 0.701 | 0.639 | 0.080 vs 0.079 |
| Any ER visit | `003/any-ed-v2` | 0.740 | 0.709 | 0.660 | 0.152 vs 0.155 |
| High-cost patient | `003/high-cost-v2-claims` (claims) | 0.834 | 0.782 | 0.634 | 0.105 vs 0.100 |

All four are scored with household income blanked, as production will be (O53).

## 2. Admission through the ER on the production contract (O56)

Cross-validated (panels 21–25):

| Config | Inputs | CV AUROC |
|---|---|---|
| `er-admit-research` | round-001 research features (spending, CCSR, Multum) | 0.7818 |
| `er-admit-v2` | `meps-portable-v2`, records only | **0.7797** |
| `er-admit-v2-claims` | plus prescription fills, home-health days | 0.7798 |
| baseline | age, prior hospital stays, prior ER visits | 0.7347 |

Same pattern as the other admission target: the contract costs almost nothing (−0.002), and claims
add nothing, so the **records-only** model is the production candidate, as pre-registered. Test AUROC
0.785 (round 001's research model: 0.788); the top 10% of predicted risk holds 40% of ER-origin
admissions, at 20% precision (rate 4.9%).

## 3. Fairness (O57)

Full tables, one per model: [`003 fairness/`](../003-portable-contract/fairness/),
[`004 fairness/`](./fairness/). Groups: race/ethnicity, insurance type (year 1), sex, age band. For
each: AUROC with a bootstrap 95% CI (not computed below 20 events), calibration ratio (mean predicted ÷
observed rate), share flagged by the overall top-10% flag, share of the group's cases caught by it,
and precision.

**What holds up**

- **Calibration by race/ethnicity is close** for the three larger groups (White, Hispanic, Black:
  ratios 0.96–1.12 across all four models). No model systematically under-predicts Black adults.
- **Sex:** AUROC within 0.01–0.04 and calibration within 0.95–1.11 for every model.
- **High cost** discriminates at least as well for every minority group as for White adults (0.82–0.89 vs 0.81).

**What a reviewer must see**

| Finding | Where | Why it matters |
|---|---|---|
| **Uninsured adults are almost never flagged** — 0–2% flagged; the flag catches 0% (ER admission), 5% (non-obstetric stay), 11% (ER visit) of their cases | all four | Their recorded rates are low (2–9%) because the labels measure **use** of care, not need: uninsured people use less. A use-based score will under-serve people who face access barriers (the Obermeyer et al., 2019 pattern). Any outreach programme must not rely on the flag alone for this group |
| **Calibration bends toward the average by age and insurance:** over-predicts 18–44 (ratio 1.21–1.25 for the admission targets, 1.16 high cost) and privately insured (1.16–1.24, admission targets); under-predicts public-only (0.89 admissions, 0.94 ER visit) and 75+ (0.90–0.93) | admissions, ER visit; high cost by age | Absolute risks shown to clinicians are a little too low for the highest-risk groups; ranking is unaffected. Recalibration on customer data (Phase 8b) should check calibration **per group**, not just overall |
| **Black adults: lower AUROC for non-obstetric stay** (0.745 vs 0.787 White; CIs 0.709–0.779 vs 0.763–0.807, barely overlapping) | `nonobstetric-v2` | Same calibration (0.96), so not a level bias, but the model separates risk less well. Monitor; candidate for a targeted look in a later round |
| **Asian adults: wide uncertainty** — 21 events for both admission targets; ER-admission AUROC 0.639 (CI 0.512–0.770) | admission targets | Too few events to conclude anything; not evidence of good or bad performance |
| **The top-10% flag is mostly older and publicly insured adults** (75+: 27–41% flagged; public-only: 18–22%) | all four | Expected from base rates. A practice that wants a flag within each age group needs per-group cutoffs; that is a policy choice, not a model one |

Race/ethnicity is **not a model input** and is never narrated per patient (O50); it appears only in
these aggregate reports.

## 4. Adults 65+ (O58)

**Rule (pre-registered):** adopt a 65+-only specialist only if its CV AUROC on 65+ beats the general
model's CV AUROC on 65+ by ≥ +0.005.

| Prediction | General model, CV AUROC on 65+ | 65+ specialist, CV AUROC | Difference | Decision |
|---|---|---|---|---|
| Admission through the ER | 0.7169 | 0.6794 | −0.038 | keep general |
| Non-obstetric hospital stay | 0.6988 | 0.6702 | −0.029 | keep general |
| Any ER visit | 0.6918 | 0.6718 | −0.020 | keep general |
| High-cost patient | 0.7870 | 0.7671 | −0.020 | keep general |

(Training rows for the specialists: 10,500 adults 65+ across panels 21–25.)

**The general models win every time, clearly.** A specialist sees a quarter of the data; what the
general model learns from younger adults about how conditions, prior use and medicines relate to
next-year use carries over to older adults. No specialist was confirmed, so the test panels were not
looked at for them.

**Within 65+, every model is weaker than overall** (test AUROC 0.70–0.78 vs 0.74–0.83). That is expected
and not a 65+ defect: overall AUROC is partly bought by separating young from old, and within one age
band that easy gain is gone (every within-band AUROC is lower — fairness tables, "Age band"). Against
the 65+ baseline the models still add 0.04–0.15. Calibration for 65+: ratios 0.90–1.07 (slight
under-prediction for admissions and ER visits at 75+).

## 5. Limitations

- Fairness numbers are from one test window (2021–2023) on MEPS survey data; customer populations
  differ. They are a starting point for the per-customer fairness check in Phase 8b, not a clearance.
- Groups are the five MEPS race/ethnicity categories; "Other or multiple" and Asian adults have few
  events — conclusions about them are weak in either direction.
- Insurance is year-1 coverage; people switching coverage are classed by year 1.
- Fairness here is about the model's errors; the label itself (use of care) carries the access bias
  noted in §3, which no model change can fix.
