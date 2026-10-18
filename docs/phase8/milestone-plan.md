# Phase 8 Milestone Plan — Patient Outcome Prediction

M1–M13. **M1–M6 built** (verified results below; M3 closed 2026-10-18, O60); M7–M13 planned. M10 and M11 are folded into M3 (O45). Expanded from M1–M11 after a second scope pass added a
dedicated experimentation track (`decisions.md` O28–O40): M3 (workbench) and M12 (promotion)
are new, and the former model-improvement milestones are now rounds of the
[experimentation protocol](./experimentation-protocol.md).

Three tracks:

- **Baseline (M1–M2).** Reproduce the prototype's dataset and model exactly, so every later
  number has a recorded reference (O6).
- **Service (M4–M9).** Make the reproduced model usable end to end: Synthea harness and leakage
  rule, `client/clinical` plumbing, the FHIR extractor, the scoring service, the agent, a live
  acceptance case.
- **Research (M3, M10–M12).** Build the experimentation workbench once (M3), run its first two
  rounds (M10: what to predict and in what form; M11: improve the chosen targets), and promote
  the winner into the running service (M12). M13 (code lists) closes the phase.

**Why service before model improvement** (`prd.md` §11 V12): the FHIR mapping (O21) and the
leakage rule (O10) are the least certain parts of the design, and only the service path
exercises them. Finding out early whether real Synthea FHIR can feed the contract matters more
than a 0.01 AUROC gain. The research track runs **in parallel**, so this costs no calendar time.

**Parallelism.** After M2, the service and research tracks are independent until M12. M5
needs only M1's scaffold and can start alongside M2. Critical path for the service:
M1 → M2 → M4 → M6 → M7 → M8 → M9. Research: M2 → M3 → M10 → M11, joining at M12 (which also
needs M7).

**After the phase.** M3's tooling outlives the phase. Later explorations are new *rounds*
under the protocol, never reopened milestones (O28); later promotions follow M12's steps
without a new milestone.

## Mapping from the prototype's planned stages (O4)

