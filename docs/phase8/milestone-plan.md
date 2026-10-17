# Phase 8 Milestone Plan — Patient Outcome Prediction

M1–M11. All **planned, none started**.

Sequencing logic: **reproduce first** (M1–M3) — dataset, model, Synthea harness — so every later
number has a recorded baseline (O6). Then **make it usable end to end on the reproduced model**
(M4–M8): `client/clinical` plumbing, the FHIR extractor, the scoring service, the agent, and a
live acceptance case. Only then **improve the model** (M9–M11): better label, richer features,
code lists — each landing as a new contract version behind a service that already works.

This reverses the prototype's planned order, which improved the model before building the service
(`prd.md` §11 V12). The reason is risk: the FHIR mapping (O21) and the leakage rule (O10) are
the least certain parts of the design, and they're exercised by the service path, not by MEPS.
Finding out early whether real Synthea FHIR can feed the contract matters more than a
0.01 AUROC gain.

Parallelism: **M4** (`client/clinical` plumbing) needs only M1's scaffold and can run alongside
M2–M3; **M9** (label work, MEPS-only) needs only M2 and can run alongside M4–M8. The critical
path is M1 → M2 → M3 → M5 → M6 → M7 → M8.

## Mapping from the prototype's planned stages (O4)

| Prototype's planned stage | Here |
|---|---|
| Research prototype (done) | Provenance — `prototype-baseline.md` |
| Reproduce the prototype with tests and reports | M1, M2, M3 |
| Better label, richer features, tuning, 65+, explanations | M9, M10 (explanations moved up to M6) |
| Scoring API, batch job, FHIR and claims adapters, code lists | M4, M5, M6, M11 (batch from object storage and claims adapter deferred — `prd.md` §8) |
| *(not in the prototype's plan — this repo's conventions)* Agent surface, live acceptance case | M7, M8 |
| Deployment, monitoring, recalibration, first customer validation | Phase 8b |

---

### M1 — Service scaffold + MEPS dataset

**Short story:** Stand up `outcome-prediction-service/` and rebuild the MEPS modelling table
exactly.

**Long story:** Package skeleton per `design.md` §1 (`pyproject.toml`, `README.md`,
gitignored `data/` and `models/`), `phase8` compose profile placeholder, `phase8` CI job,
`pytest.ini` entry. Implement, from the method in `prototype-baseline.md` §4.1 (O7),
`meps/download.py`
(zipfile extraction, SHA-256 record), `meps/build.py` (with per-panel diagnosis-column
resolution logged — `design.md` §11 defect 6) and `meps/inspect.py`. Register MEPS in
`data/reference/README.md` with its use terms and the open AHRQ question (O13, O23).

**Deliverable:** 56,360 rows, 4,820 events, per-panel counts matching
`prototype-baseline.md` §3.1; HC-252 dictionary with 2,648 variables and the expected storage
counts. Phase 1 independence job still green.

**Depends on:** nothing new.

---

### M2 — Training, evaluation, artifact

**Short story:** Reproduce AUROC 0.769 / 0.708 and write the reports.

**Long story:** `model/train.py`, `model/evaluate.py`, `model/artifact.py`, implemented from
`prototype-baseline.md` §4.2–§4.3 and checked against §5.2 (O7). The artifact
carries both models (O18), a SHA-256 manifest (O17), the training score distribution (for
percentiles), and metadata stating that headline metrics come from the validation model, not
the release model (`design.md` §11 defect 5). `scikit-learn` pinned exactly (O12).

**Deliverable:** Test AUROC in [0.760, 0.778] (GBM) and [0.700, 0.716] (comparison);
`metrics.json` + `model_report.md` covering FR-E1–E5; a tampered manifest is refused.

**Depends on:** M1.

---

### M3 — Synthea CSV harness, scoring mode, leakage test

**Short story:** Reproduce the Synthea ETL as-is, then split training from scoring mode and fix
the prescription leak.

**Long story:** Generate one Synthea v4.0.0 population with CSV **and** FHIR export (O11) —
the FHIR half is used in M5. Implement the prototype's mapping rules
(`prototype-baseline.md` §6.3) as-is in `etl/extract/synthea_csv.py` + `etl/canonical.py` +
`etl/transform/to_contract.py`; confirm schema and sanity checks (`prd.md` §9, criterion 4).
**Then**, as a separate commit: the `as_of` scoring mode (`design.md` §6), the leakage test, unknown-state → 0, and one categorical rule for both modes (§11 defects 1, 3,
4). Commit a tiny Synthea fixture for CI; keep the `coronary` regression test.

**Deliverable:** Contract rows from Synthea CSV in both modes; the leakage test passes, and
fails on the reproduced (unfixed) code — proving it tests something.

**Depends on:** M2 (needs a model to score with).

---

### M4 — `client/clinical` extension (additive)

**Short story:** Give the clinical client the encounters, medication history and cost data the
contract needs, without changing anything existing callers see.

**Long story:** New domain dataclasses and methods (FR-F1), each returning clinical terms, never
raw bundles. Coordinate with Phase 7 M3 on `get_medications()`'s status filter — whichever
lands first defines it (O9). `triage-service`'s and `mcp-agent`'s test suites must pass
unmodified.

**Deliverable:** New methods with unit tests against recorded FHIR fixtures; all existing
`client/clinical` callers unaffected.

**Depends on:** nothing in Phase 8 beyond M1's scaffold; can start alongside M2–M3.

---

