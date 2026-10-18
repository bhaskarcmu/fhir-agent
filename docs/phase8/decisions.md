# Phase 8 — Decisions

ADR-style index, same convention as Phase 2 (`D`/`C`), Phase 3 (`P`), Phase 4 (`E`), Phase 6
(`H`), Phase 7 (`R`). `O` here stands for **O**utcome prediction. Each entry: status, one-line
rationale, and where the full reasoning lives — this repo's chat-driven planning process,
captured in `prd.md` and `design.md`, plus `prototype-baseline.md` where a decision is
carried over from the research prototype that seeded this phase.

## Scope and shape (repo owner's decisions)

| ID | Decision | Status | Rationale / where it lives |
|---|---|---|---|
| O1 | Phase 8 is **patient outcome prediction with machine learning**; the first outcome is the probability of at least one inpatient stay in the next 12 months, for adults | Accepted | Repo owner's chosen focus. The service is named for the general capability, not the first model, so a later outcome (e.g. ED visits) is a new model inside the same service, not a new phase-sized rename. Which further outcomes and prediction forms are worth serving is explored in `outcome-prediction-lab` (O28, O34) and served only through promotion (O33, M12). `prd.md` §1. |
| O2 | The model runs in **one new top-level service**, `outcome-prediction-service/` — not in `triage-service`, not in any agent | Accepted | Repo owner's decision. Also the repo's monolith-first precedent (Phase 4 `epic-emulator`, Phase 7 R8): dataset build, training, evaluation, the ETL adapters and the scoring API live as subpackages of one service until real evidence shows where a cut belongs. Name is not load-bearing — cheap to rename before code exists. `design.md` §1. |
| O3 | Predictions are returned as **FHIR `RiskAssessment`** resources carrying a numeric probability, the same resource type `triage-service` returns | Accepted | Repo owner's decision. `triage-service`'s Pydantic `PredictionModel` has `outcome` + `qualitativeRisk` only — no `probabilityDecimal` — so Phase 8 defines its **own** superset models; `triage-service` is not modified (pattern precedent, not shared code — the same stance Phase 7 took with `claims-service`'s `FhirArtifactBuilder`). Supersedes the prototype's planned custom `/v1/score` JSON. `design.md` §4. |

## Reconciling the prototype's plan with this repo

| ID | Decision | Status | Rationale / where it lives |
|---|---|---|---|
| O4 | The prototype's own numbered stages are **not used**; its planned work becomes **Phase 8 milestones M1–M13** plus a deferred **Phase 8b**; never "Phase 8.x" | Accepted | "Phase" is reserved for top-level phases (`docs/README.md` conventions), and the prototype's stage numbers collided with this repo's phase numbers. The prototype itself is provenance, not a milestone; reproduction → M1, M2, M4; service, adapters and code lists → M5–M7 and M13; model improvement → M10–M11, run as rounds of the experimentation protocol (O28); M3 (experimentation workbench), M8–M9 (agent, end-to-end acceptance) and M12 (promotion) are new, from this repo's conventions and the second pass below; cloud, monitoring, recalibration and customer validation → Phase 8b, mirroring Phase 2b/3b. Mapping table: `milestone-plan.md`. |
| O5 | The raw hand-off documents (draft PRD, preliminary design, developer notes with prototype code) are **not kept in the repo**. What they established is restated in conformant form in `prototype-baseline.md`, `prd.md` and `design.md` | Accepted | Repo owner's decision: the raw files used their own phase numbering and standalone-repo instructions, which would mislead future searches of this repo. This deliberately departs from Phase 2's `source-prd.md` archive precedent. The repo owner holds the originals. Every deviation from the prototype's plan is listed in `prd.md` §11. |
| O6 | **Reproduce before change.** The prototype's dataset counts and metrics are reproduced within the prototype's tolerances (`prototype-baseline.md` §5) before any modelling or mapping logic is altered; known prototype defects (`design.md` §11) are fixed only after the reproduction is recorded | Accepted | Without a reproduced baseline, a later number can't be attributed to a fix vs. a drift. Same "verified numbers at every milestone" discipline as `phase3/design.md` §13. |
| O7 | The prototype's scripts are **not committed**. The package is implemented from the method recorded in `prototype-baseline.md` §4 and §6.3 and validated against the numbers in §5 | Accepted | The repo convention is one package per component with tests; two parallel implementations (flat scripts + package) would drift. The recorded method gives every parameter needed (hyperparameters, seeds, filters, mapping rules); the recorded numbers are the acceptance test. |
| O8 | The production input path is **FHIR from `fhir-service`, read through `client/clinical`** — built in this phase (M5–M6), not "later". The Synthea CSV adapter is kept only as the reproduction and parity harness | Accepted | This repo already generates Synthea patients as FHIR and serves them from `fhir-service`; the prototype's standalone repo had neither. FHIR is how every other phase reads patient data. `design.md` §7. |
| O9 | `client/clinical` is extended **additively** — new domain dataclasses and methods for encounters, medication history and claim/EOB costs; existing methods' defaults and every existing caller's behaviour unchanged | Accepted | CLAUDE.md: `client/clinical` speaks clinical domain terms, never raw bundles. **Coordination with Phase 7 M3**, which also widens `get_medications()` (optional status filter): whichever phase lands first defines that signature and the other reuses it — never two different filters. |
| O10 | **Scoring-mode as-of semantics:** features come from the 12 months ending at an explicit `as_of` date; no record dated after `as_of` is read in scoring mode; a leakage test (records added after `as_of` change nothing) is mandatory | Accepted | The prototype's design states the principle but the prototype breaks it (`design.md` §11, defect 1). Calendar-year windows are kept only where reproducing MEPS/prototype numbers requires them. `design.md` §6. |
| O11 | Synthea runs use the **repo's pinned Synthea v4.0.0 on the devcontainer's Java 21**, not `master-branch-latest` on a downloaded Java 17. Phase 8's runs export CSV **and** FHIR from the same generation, via phase-local command-line overrides — `data/synthea/synthea.properties` is not edited | Accepted | One pinned version answers the prototype's own reproducibility concern. Same-run CSV + FHIR gives a free parity test (identical patients through both adapters → identical feature rows). Shared generator config stays untouched for earlier phases. |
| O12 | **Repo conventions override the prototype's tooling:** `requires-python = ">=3.11"` (CI runs 3.11), a per-package `pyproject.toml`, module CLIs instead of a Makefile, the existing devcontainer, a `phase8` compose profile, a `phase8` job in the existing `.github/workflows/tests.yml`, and an entry in the root `pytest.ini` `testpaths`. `scikit-learn` is pinned **exactly** | Accepted | Every prior phase is additive in exactly this shape; CI's Phase 1 independence job asserts a plain `docker compose up` still resolves to `fhir mcp-agent triage`. Exact `scikit-learn` pin because pickled models aren't portable across its versions (`prototype-baseline.md` §4.4). |
| O13 | Data and dependency licences are recorded in the **existing** places — `NOTICE` for third-party code, `data/reference/README.md` for data sources (MEPS, Synthea outputs) — not a new `LICENSES.md` | Accepted | One licence record per kind, not two. |
| O14 | `outcome-prediction-service` is **internal-only**: no Kong route this phase | Accepted | Phase 3 precedent ("everything new is internal-only"). Exposing it at the edge is a gateway/infra change, which CLAUDE.md says to stop and ask about; it belongs with Phase 8b. |
| O15 | The conversational surface is a **new package, `outcome-prediction-agent/`, built on `agent-platform`**; `mcp-agent` is not modified | Accepted | Every phase's "explains and orchestrates" agent is its own package (Phase 7 R22); modifying `mcp-agent` would put a Phase 8 dependency inside the Phase 1 independence job. Built on Phase 6 infrastructure, not a reinvention (Phase 7 R23). The agent never computes, adjusts or infers a score. `design.md` §9. |
| O16 | The agent's default LLM provider stays the **self-hosted** one (Phase 6 H45); the prototype's "never send real patient data to an online AI service" rule is adopted as a phase non-goal | Accepted | The two rules point the same way; adopting both costs nothing. Development data is MEPS public files and Synthea only. |
| O17 | Model artifacts are **never committed**. Each artifact directory carries a SHA-256 manifest; the service verifies it before deserialising and refuses unknown artifacts. CI trains a throwaway model on a small committed synthetic fixture; tests that need the MEPS cache **self-skip** when it's absent | Accepted | `joblib`/`pickle` loading executes code, so integrity is checked first. Self-skip mirrors `provider-registry-service`'s DB-backed tests. MEPS downloads (~40 MB) stay out of required CI. `design.md` §8. |
| O18 | The **comparison model** (logistic regression on age + any prior stay) is persisted in the same artifact as the main model | Accepted | The prototype's plan requires both scores in every response (FR-S2) but its training step saves only the gradient-boosting model (`design.md` §11, defect 2). |
| O19 | Phase 8's own documents follow **this repo's house style** (em dashes and status emoji allowed), not the prototype documents' "no em dashes, no emojis" rule | Accepted | Consistency across `docs/phase*/`. |
| O20 | Risk results are **returned, not persisted** to `fhir-service` this phase | Accepted | Same as `triage-service`'s `RiskAssessment` today. Persistence (and who may write clinical risk into the record) is a Phase 8b question alongside batch scoring. |

## Accepted with a validation step

| ID | Decision | Status | Rationale / where it lives |
|---|---|---|---|
| O21 | The FHIR → canonical-table mapping (`design.md` §7) — encounter class, prescription fills, cost, coverage — is a **sketch** until checked against real Synthea v4.0.0 FHIR output | Accepted, unvalidated | Synthea's FHIR export folds CSV classes together (e.g. office vs. hospital outpatient may both arrive as `AMB`), and fill counts may not be present as such. M6 confirms each rule live and records what it found, same posture as Phase 7 R11. |
| O22 | Prediction **outcome coding** uses SNOMED CT `32485007` "Hospital admission (procedure)", window as `whenPeriod` | Accepted, unvalidated | Code to be checked against the terminology server/browser in M7 before it ships; a wrong code is cheap to fix before any consumer exists. |

## Open (deliberate non-decisions)

| ID | Question | Status | Notes |
|---|---|---|---|
| O23 | Does AHRQ permit commercial use of models trained on MEPS public-use files? | Open — blocks commercialisation, not the build | Carried over from the prototype's plan (`prototype-baseline.md` §2). A legal question for the repo owner; no milestone depends on the answer. |
| O24 | `qualitativeRisk` (high/moderate/low) on the `RiskAssessment` | Deferred, not resolved | Needs clinically signed-off thresholds; until then only `probabilityDecimal` + percentile ship. Inventing cut-points would be clinical logic nobody has reviewed. |
| O25 | Keep, drop, or rank-transform the non-portable features (`totexpy1`, `rxtoty1`, `hhtotdy1`) | Open — decided in M11 | Prototype evidence: dropping all three changed MEPS AUROC 0.766 → 0.768 (`prototype-baseline.md` §6.4). MEPS money is payments; FHIR/claims carry charges. |
| O26 | Primary customer input — FHIR from an EHR, claims, or both | Open | Carried over from the prototype's plan. FHIR is built this phase (O8); a claims-file adapter is deferred (`prd.md` §8). |
| O27 | Who signs off on clinical code lists (M13) | Open | Carried over from the prototype's plan. M13 can build the mechanism; the lists ship as "unreviewed" until someone owns them. |

## Second pass — experimentation track

Added after the repo owner asked for a dedicated, revisitable way to explore models and decide
which kinds of prediction are worth offering, with tools later engineers can pick up at any
time. Critiqued before writing (see `prd.md` §12): the request was sound, but a milestone that
"reopens" breaks how this repo tracks milestones, and open-ended exploration against a fixed
test set erodes the trustworthiness of every number it produces. The decisions below address
both. Scope confirmed by the repo owner: package name `outcome-prediction-lab`; the
exploration covers *what* to predict and *in what form*.

| ID | Decision | Status | Rationale / where it lives |
|---|---|---|---|
| O28 | Exploration is a **dedicated research track**: milestone M3 builds the tooling **once** and completes; every later exploration — by anyone, at any time — runs as a numbered **round** under [`experimentation-protocol.md`](./experimentation-protocol.md). Milestones are never reopened | Accepted, load-bearing | Keeps milestone status meaningful (a milestone is a one-time deliverable in every phase) while making research permanently resumable. Precedent for a standing document beside milestones: `phase6/telemetry-schema.md`. M10 and M11 are the protocol's first two rounds, not one-off code. |
| O29 | The tooling is its **own top-level package, `outcome-prediction-lab/`** — named by the repo owner. It **imports** `outcome-prediction-service`'s dataset, model and contract code; the service never imports the lab | Accepted | Research-only dependencies (experiment tracking, notebook tooling) stay out of the scoring service's runtime image. One implementation of the dataset build and training, not a research fork that drifts from production. |
| O30 | Experiment tracking and the model registry use **MLflow, self-hosted, with a local file/SQLite backend**, gitignored, version pinned | Accepted | Industry-standard, Apache 2.0, runs entirely on the developer's machine. **DVC** rejected: its strength (git-native data versioning) isn't needed — MEPS files are checksummed downloads — and its run comparison is weaker. **Hosted trackers** (e.g. Weights & Biases) rejected: they send run data off the machine. Licence recorded in `NOTICE` (O13). |
| O31 | The **durable record of a round is committed**: `outcome-prediction-lab/rounds/NNN-<slug>/` holds the round's configs, report, summary metrics and scorecard. The MLflow store is a local working cache, not the record | Accepted | A gitignored tracking store dies with the workspace; posterity resumes from committed configs that re-run reproducibly (fixed seeds, recorded data checksums, code commit). |
| O32 | **Holdout discipline.** Exploration evaluates only by panel-grouped cross-validation within training panels 21–25. Test panels 26–27 are opened only to *confirm* a candidate chosen beforehand, and every opening is appended to a committed **holdout ledger**; the lab's CLI refuses a test-panel evaluation without a ledger entry. When AHRQ releases a newer two-year panel, it becomes the fresh confirmation set | Accepted, load-bearing | Repeated looks at one test set slowly tune everything to it — the main way an open-ended research track makes its own numbers untrustworthy. The ledger makes the number of looks visible, and the CLI makes the rule hard to skip. |
| O33 | **Promotion path:** experiment → *candidate* (scorecard + model card) → *decision* (a new `decisions.md` entry plus a new contract/target version) → *served* (M12 and later). `outcome-prediction-service` loads only artifacts that carry a promotion record | Accepted, load-bearing | Exploration can never change production by accident. Extends O17's integrity check from "is this artifact intact?" to "was this artifact approved?". |
| O34 | The prediction space explored is **outcome × form**. Outcomes: the year-2 outcomes MEPS actually labels — candidates include any inpatient stay, unplanned stay, ED visits, hospital nights and high cost, each confirmed against the files before use (`prototype-baseline.md` §3). Forms: probability of an event, expected count, cost estimate, and ordinal tiers where they fall out naturally | Accepted | Repo owner chose the broader scope. Bounded by what MEPS labels: an outcome MEPS can't label can't be trained here. |
| O35 | **FHIR representability is a gate for serving, not for exploring.** `RiskAssessment` (O3) carries probabilities natively; a count or cost form may be explored freely, but serving one requires a new decision revisiting O3 (an extension, a different resource, or re-expressing it as the probability of crossing a threshold) | Accepted | Resolves the tension between O3 and O34 explicitly instead of discovering it at promotion time. |
| O36 | Every candidate is judged on a **target scorecard** with ML *and* non-ML criteria: cross-validated discrimination and calibration; base rate; **measurability in FHIR/claims data** (without it, no customer validation or recalibration is possible); actionability for care management; lead time; subgroup fairness; FHIR representability (O35); regulatory posture. Non-ML criteria are scored by a person, with written rationale | Accepted | The best-scoring model can still be the wrong product. The scorecard turns "which predictions are advisable" into a recorded judgement rather than a metric race. |
| O37 | **Uplift / impactability** (who would benefit from outreach) is **out of reach** with MEPS — it has no intervention data — and every scorecard says so explicitly | Accepted | It is what care managers most want; leaving it unsaid would imply the lab covers it. |
| O38 | Notebooks are allowed for exploration but committed **only with outputs stripped** (checked in CI). Only scripted, config-driven runs count as evidence in a round report | Accepted | Notebooks with outputs are hard to review and can carry data into git; config-driven runs are what makes a round re-runnable. |
| O39 | Every candidate and every promoted model ships a **model card** generated from tracked metadata (intended use, training data, metrics by subgroup, limitations, the O37 gap) | Accepted | The standard way to state what a model is for and where it fails; also what a customer's reviewer or counsel (the FDA CDS question) will ask for. |
| O40 | Which outcome(s) and form(s) to promote first | Open — decided at the end of M10, by scorecard | Includes the earlier any-stay vs unplanned-stay question. |

## Data provenance and preservation

Added after the repo owner asked what the industry practice is for keeping data that the code
doesn't store — given that a public source can go down, move, or change. Code in git; data in
versioned object storage under your own control; small pointers to the data in git. The repo
owner chose to implement all of it now, with private bucket(s) and without DVC.

| ID | Decision | Status | Rationale / where it lives |
|---|---|---|---|
| O41 | **Data is pinned in git and preserved outside it.** A committed manifest, `outcome-prediction-service/meps-manifest.json`, records the URL and SHA-256 of every original MEPS zip, extracted `.dta`, documentation page and codebook. The originals are mirrored, write-once and content-addressed (`meps/sha256/<sha>/<name>`), to **private** GCS bucket(s) with public access prevention enforced and a retention policy; the bucket's Terraform is `outcome-prediction-service/infra/`. `download.fetch` tries the local archive, then AHRQ, then each mirror in `OUTCOME_PREDICTION_MEPS_MIRRORS`, accepting only bytes that match the manifest. **DVC not adopted**, per the repo owner — the manifest plus mirrors cover what it would add here | Accepted — real bucket **deferred, not dropped** (its Terraform is ready to apply; this repo provisions no GCP credentials). A local GCS emulator stands in for testing (O43); the repo owner keeps a `file://` copy at an off-workspace location | Before this, nothing in git pinned the data: `checksums.json` lived in the gitignored cache. AHRQ stays the primary source, so the mirror is a backstop, not a redistribution. Private, not a public archive (Zenodo etc.), because redistribution rights are part of the open O23 question. Retention policy instead of object versioning: under retention an object can't be overwritten or deleted at all, which is stronger. `design.md` §13. |
| O42 | **A changed upstream file is rejected, not adopted.** If AHRQ republishes different bytes, `fetch` refuses them and uses a mirror's original; adopting the new release is a deliberate, reviewed change (`manifest snapshot --accept-change`, a git diff of the manifest), followed by re-running the reproduction tests | Accepted | Statistical agencies do re-release corrected files. Silently training on them would move every number with no trace in the repo. |
| O43 | Until the real bucket is wanted, a **local GCS emulator** (`fsouza/fake-gcs-server:1.56.1`, compose service `gcs-emulator`, profile `phase8`) stands in for it, reached by the real `google-cloud-storage` client via `STORAGE_EMULATOR_HOST`. Tests reach it through the `gcs_emulator` fixture, which reuses a running emulator or starts this image itself (O44), so the `gs://` path is tested on every PR. It is a **test stand-in, not a backup** — its storage lives on this workspace's Docker host — and it doesn't enforce retention, IAM or public-access prevention, which exist only in the unapplied Terraform | Accepted | Repo owner's choice to skip creating a GCP bucket for now. Verified before relying on it: the emulator honours the write-once generation precondition (a second create returns 412), and the full real-data path (push 21 originals, verify, AHRQ-down restore of all 7 panels, byte-identical rebuild) runs through it. Preservation is covered separately by the repo owner's off-workspace `file://` copy. |
| O44 | **Tests that need data populate it; they don't skip.** Session fixtures (`tests/conftest.py`) give every test that asks for them complete, verified data — `meps_cache` fetches any missing panel (local archive → AHRQ → mirrors, checked against the manifest), and sets aside and re-fetches any cached file that doesn't match it; `gcs_emulator` reuses a reachable emulator or starts a container for the session; `meps_emulator_bucket` creates the emulator bucket if absent and tops up any missing data zip. This holds for one test, a file, or the whole suite, run by hand or by CI. A fixture that can't obtain its data **fails** the test; skipping happens only when `OUTCOME_PREDICTION_TESTS_OFFLINE=1` is set deliberately. CI caches the original zips (keyed on the manifest) | Accepted; **supersedes O17's self-skip clause** | Repo owner's requirement: before approving, they need to know the tests actually pass — and a skipped test proves nothing. A green CI run now means every Phase 8 test, including the exact-reproduction checks, executed. The cache keeps CI independent of AHRQ after its first run. |


## Third pass — M3, round 001 (iteration 1)

The repo owner asked for M3 to be a multi-prompt, learning-oriented milestone covering *what* to
predict and *how*, with explicit concepts to try (TF-IDF, autoencoders, random forest with
per-patient explanations, missing values, feature importance). Results:
`outcome-prediction-lab/rounds/001-what-and-how/report.md`.

| ID | Decision | Status | Rationale / where it lives |
|---|---|---|---|
| O45 | **M10 and M11 are folded into M3.** M3 builds the lab *while* running real rounds, iteratively; it ends when the repo owner decides no further iteration is needed. M10/M11 keep their numbers as markers but carry no separate work | Accepted | Repo owner's choice ("we can always change milestones again"). Building tools in the course of real exploration is better learning than building them first in the abstract. |
| O46 | MLflow tracking uses a **local SQLite store** (`outcome-prediction-lab/mlflow.db`, gitignored) and is an **optional** `tracking` extra (`mlflow==3.17.1`), best-effort in round scripts | Accepted; **refines O30** | MLflow 3 retired the file store O30 assumed; `mlflow-skinny` can't use SQLite. Heavy dependencies stay optional because a round's committed `metrics.json` is the record (O31). |
| O47 | **Admission labels count stays that *began* in year 2**; the recommended headline label is **non-obstetric admission** (excludes `RSNINHOS` 4–6) | Accepted for the lab; promotion still via O40 | The prototype's label counts year-2 discharges and includes childbirth; round 001 showed most code-feature gain on it is pregnancy codes predicting deliveries. Non-obstetric admission scores higher (test AUROC 0.795) on a label that means what a care manager means. |
| O48 | **Death and loss of insurance are learning-only targets**: never promoted from MEPS-only work | Accepted | Kept to teach rare-event evaluation. Any real use needs clinical / fairness governance, not just a model. |


## Round 002 — text, tooling and narratives

| ID | Decision | Status | Rationale / where it lives |
|---|---|---|---|
| O49 | **Codes are named from the pinned sources only:** ICD-10 and CCSR labels from AHRQ's MEPS documentation pages, Multum drug classes from AHRQ's therapeutic-class table, gaps from the CDC/NCHS ICD-10-CM FY2026 release (public domain, pinned by SHA-256). Unnamed CCSR groups are described by body system; AHRQ-truncated labels end in "…"; one documented override (U07 = COVID-19) | Accepted | No extra licences: HCUP's CCSR file was not used because its download terms aren't stated clearly. `outcome_prediction_lab/vocabulary.py`. |
| O50 | **Patient narratives are templated and self-explanatory:** full names instead of codes; comparisons with OBSERVED next-year rates among comparable adults in the training panels; the marginal-vs-conditional case named explicitly; race/ethnicity never narrated per patient; a patient's actual outcome never shown | Accepted | Repo owner's requirement (no codes to look up; compare with meaningful aggregates). Showing outcomes would make an explanation a test-panel look; narrating race per patient invites misuse — its influence belongs in aggregate fairness reporting. `narrate.py`. |
| O51 | **Drug classes use the most specific Multum level available** (TC1S1_1 > TC1S1 > TC1). Round 001's level-3-only behaviour stays available, pinned in its script, so its numbers remain reproducible | Accepted | Level 3 is "inapplicable" for classes without a third level: round 001 gave 34% of fills no class. Measured effect on prediction: nil. |


## Round 003 — the portable feature contract

| ID | Decision | Status | Rationale / where it lives |
|---|---|---|---|
| O52 | **Production models are trained on the portable contract `meps-portable-v2`** (`outcome_prediction/contract.py`): every input tagged with its FHIR source and a reliability tier (always / usually / rarely / claims-only / not portable). Two tiers of use: records-only customers (`portable-v2`) and customers who also send claims (`portable-v2+claims`). MEPS-only CCSR groups and Multum drug classes are replaced by ICD-10-only code tokens, ICD-10 chapter counts and distinct-medicine counts | Accepted | A model must never depend on an input production can't fill. Cost measured in round 003 (test panels): non-obstetric admission 0.795 → **0.795**, any ER visit 0.739 → **0.740**, high cost 0.850 → **0.834** (with claims). `outcome-prediction-lab/rounds/003-portable-contract/report.md`. |
| O53 | **Always-missing inputs are dropped and the model retrained — never imputed; sometimes-missing inputs stay, with missingness augmentation** (a pipeline step that hides them for half of training rows, never at scoring). Income is the sometimes-missing case: models are scored with it blanked, as production will be | Accepted | An imputed value is a function of the other inputs, so it adds no information — only silent miscalibration. Augmentation keeps calibration with income blanked (mean prediction 0.0741 vs rate 0.0741, CV). |
| O54 | **A target is only offered to a customer who can observe its outcome**: admissions and ER visits from records (within the system) or claims; high cost **from claims only** — its production model is the claims-tier one, and the model card states it | Accepted | Without the outcome, a customer can neither validate nor recalibrate the model (scorecard criterion "measurable in customer data", O36). `contract.LABEL_OBSERVABILITY`. |


## Focus

| ID | Decision | Status | Rationale / where it lives |
|---|---|---|---|
| O55 | **Phase 8 focuses on four predictions only, unless the repo owner explicitly says otherwise:** (1) admission through the emergency room, (2) hospital stay not related to pregnancy or childbirth, (3) any emergency-room visit, (4) being a high-cost patient. All other targets are **parked, not deleted** | Accepted (repo owner, 2026-10-18); **narrows O40** to a choice among these four | All four are event probabilities (native `RiskAssessment`, O3); three are validatable from records, high cost from claims (O54). The decision path and every parked item's location: [`prediction-targets.md`](./prediction-targets.md). |

## Round 004 — readiness of the four focus predictions

| ID | Decision | Status | Rationale / where it lives |
|---|---|---|---|
| O56 | **Admission through the ER's production model is `er-admit-v2`** — `meps-portable-v2`, records-only tier, income learned-missing and blanked at scoring. The claims tier adds nothing (CV 0.7798 vs 0.7797) | Accepted | Test AUROC **0.785** (research model 0.788; baseline 0.754); calibrated (0.051 vs 0.049). ER-origin admissions are observable in records or claims (O54). All four focus predictions now have a production-contract model. `outcome-prediction-lab/rounds/004-focus-four-readiness/report.md` §2. |
| O57 | **Every focus production model ships with a subgroup fairness report** (race/ethnicity, insurance, sex, age band: AUROC with CI, calibration ratio, flag share, cases caught, precision) on its model card; it is a logged test-panel look (`<config>:fairness`). Known findings travel with the model: **uninsured adults are almost never flagged** (labels measure use, not need), calibration bends toward the average by age and insurance, and Black adults' AUROC for non-obstetric stay is lower (0.745 vs 0.787) | Accepted (FR-E6) | `outcome-prediction-lab fairness`; reports in each round's `fairness/`. Phase 8b repeats the check per customer, per group. Race/ethnicity stays out of the inputs and out of per-patient narratives (O50). |
| O58 | **No separate 65+ model** (FR-M6): the general production models are used for adults 65+ | Accepted | Pre-registered rule (specialist must beat the general model's CV AUROC on 65+ by ≥ +0.005) failed for all four, by 0.020–0.038. 65+ performance and calibration are reported on every model card. Report §4. |

## Closing M3

| ID | Decision | Status | Rationale / where it lives |
|---|---|---|---|
| O59 | **The first promotion is the non-obstetric hospital stay (`admit_nonobstetric_y2`), as a probability, via `003-portable-contract/nonobstetric-v2`** on `meps-portable-v2` (records-only tier). M12 serves it beside `meps25-v1`. The person-scored scorecard criteria for all four focus models are recorded (`rounds/*/criteria/*.json`), drafted by Claude and adopted by the repo owner | Accepted (repo owner, 2026-10-18); **resolves O40** | Highest-quality label a records-only customer can validate (test AUROC 0.795, calibrated; top 10% hold 38% of stays); classic care-management signal; scorecard: measurable in records or claims, actionable High, native `RiskAssessment` (O3). Its known fairness findings (O57) travel with it. The other three stay focus predictions for later promotions. |
| O60 | **M3 is closed**: the workbench is built and rounds 000–004 are complete. The lab stays available; new rounds open on demand under the protocol (O45) | Accepted (repo owner, 2026-10-18) | Every M3 deliverable is met: round 000 reproduces M2 bit for bit; CLI guards are tested; the four focus models have model cards, fairness reports, 65+ checks and full scorecards; O40 decided (O59). |


## M4 — Synthea harness and scoring mode

| ID | Decision | Status | Rationale / where it lives |
|---|---|---|---|
| O61 | **Phase 8 pins Synthea v4.0.0 itself** (`etl/synthea.py`: release URL + SHA-256 `ed43c20a…`, verified before use) and generates the prototype's population (seed 42, 3,000, ages 18–90, end 2024-12-31, Arizona) **CSV-only**. The FHIR half (O11) is regenerated from the same seed when M6 needs it | Accepted | O11 called v4.0.0 "the repo's pinned" release, but `data/scripts/generate.sh` pins 3.3.0 for earlier phases and stays untouched. Same seed → same patients with or without the FHIR export (checked on a 20-patient run), and full-history FHIR for 3,700 people would be ~26 GB. |
| O62 | **Scoring mode is the training rule** (`as_of_view` + `contract_rows`): training mode = scoring mode as of 31 December of year 1, plus the label. Values final only when a record ends are unknown while it runs: a running prescription's fills are estimated from the same person's last **ended** record of the same drug (else one a month) × the per-fill price; a running stay counts nights so far and no cost; a death after `as_of` is unknown | Accepted | Fixes `design.md` §11 defects 1, 3, 4. The leakage test (records after `as_of` change nothing) passes, and fails on the reproduced prototype code. Synthea fill rates vary (median 1.09 a month, many 90-day supplies), so a flat monthly rule overcounts. M6 decides the FHIR equivalent (`MedicationDispense` or `dispenseRequest`). |

## Supersession notes

- **O44 supersedes O17's last clause** ("tests that need the MEPS cache self-skip when it's
  absent; MEPS downloads stay out of required CI"). The rest of O17 — artifacts never committed,
  manifest verified before deserialisation, a throwaway model trained on a synthetic fixture for
  service tests — stands. O17's row is left as written, for the record.

- **O52 and O53 resolve O25**: last-year spending is not portable and is dropped from every
  production model (not imputed); prescription fills and home-health days are claims-only inputs,
  used only in the `portable-v2+claims` tier. O25's row is left as written, for the record.
- **O55 narrows O40**: the first promotion is chosen among the four focus predictions (O40 stays
  open for that choice; the recommendation is non-obstetric admission). O40's row is left as written.
- **O59 resolves O40**: the first promotion is non-obstetric hospital stay (`nonobstetric-v2`). O40's
  row is left as written.
- **O61 corrects O11's wording**: v4.0.0 is pinned by Phase 8 (`etl/synthea.py`), not by the repo's
  `generate.sh` (3.3.0); and the M4 run is CSV-only, with FHIR regenerated from the same seed for M6.
  O11's row is left as written.
- **O46 refines O30**: same tool (MLflow), different store (SQLite instead of the retired file
  store), now an optional extra.

Future entries that revise one of the above will say so explicitly here, same convention as
Phase 4 (`E`-series), Phase 6 (`H`-series) and Phase 7 (`R`-series).