| Prototype's planned stage | Here |
|---|---|
| Research prototype (done) | Provenance — `prototype-baseline.md` |
| Reproduce the prototype with tests and reports | M1, M2, M4 |
| Better label, richer features, tuning, 65+, explanations | M10, M11 as protocol rounds (explanations moved up to M7) |
| Scoring API, batch job, FHIR and claims adapters, code lists | M5, M6, M7, M13 (batch from object storage and claims adapter deferred — `prd.md` §8) |
| *(not in the prototype's plan)* Experimentation workbench, promotion path | M3, M12 |
| *(not in the prototype's plan — this repo's conventions)* Agent surface, live acceptance case | M8, M9 |
| Deployment, monitoring, recalibration, first customer validation | Phase 8b |

---

### M1 — Service scaffold + MEPS dataset

**Short story:** Stand up `outcome-prediction-service/` and rebuild the MEPS modelling table
exactly.

**Long story:** Package skeleton per `design.md` §1 (`pyproject.toml`, `README.md`,
gitignored `data/` and `models/`), `phase8` CI job, `pytest.ini` entry. (The `phase8` compose
profile moves to M7: until the API exists there is nothing for a compose service to run.) Implement, from the method in `prototype-baseline.md` §4.1 (O7),
`meps/download.py` (zipfile extraction, SHA-256 record), `meps/build.py` (with per-panel
diagnosis-column resolution logged — `design.md` §11 defect 6) and `meps/dictionary.py`. Register
MEPS in `data/reference/README.md` with its use terms and the open AHRQ question (O13, O23).

**Deliverable:** 56,360 rows, 4,820 events, per-panel counts matching
`prototype-baseline.md` §3.1; HC-252 dictionary with 2,648 variables and the expected storage
counts. Phase 1 independence job still green.

**Depends on:** nothing new.

**Verified (M1 built):** reproduced **exactly** against real AHRQ downloads with pandas 3.0.6 /
Python 3.12 — `(56360, 31)`, 4,820 events, and every per-panel persons / adults / events figure
in `prototype-baseline.md` §3.1; HC-252 dictionary 2,648 variables with identical storage
counts. Diagnosis-column resolution unambiguous in every panel (`design.md` §11 defect 6).
Downloads: 38 MB zipped, 721 MB extracted. Tests: 27 pass with the MEPS cache; 17 pass and 10
self-skip without it (the CI configuration).

---

### M2 — Training, evaluation, artifact

**Short story:** Reproduce AUROC 0.769 / 0.708 and write the reports.

**Long story:** `model/train.py`, `model/evaluate.py`, `model/artifact.py`, implemented from
`prototype-baseline.md` §4.2–§4.3 and checked against §5.2 (O7). The artifact carries both
models (O18), a SHA-256 manifest (O17), the training score distribution (for percentiles), and
metadata stating that headline metrics come from the validation model, not the release model
(`design.md` §11 defect 5). `scikit-learn` pinned exactly (O12). Training and evaluation are
written as importable functions, not only CLIs — the lab (M3) calls them (O29).

**Deliverable:** Test AUROC in [0.760, 0.778] (GBM) and [0.700, 0.716] (comparison);
`metrics.json` + `model_report.md` covering FR-E1–E5; a tampered manifest is refused.

**Depends on:** M1.

**Verified (M2 built):** with `scikit-learn` 1.9.1 (the prototype's version; wheels confirmed
for Python 3.11 and 3.12), the reproduction is **exact to every reported digit**, not merely
within tolerance: GBM AUROC 0.769 [0.754, 0.786], comparison 0.708 [0.691, 0.725], AUPRC, Brier,
top-k, survey-weighted AUROC 0.780, all ten calibration deciles, all seven subgroups, the
permutation-importance ranking and the comparison coefficients (-4.047, 0.0280, 1.3055) — every
figure in `prototype-baseline.md` §5.2. Bootstrap CIs match because the shared generator is
consumed in the prototype's order. Release artifact `gbm-meps25-v1-950d8be12078` (ID derived from
the training table's checksum); a one-byte change to any file is refused before deserialisation.
`train` + `evaluate` take ~18 s. Tests: 63 pass with the MEPS cache; 48 pass and 15 self-skip
without it (CI).

---

### M3 — Experimentation workbench: `outcome-prediction-lab`

**Short story:** Build, once, the tools anyone can use at any time to explore models and
prediction targets without eroding the test set.

**Long story:** New top-level package `outcome-prediction-lab/` (O29) per `design.md` §12:
local MLflow tracking and model registry (O30); config-driven runs with panel-grouped
cross-validation on training panels only; `targets.py` for label definitions across outcome ×
form (O34), with every MEPS variable confirmed by `dictionary.py` before use; the holdout ledger
and a CLI that refuses unlogged test-panel evaluation (O32); the target scorecard (O36) and
model-card generator (O39); output-stripped notebooks checked in CI (O38). Write
[`experimentation-protocol.md`](./experimentation-protocol.md) into its final form against the
real CLI. **Round 000** proves the tooling: re-run M2's model through the lab and match M2's
numbers.

**Deliverable:** `rounds/000-baseline-reproduction/` committed, with the lab's
cross-validated numbers consistent with M2; the CLI's test-panel guard and config guard each
covered by a test that shows them refusing; a model card for the `meps25-v1` model.

**Depends on:** M2. (Runs in parallel with the whole service track.)

**Re-scoped (O45):** M3 now also carries M10 and M11's work — it builds the lab *while* running
real, iterative rounds, and ends when the repo owner decides no further iteration is needed.

**Iteration 1 done — round 001** (`outcome-prediction-lab/rounds/001-what-and-how/report.md`):
on the prototype's exact objective and test panels, AUROC 0.769 → 0.788 (+0.019 [+0.011, +0.027]),
AUPRC 0.265 → 0.307 — mostly from code features (TF-IDF → LSA), and mostly because pregnancy codes
predict childbirth admissions; seven new targets, all beating simple baselines; concept-by-concept
verdicts. Built: lab table (28 MEPS files, IDs normalised), honest missing encoding, code
"documents", vendored HFRS/Charlson/Elixhauser, pipelines, leave-one-panel-out CV, paired bootstrap,
holdout ledger with guard, SHAP narratives, surrogate tree, value-of-information action items.
**Iteration 2 done — round 002** (`outcome-prediction-lab/rounds/002-text-and-explanations/report.md`):
the `outcome-prediction-lab` CLI (run / compare / confirm / card / scorecard / promote / explain /
drug-names / notebook check, in CI); every code named in plain language (O49); self-explanatory
per-patient narratives with comparison groups (O50); TF-IDF on code descriptions (no gain for
gradient boosting, +0.002 for a linear model); character n-grams for drug names (72.6% vs 68.4% class
accuracy on unseen names); a drug-class defect fixed (O51). No test look (pre-registered bar not met).

**Iteration 3 done — round 003** (`outcome-prediction-lab/rounds/003-portable-contract/report.md`): the
portable feature contract `meps-portable-v2` (O52) with "drop, don't impute" and missingness
augmentation (O53), and outcome observability (O54); O25 resolved. Production-contract models on the
test panels: non-obstetric admission 0.795, any ER visit 0.740, high cost 0.834 (with claims).
**M6 and M7 now build against `meps-portable-v2`**, not `meps25-v1`.

**Focus (O55, 2026-10-18):** four predictions — admission through the ER, non-obstetric hospital stay,
any ER visit, high-cost patient ([`prediction-targets.md`](./prediction-targets.md)). Remaining M3 work
applies to these four.

**Iteration 4 done — round 004** (`outcome-prediction-lab/rounds/004-focus-four-readiness/report.md`):
admission through the ER on the production contract (`er-admit-v2`, test AUROC 0.785; O56) — **all four
focus predictions now have a production-contract model**; subgroup fairness reports for all four on
their model cards (FR-E6, O57); a 65+ check for all four — the general models beat 65+ specialists by
0.02–0.04 CV AUROC, so no separate 65+ model (FR-M6, O58).

**Round 000 done** (`outcome-prediction-lab/rounds/000-baseline-reproduction/report.md`): M2's
`meps25-v1` models reproduced through the lab CLI **bit for bit** (test AUROC 0.769008… / 0.707620…),
by calling the service's own fitting code (`"model": "meps25-v1"`); lab CV AUROC 0.768 / 0.686; model
card for `meps25-v1`. The original M3 deliverable is complete.

**M3 closed (O60, 2026-10-18).** Person-scored scorecard criteria recorded for all four focus models;
**O40 decided (O59): the first promotion is non-obstetric hospital stay** (`nonobstetric-v2`, on
`meps-portable-v2`), which M12 serves beside `meps25-v1`. The lab stays open for rounds on demand.

---

### M4 — Synthea CSV harness, scoring mode, leakage test

**Short story:** Reproduce the Synthea ETL as-is, then split training from scoring mode and fix
the prescription leak.

**Long story:** Generate one Synthea v4.0.0 population with CSV **and** FHIR export (O11) —
the FHIR half is used in M6. Implement the prototype's mapping rules
(`prototype-baseline.md` §6.3) as-is in `etl/extract/synthea_csv.py` + `etl/canonical.py` +
`etl/transform/to_contract.py`; confirm schema and sanity checks (`prd.md` §9, criterion 4).
**Then**, as a separate commit: the `as_of` scoring mode (`design.md` §6), the leakage test,
unknown-state → 0, and one categorical rule for both modes (§11 defects 1, 3, 4). Commit a tiny
Synthea fixture for CI; keep the `coronary` regression test.

**Deliverable:** Contract rows from Synthea CSV in both modes; the leakage test passes, and
fails on the reproduced (unfixed) code — proving it tests something.

**Depends on:** M2 (needs a model to score with).

**Verified (M4 built):** Synthea v4.0.0 (pinned by SHA-256, O61), the prototype's population: 2,916
adults alive at the end of 2023. Reproduced as-is (`prototype_training_rows`), the profile matches the
prototype's run (`prototype-baseline.md` §6.4): 2,913 adults there; pipeline-check AUROC 0.656 (0.656
there), mean predicted 10.2% (10.5%), coronary 24.1% (25.1%), arthritis 11.9% (12%), mean fills 33.9
(33.8), any home health 0.45% (0.4%); year-2 stay rate 6.0% (4.7%). **Never evidence of accuracy.**
Fixed mapping (O62): schema and sanity checks pass in both modes; only `rxtoty1`, `totexpy1` and
`ipngtdy1` change (stays crossing 31 December now count nights up to it); AUROC 0.655. The leakage test
passes, and fails on the reproduced code. Committed fixture: 7 adults, 172 KB. Tests: 18 new.

