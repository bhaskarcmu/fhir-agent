# Phase 8 — Prediction targets: the four in focus, and how we got here

**Decision:** [`decisions.md`](./decisions.md) **O55** (2026-10-18). From here on, Phase 8 works on
**four predictions only**, unless the repo owner explicitly says otherwise. Everything else
explored so far is **parked, not deleted** — §4 lists where each piece lives, so it can be picked
up again.

## 1. The four focus predictions

All four are next-12-month **event probabilities** for adults, so each maps natively onto a FHIR
`RiskAssessment` (O3) — no new output format is needed.

| # | Prediction | Label (lab) | Best test result so far | Production model (contract `meps-portable-v2`) | Customer must supply |
|---|---|---|---|---|---|
| 1 | **Admission through the emergency room** | `admit_via_er_y2` | AUROC **0.785** (round 004, production contract) | `er-admit-v2` | records or claims |
| 2 | **Hospital stay not related to pregnancy or childbirth** | `admit_nonobstetric_y2` | AUROC **0.795** (round 003, production contract) | `nonobstetric-v2` | records or claims |
| 3 | **Any emergency-room visit** | `any_ed_y2` | AUROC **0.740** (round 003, production contract) | `any-ed-v2` | records or claims |
| 4 | **Being a high-cost patient** (top 10% of next-year spending) | `high_cost_y2` | AUROC **0.834** (round 003, production contract, with claims) | `high-cost-v2-claims` | **claims** (O54) |

Why these four together: two describe *unplanned acute care* (ER-origin admissions, ER visits),
one describes *serious illness requiring admission* without the childbirth distortion, and one is
the *financial* view. Three can be validated by any customer; high cost needs claims.

## 2. How we got here — the decision path

| When | Step | What we learned | Record |
|---|---|---|---|
| Phase 8 start | Research prototype handed over: one target, **any hospital stay** (AUROC 0.769) | A reproducible starting point on free US data (MEPS) | [`prototype-baseline.md`](./prototype-baseline.md) |
| M1–M2 | Reproduced the prototype **exactly** — dataset counts and every reported metric | The baseline is trustworthy | `milestone-plan.md` M1–M2 |
| Data | Pinned the data in git, preserved it in private mirrors; tests populate their own data | Results stay reproducible even if AHRQ changes or disappears | O41–O44 |
| Round 001 | Explored **nine** targets and many methods | **Any stay is distorted by childbirth**: most code-feature gain was pregnancy codes predicting deliveries. Non-obstetric admission is the cleaner label (O47). Seven new targets all beat simple baselines | [round 001 report](../../outcome-prediction-lab/rounds/001-what-and-how/report.md) |
| Summary review | Clinical and business value of each target | Non-obstetric admission = clinical anchor; any ER visit = strongest lift over a simple rule; high cost = finance view; death and insurance loss = learning only (O48) | conversation summary, reflected here |
| Round 002 | Text representations, self-explanatory narratives, the lab CLI | Text adds little on a pregnancy-free label; character n-grams map messy drug names well; every patient can get a plain-language explanation | [round 002 report](../../outcome-prediction-lab/rounds/002-text-and-explanations/report.md) |
| Idea considered | **"Find similar patients"** with autoencoder embeddings | Critiqued (similarity must be intervention-specific; autoencoders unlikely to beat simpler methods here; no ground truth in MEPS; privacy and anchoring risks) — **then dropped by the repo owner** | §5 below |
| ETL review | What survives conversion from customer FHIR | Last-year spending isn't portable; high cost can be predicted without it (CV 0.860 → 0.852) | O25 → O52–O53 |
| Round 003 | The portable contract `meps-portable-v2` | Production models lose nothing for admissions and ER visits, a little for high cost; high cost needs claims to be validated | [round 003 report](../../outcome-prediction-lab/rounds/003-portable-contract/report.md), O52–O54 |
| **2026-10-18** | **Repo owner narrows the focus to the four in §1** | — | **O55** |
| Round 004 | Readiness of the four: ER-admission production model, fairness, 65+ | All four have production models; fairness findings recorded (uninsured rarely flagged — labels measure use, not need); general models beat 65+ specialists | [round 004 report](../../outcome-prediction-lab/rounds/004-focus-four-readiness/report.md), O56–O58 |