### M5 — FHIR extractor + parity + data-quality report

**Short story:** Build the canonical tables from `fhir-service`, and prove they match the CSV
path.

**Long story:** `etl/extract/fhir.py`. Load M3's FHIR half into `fhir-service`, then validate
every row of `design.md` §7's mapping sketch against what Synthea v4.0.0 actually emits —
recording each finding in the design doc (O21). The parity test (FR-F3) runs the same patients
through both extractors. Every feature records its contributing resources (FR-F4). The
data-quality report (FR-T6) flags missing/impossible values, unknown codes and distribution
drift vs MEPS — the place where Synthea's 25% coronary-disease rate (vs 5.6% in MEPS) shows up
as data, not surprise.

**Deliverable:** Parity holds, or every difference is listed with a reason; leakage test passes
on the FHIR extractor too; data-quality report generated.

**Depends on:** M3, M4.

---

### M6 — Scoring service → `RiskAssessment`

**Short story:** The API, returning FHIR.

**Long story:** `api.py` and `fhir/risk_assessment.py` per `design.md` §4–§5: both triggers,
`/health`, `/model`, artifact verification at startup, per-patient explanations (FR-M8), input
warnings, OpenTelemetry using `triage-service`'s pattern. Verify the outcome SNOMED code (O22).
Compose service under the `phase8` profile; port assigned.

**Deliverable:** A Synthea patient in `fhir-service` returns a valid FHIR R4 `RiskAssessment`
whose `basis` references resolve; contract-row batches return a `Bundle`; single-row latency
under 100 ms measured and recorded.

**Depends on:** M5.

---

### M7 — `outcome-prediction-agent`

**Short story:** Ask for a patient's hospitalization risk in plain language; get a grounded
answer.

**Long story:** New package on `agent-platform` (O15), self-hosted model by default (O16),
calling only `tools.py`'s three tools (`design.md` §9). `explain.py` narrates the
`RiskAssessment` — probability, comparison score, percentile, top reasons, model version — and
nothing else (FR-A2, FR-A3). Adversarial tests: "adjust for her new diagnosis", "is that high
risk?", "rank everyone over 20%" must not produce a number or band the service didn't return.

**Deliverable:** Grounding and adversarial suites pass in CI against the self-hosted model.

**Depends on:** M6.

---

### M8 — End-to-end acceptance case and demo

**Short story:** Everything, live, under the `phase8` profile.

**Long story:** Mirrors Phase 4 M5 and Phase 7 M12: `e2e/test_outcome_prediction_acceptance.py`
against real running services. Demo beats: (1) a seeded Synthea patient scored through the
API, with `basis` resolved back to their encounters and conditions; (2) the same patient
through the agent, narration traceable line by line to the `RiskAssessment`; (3) adding an
encounter dated after `as_of` and showing the score doesn't move.

**Deliverable:** The e2e suite passes; demo steps documented in `docs/demo-guide.md`.

**Depends on:** M7.

---

### M9 — Unplanned-stay label + round-3 handling → `meps25-v2`

**Short story:** Stop predicting childbirth.

**Long story:** FR-D4 and FR-D7 using the yearly Hospital Inpatient Stays files
(`prototype-baseline.md` §8): `label_unplanned_12m` excludes `RSNINHOS` 4/5/6, optionally
planned stays; round-3 items excluded or tested separately. Re-run the 18–44 sex check that
exposed the problem (7.4% vs 2.2%). Ships as contract/label `meps25-v2`; `v1` stays loadable.

**Deliverable:** Both labels' metrics side by side in the report; the women-18–44 rate gap
explained by the label change.

**Depends on:** M2. (Runs in parallel with M4–M8.)

---

### M10 — Richer features, tuning, 65+, fairness

**Short story:** Close the gap to the prototype's targets (AUROC ≥ 0.78; ≥ 0.73 for 65+).

**Long story:** FR-D5 (condition/CCSR and drug-class features from MEPS event files), FR-D6 as a
separately reported survey-only experiment, FR-M5 (panel-grouped CV on 21–25 only, 26–27
untouched), FR-M6 (65+), FR-E6 (fairness by race/ethnicity and insurance). Decide O25 with
numbers. Any feature that can't be derived from FHIR stays out of the FHIR-servable contract.

**Deliverable:** A new contract version with metrics against the targets, and an O25 decision
recorded in `decisions.md`.

**Depends on:** M9.

---

### M11 — Versioned clinical code lists

**Short story:** Replace description regexes with reviewed ICD-10-CM code lists.

**Long story:** FR-T4: SNOMED CT → ICD-10-CM via the NLM map (UMLS licence, free in the US —
an account the repo owner holds, not a repo secret), truncated to 3 characters, one versioned
list per diagnosis flag under `etl/codelists/`. `data/reference/icd10/` is reused where it
covers the need. Lists ship marked "unreviewed" until O27 has an owner.

**Deliverable:** Both extractors use the code lists; the parity and `coronary` regression tests
still pass; flag prevalence on Synthea compared before/after in the data-quality report.

**Depends on:** M5.

---

## What's explicitly not a milestone here

Per `prd.md` §8: cloud deployment, recalibration on customer data, monitoring, population batch
from object storage, first customer validation (all **Phase 8b**); a claims-file adapter;
persisting `RiskAssessment` to `fhir-service`; a Kong route; a worklist UI; qualitative risk
bands. None of these gets a milestone number; adding one later is a new decision, not an
oversight in this plan.