---

### M5 — `client/clinical` extension (additive)

**Short story:** Give the clinical client the encounters, medication history and cost data the
contract needs, without changing anything existing callers see.

**Long story:** New domain dataclasses and methods (FR-F1), each returning clinical terms, never
raw bundles. Coordinate with Phase 7 M3 on `get_medications()`'s status filter — whichever
lands first defines it (O9). `triage-service`'s and `mcp-agent`'s test suites must pass
unmodified.

**Deliverable:** New methods with unit tests against recorded FHIR fixtures; all existing
`client/clinical` callers unaffected.

**Depends on:** M1's scaffold only; can start alongside M2.

**Verified (M5 built):** six additive methods and dataclasses (O63) — demographics, encounters,
medication history, dispenses, care costs (ExplanationOfBenefit) and coverage — reading every page,
with paging links replayed through the gateway. Checked live against HAPI v7.2.0 loaded with 10
Synthea v4.0.0 patients (up to 401 claims and 336 prescriptions for one patient); unit tests replay a
recorded, de-identified conversation (17 new tests, 54 in the package). `get_medications()` is
unchanged (its exact request is pinned by a test); `triage-service` and `mcp-agent` pass unmodified
(146 passed; 4 live-Ollama tests need a local model, same on `main`). What Synthea's FHIR does and
doesn't carry is recorded for M6 (O64).

