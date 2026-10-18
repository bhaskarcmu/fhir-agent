# Round 003 report — the portable feature contract (`meps-portable-v2`)

**Status:** complete. **Pre-registration:** [`README.md`](./README.md). **Run through the CLI:**
[`configs/`](./configs/), [`runs/`](./runs/). **Test-panel looks:** 3, as pre-registered, all in
[`../../holdout-ledger.md`](../../holdout-ledger.md). Decisions: O52–O54 (O25 resolved).

## 1. Headline

**Production models built only from what a customer's FHIR / claims data can supply lose nothing for
admissions and ER visits, and a little for high cost.** On the untouched test panels:

| Target | Round-001 research model | **Production contract** | Portable baseline | Calibration (mean predicted vs rate) |
|---|---|---|---|---|
| Non-obstetric admission | 0.795 | **0.795** (records only); top 10%: 30% admitted, 38% of admissions | 0.756 | 0.080 vs 0.079 |
| Any ER visit | 0.739 | **0.740** (records only); top 10%: 44% visit the ER | 0.682 | 0.152 vs 0.155 |
| High-cost patient | 0.850 | **0.834** (with claims); top 10%: 44% high-cost | 0.722 | 0.105 vs 0.100 |

All three were scored **with household income blanked**, as production will be; they stay calibrated
because they were trained with missingness augmentation.

## 2. What the contract changes (`outcome_prediction/contract.py`)

| Out (not portable) | Why | In (portable replacement) |
|---|---|---|
| Last year's spending | MEPS = payments from all payers; records hold one system's charges | — (dropped, not imputed: O53) |
| CCSR condition groups, CCSR body-system count | Need AHRQ's mapping file (terms unclear) | ICD-10 chapter count (CMS/NCHS chapter ranges) |
| Multum drug classes and class count | Proprietary; FHIR carries RxNorm | Distinct-medicine count (≈ RxNorm ingredients; correlation 0.996 with class count) |
| Code tokens incl. CCSR + Multum | as above | ICD-10-only code tokens → LSA |
| Prescription fills, home-health days | Need dispensing / claims data | Kept in the claims tier only |
| Household income (poverty category) | Almost never recorded | Kept as optional; models learn to work without it |

## 3. Cross-validated detail (panels 21–25)

| Target | Research (spending, CCSR, Multum) | `v2` records only | `v2` + claims | Baseline |
|---|---|---|---|---|
| Non-obstetric admission | 0.7988 | 0.7983 | 0.7989 | 0.7478 |
| Any ER visit | 0.7343 | 0.7305 | 0.7305 | 0.6662 |
| High-cost patient | 0.8599 | 0.8402 | 0.8472 | 0.7344 |

High cost depends most on detail the contract removes (spending, drug classes, prescription fills),
which is why its claims tier helps (+0.007) and the others' doesn't.

## 4. The two rules that make it work (O53)

- **Always missing → drop and retrain.** Filling in spending from the other inputs would add no
  information (the fill-in *is* a function of them) and would silently miscalibrate a model trained
  on real spending.
- **Sometimes missing → keep, with augmentation.** Income is hidden for half the training rows by a
  pipeline step that only acts while fitting, so the model learns both situations. Narratives say
  "Household income isn't recorded; depending on it, the estimate would be between 20% and 26% —
  worth recording."

## 5. Which customers can use which target (O54)

| Target | Customer needs | Model |
|---|---|---|
| Non-obstetric admission | records (within the system) or claims (all hospitals) | `nonobstetric-v2` |
| Any ER visit | records or claims | `any-ed-v2` |
| High-cost patient | **claims** — records alone can never validate or recalibrate it | `high-cost-v2-claims` |

Model cards: [`cards/`](./cards/); scorecards (person-scored criteria still owed): [`scorecards/`](./scorecards/);
example narratives: [`explanations/nonobstetric-v2-examples.md`](./explanations/nonobstetric-v2-examples.md).

## 6. Limitations

- Still MEPS: "usually available" features are *usually* present in records but undercounted when
  care happens elsewhere — records-only customers will need recalibration (Phase 8b).
- The office vs hospital-outpatient visit split and the SNOMED → ICD-10 code lists are still to be
  confirmed against real FHIR (M6, M13).
- Knowledge scores (Charlson, Elixhauser) remain approximate at 3 characters.