## 3. What changes now

- **Default scope:** every new round, model card, scorecard, narrative and milestone deliverable
  targets these four unless the repo owner says otherwise.
- **Gap closed (round 004):** admission through the ER now has its production-contract model
  (`er-admit-v2`, O56). Every focus model's card carries a subgroup fairness report (O57) and 65+
  performance; no separate 65+ model (O58).
- **O40** ("which outcome to promote first") now chooses *among these four*; the recommendation stands
  — non-obstetric admission first.
- **Service work (M6, M7, M12)** builds the four labels' inputs on `meps-portable-v2`; any-stay
  (`meps25-v1`) stays only as the reproduced reference model from M2.

## 4. Parked work — kept, not deleted

| Item | Status | Where it lives | Pick it up by |
|---|---|---|---|
| **Any hospital stay** (the prototype's target) | Reference only — reproduced exactly; distorted by childbirth | M2 artifact; `meps25-v1`; round 001 §3 | Re-running `outcome_prediction.model.train` |
| **Number of ER visits** (count form) | Parked — modest ranking (Spearman 0.30) | Round 001 `cv_targets` / `confirm` (`ed_visits_y2`) | A config with `"label": "ed_visits_y2", "task": "count"` |
| **Total spending** (cost form) | Parked — barely beats last year's spend; needs claims; output isn't a probability (O35) | Round 001 (`cost_y2`) | A config with `"task": "cost"` |
| **Death** | Learning only (O48) — never promoted | Round 001 (`died_y2`) | Only with clinical governance |
| **Loss of insurance** | Learning only (O48) | Round 001 (`lost_insurance_y2`) | Only after a fairness review |
| Prototype's any-stay improvements (TF-IDF/LSA etc.) | Result recorded: 0.769 → 0.788, mostly pregnancy | Round 001 report §3 | — |
| Drug-name normalisation (character n-grams) | Result recorded; useful for future FHIR medication text | Round 002 §3, `drugnames.py` | `outcome-prediction-lab drug-names` |
| Autoencoders, random forest, monotonic constraints, tuning, knowledge scores, missingness strategies | Results recorded with verdicts | Round 001 §5, round 002 §2 | Configs in the lab |
| Explanations: SHAP, surrogate tree, narratives | In use for the four | `explain.py`, `narrate.py` | `outcome-prediction-lab explain` |

The lab table keeps every label (`data.add_targets`), so a parked target is one config away.

## 5. Ideas considered and dropped (or out of reach)

| Idea | Outcome | Why |
|---|---|---|
| **Find similar patients** (autoencoder embeddings, for reusing a care team's research) | **Dropped** by the repo owner, 2026-10-18, after critique | Similarity has to be specific to the intervention being reused; our own results suggest autoencoders wouldn't beat simpler, explainable methods; MEPS has no record of interventions, so no ground truth; showing other patients' records raises access, audit and anchoring concerns. If revisited: explainable facet matching within one customer's own panel, validated by clinicians |
| UK data (CPRD, OpenSAFELY) for training | Rejected at the start | Cost, research-only terms, aggregates only, different coding (`prototype-baseline.md` §2) |
| Area-level deprivation (ADI etc.) | Not usable for training | MEPS public files have only 4 regions; ADI forbids commercial use |
| "Potentially preventable admission" (AHRQ PQIs) | Deferred | Needs full ICD-10 codes; MEPS releases 3 characters |
| Uplift / impactability (who benefits from outreach) | Out of reach | MEPS has no intervention data (O37) |
| TF-IDF on code descriptions as model features | Tried, no gain for gradient boosting | Round 002 §2 |