---

### M6 — FHIR extractor + parity + data-quality report

**Short story:** Build the canonical tables from `fhir-service`, and prove they match the CSV
path.

**Long story:** `etl/extract/fhir.py`. Load M4's FHIR half into `fhir-service`, then validate
every row of `design.md` §7's mapping sketch against what Synthea v4.0.0 actually emits —
recording each finding in the design doc (O21). The parity test (FR-F3) runs the same patients
through both extractors. Every feature records its contributing resources (FR-F4). The
data-quality report (FR-T6) flags missing/impossible values, unknown codes and distribution
drift vs MEPS — the place where Synthea's 25% coronary-disease rate (vs 5.6% in MEPS) shows up
as data, not surprise.

**Deliverable:** Parity holds, or every difference is listed with a reason; leakage test passes
on the FHIR extractor too; data-quality report generated.

**Depends on:** M4, M5.

**Verified (M6 built):** `etl/extract/fhir.py` (O65) on one Synthea v4.0.0 run exported as CSV and
FHIR and loaded into HAPI v7.2.0 (33 patients, 0 load errors). **Parity holds** (`etl/parity.py`):
year 1 = 2023, 20 adults, 19 of 26 columns identical; the rest — income default, office/outpatient
merged, hospice, a year-2 SNF stay, fills and prescription costs from claims — each explained and
verified by code (2022: 20 identical). Leakage test passes on the FHIR path (records after `as_of`
injected into the server's responses change nothing). Every feature value cites its records
(FR-F4, `explain=True`). Data-quality report (`etl/quality.py`, FR-T6) against committed MEPS
aggregates: Synthea's coronary disease 24.1% vs 5.4% flagged, with 9 other alerts (one state,
asthma, arthritis, spending ×9, fills ×3 …). Missing income now defaults to 4 with a warning (O66),
not silently to 5. Client additions found necessary: `get_condition_history` (paged) and referenced
medicines in `get_medication_history`. Tests: 18 new (service), 3 new (client).

---

### M7 — Scoring service → `RiskAssessment`

**Short story:** The API, returning FHIR.

**Long story:** `api.py` and `fhir/risk_assessment.py` per `design.md` §4–§5: both triggers,
`/health`, `/model`, artifact verification at startup, per-patient explanations (FR-M8), input
warnings, OpenTelemetry using `triage-service`'s pattern. Verify the outcome SNOMED code (O22).
Compose service under the `phase8` profile; port assigned. Serves the `meps25-v1` model, whose
approval is decisions O2/O3 themselves (`design.md` §8).

**Deliverable:** A Synthea patient in `fhir-service` returns a valid FHIR R4 `RiskAssessment`
whose `basis` references resolve; contract-row batches return a `Bundle`; single-row latency
under 100 ms measured and recorded.

**Depends on:** M6.

---

### M8 — `outcome-prediction-agent`

**Short story:** Ask for a patient's hospitalization risk in plain language; get a grounded
answer.

**Long story:** New package on `agent-platform` (O15), self-hosted model by default (O16),
calling only `tools.py`'s three tools (`design.md` §9). `explain.py` narrates the
`RiskAssessment` — probability, comparison score, percentile, top reasons, model version — and
nothing else (FR-A2, FR-A3). Adversarial tests: "adjust for her new diagnosis", "is that high
risk?", "rank everyone over 20%" must not produce a number or band the service didn't return.

**Deliverable:** Grounding and adversarial suites pass in CI against the self-hosted model.

**Depends on:** M7.

---

### M9 — End-to-end acceptance case and demo

**Short story:** Everything, live, under the `phase8` profile.

