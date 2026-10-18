# Phase 8 Experimentation Protocol — Running a Research Round

The standing procedure for exploring models and prediction targets with
`outcome-prediction-lab/`. It applies to **every** round, by anyone, at any time, long after
Phase 8's milestones are complete (`decisions.md` O28). Milestone M3 builds the tooling this
document refers to; M10 and M11 are the first two rounds run under it.

> **This document is a runbook, not a status page.** Phase 8's status lives in
> [`README.md`](./README.md); a round's results live in its own committed directory (§3).
> If a step below no longer matches the tooling, fix this document in the same change.

---

## 1. When to start a round

Start a round when there's a question the current model can't answer with a number already
on record. Typical triggers:

- A new outcome or prediction form is worth evaluating (O34).
- A new feature group, label definition or model family is proposed.
- AHRQ publishes a new MEPS panel (also triggers a holdout rotation — §5).
- A customer's data shows a feature isn't portable (O25) and an alternative is needed.
- A served model's assumptions are questioned (fairness, calibration, a subgroup).

Don't start a round to tune a number nobody has asked about.

## 2. The rules every round follows

1. **Training panels only for exploration.** All comparisons use panel-grouped cross-validation
   within training panels (21–25 today). Never select, tune or compare on the test panels (O32).
2. **The test set is for confirmation, and every look is logged.** Opening the test panels
   requires a candidate named *before* the look and an appended entry in the holdout ledger
   (§5). The CLI enforces this; don't work around it.
3. **Only config-driven runs count.** A notebook can suggest an idea; a result in a round report
   must come from a committed config re-runnable with the lab's CLI (O38).
4. **Public data only.** MEPS public files and Synthea. No customer data, no PHI, nothing sent
   to an online service (prd §4, O16).
5. **Reproduce before you compare.** Each round re-runs the current served model's config first,
   so its baseline numbers come from the same code and library versions as the new ones.
6. **Synthea is never evidence of accuracy.** It may appear only as a pipeline check.

## 2a. The command line

Every step below has a command (`outcome-prediction-lab --help`):

| Step | Command |
|---|---|
| Run configs (CV, training panels only) | `outcome-prediction-lab run <round> <config> [...]` |
| Compare a round's runs | `outcome-prediction-lab compare <round>` (writes `comparison.md`) |
| Confirm a finalist (one logged test look) | `outcome-prediction-lab confirm <round> <config> --record "why"` |
| Model card / target scorecard | `outcome-prediction-lab card` / `scorecard <round> <config> [--criteria person.json]` |
| Promote (needs a decision ID) | `outcome-prediction-lab promote <round> <config> --decision O<n>` |
| Explain patients | `outcome-prediction-lab explain <round> <config> --patient ID / --sample N / --all` |
| Notebook hygiene | `outcome-prediction-lab notebooks-check` (CI) / `notebooks-strip <file>` |

Configs live in `rounds/<round>/configs/<name>.json` and may only say *what* to model (label, task,
features, model, text representations, parameters, baseline inputs); any key naming panels or splits
is refused.

## 3. Steps

1. **Open the round.** Create `outcome-prediction-lab/rounds/NNN-<slug>/` (next free number)
   with a `README.md` stating the question, the candidates, the success criteria and which
   test-panel confirmation (if any) is planned. Commit it before running anything — the
   pre-registration.
2. **Write configs.** One config per candidate under the round's `configs/`: label definition,
   prediction form, feature set (contract version), model family and hyperparameter search
   space, seeds.
3. **Run.** Execute the configs with the lab CLI. Runs are tracked in the local MLflow store
   (O30) with data checksums, code commit, config, seed, metrics and artifacts.
4. **Compare on cross-validation.** Use the lab's comparison report. Look at subgroups and
   calibration, not only AUROC.
5. **Fill the scorecard.** For each serious candidate, complete the target scorecard (§4) —
   ML criteria from the runs, non-ML criteria by a person with written rationale.
6. **Confirm (optional, logged).** For at most the candidates named in step 1, append to the
   holdout ledger and run the test-panel evaluation.
7. **Write the round report.** `report.md` in the round directory: question, what was run,
   cross-validated results, scorecards, any confirmation results, conclusion, and what's left
   open. Export summary metrics to `metrics.json` beside it.
8. **Decide.** A round ends in one of: *no change*; *candidate* (with model card, O39) awaiting
   promotion; or *recommend promotion*, which needs a new `decisions.md` entry (§6).
9. **Commit** the round directory, ledger entries and any protocol fixes together.

## 4. The target scorecard (O36)

| Criterion | Source | Notes |
|---|---|---|
| Discrimination (AUROC/AUPRC, or the form's equivalent) | CV runs | With bootstrap intervals |
| Calibration | CV runs | By decile; mean predicted vs actual |
| Subgroup performance and fairness | CV runs | Age band, sex, prior use, race/ethnicity, insurance |
| Base rate | Data | Very rare outcomes make poor worklists |
| Measurable in FHIR / claims | Person | Can a customer's own data observe this outcome? If not: no validation, no recalibration |
| Actionable for care management | Person | What would a care manager do differently? |
| Lead time | Person | Is there time to act before the outcome? |
| FHIR representability | Person | Probability → `RiskAssessment` natively; count/cost needs a decision revisiting O3 (O35) |
| Regulatory posture | Person | Does this change the FDA CDS position? |
| Uplift / impactability | — | Always "not assessable with MEPS" (O37) |

## 5. The holdout ledger and rotation (O32)

`outcome-prediction-lab/holdout-ledger.md` is append-only: date, round, candidate config, who,
and why the look was needed. The lab CLI refuses a test-panel evaluation unless the candidate
has a ledger entry.

**Rotation.** When AHRQ releases a newer two-year longitudinal panel: it becomes the
confirmation set; the previous test panels join the training panels; the ledger records the
rotation; and the next round re-establishes the served model's baseline on the new split.

## 6. Promotion (O33)

A candidate reaches production only by: a round report recommending it → a model card → a new
`decisions.md` entry (and, for a non-probability form, the O35 decision) → a new contract or
target version → an artifact carrying a promotion record. `outcome-prediction-service` refuses
artifacts without one. The first promotion is milestone M12; later promotions follow the same
steps without a new milestone.

## 7. Resuming after a long gap

1. Read the latest round reports in `outcome-prediction-lab/rounds/` and the holdout ledger.
2. Re-run the served model's config and confirm its recorded numbers (§2 rule 5). If they
   moved, find out why before anything else — library versions are the usual cause.
3. Check whether AHRQ has published new panels (§5).
4. Open a new round.