**Long story:** Mirrors Phase 4 M5 and Phase 7 M12: `e2e/test_outcome_prediction_acceptance.py`
against real running services. Demo beats: (1) a seeded Synthea patient scored through the
API, with `basis` resolved back to their encounters and conditions; (2) the same patient
through the agent, narration traceable line by line to the `RiskAssessment`; (3) adding an
encounter dated after `as_of` and showing the score doesn't move.

**Deliverable:** The e2e suite passes; demo steps documented in `docs/demo-guide.md`.

**Depends on:** M8.

---

### M10 — Round 001: what to predict, and in what form *(folded into M3 — O45)*

**Short story:** The first real research round — decide which outcomes and prediction forms
are advisable, by scorecard, not by metric alone.

**Long story:** Run under the protocol (pre-registered in
`outcome-prediction-lab/rounds/001-target-study/`). Candidates span outcome × form (O34): any
inpatient stay (the baseline), **unplanned stay** (excluding childbirth/pregnancy, `RSNINHOS`
4/5/6, optionally planned stays — FR-D4, `prototype-baseline.md` §8), ED visits, hospital
nights and high cost; forms of event probability, expected count, cost and ordinal tier where
they apply. Round-3 items excluded or tested separately (FR-D7). Re-run the 18–44 sex check that
exposed the childbirth problem (7.4% vs 2.2%). Every serious candidate gets a full scorecard
(O36) — including measurability in FHIR/claims, actionability, FHIR representability (O35),
and the explicit uplift gap (O37). Confirmation on the test panels only for the named
finalists, through the ledger.

**Deliverable:** Round report with scorecards and model cards; O40 decided — which
outcome(s) and form(s) to take forward — as a new `decisions.md` entry; for any
non-probability form chosen, the O35 representation decision too.

**Depends on:** M3.

---

### M11 — Round 002: improve the chosen target(s) *(folded into M3 — O45)*

**Short story:** Close the gap to the prototype's targets (AUROC ≥ 0.78; ≥ 0.73 for 65+) for
what M10 chose.

**Long story:** Run under the protocol. FR-D5 (condition/CCSR and drug-class features from
MEPS event files), FR-D6 as a separately reported survey-only experiment, FR-M5 (hyperparameter
search via the lab's panel-grouped CV), FR-M6 (65+), FR-E6 (fairness by race/ethnicity and
insurance). Decide O25 (non-portable features) with numbers. Any feature that can't be derived
from FHIR stays out of the servable contract.

**Deliverable:** Round report; a candidate with model card, recommended for promotion as a new
contract version; O25 recorded in `decisions.md`.

**Depends on:** M10.

---

### M12 — First promotion into the service

**Short story:** Exercise the promotion path end to end, once, so it's proven before anyone
relies on it.

**Long story:** `promote.py` writes `PROMOTION.json` (O33, `design.md` §8); the service
starts refusing artifacts without it, and the `meps25-v1` artifact gets its retrofitted record.
Serve M11's candidate as a new contract/target version beside `meps25-v1`: FHIR extractor and
`to_contract.py` extended for its features, `RiskAssessment` outcome coding and window updated
for its target, the agent's narration checked against it, M9's acceptance case extended. If M10
chose a non-probability form, implement the representation O35 decided.

**Deliverable:** Both versions servable; an unpromoted artifact is refused (tested); the e2e
suite passes for the new version.

**Depends on:** M7 (service), M11 (candidate).

---

### M13 — Versioned clinical code lists

**Short story:** Replace description regexes with reviewed ICD-10-CM code lists.

**Long story:** FR-T4: SNOMED CT → ICD-10-CM via the NLM map (UMLS licence, free in the US —
an account the repo owner holds, not a repo secret), truncated to 3 characters, one versioned
list per diagnosis flag under `etl/codelists/`. `data/reference/icd10/` is reused where it
covers the need. Lists ship marked "unreviewed" until O27 has an owner.

**Deliverable:** Both extractors use the code lists; the parity and `coronary` regression tests
still pass; flag prevalence on Synthea compared before/after in the data-quality report.

**Depends on:** M6.

---

## What's explicitly not a milestone here

Per `prd.md` §8: cloud deployment, recalibration on customer data, monitoring, population batch
from object storage, first customer validation (all **Phase 8b**); a shared or hosted
experiment-tracking server (Phase 8b); a claims-file adapter; persisting `RiskAssessment` to
`fhir-service`; a Kong route; a worklist UI; qualitative risk bands; uplift/impactability
modelling (O37). Future research rounds and promotions after M12 are protocol runs, not
milestones (O28). None of these gets a milestone number; adding one later is a new decision,
not an oversight in this plan.
