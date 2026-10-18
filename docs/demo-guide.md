# Demo Guide

How to experience the system yourself, and how to show it to four very different audiences
without boring or losing any of them.

The same stack tells four different stories. The mistake is telling the architect's story to the
clinician. Pick the audience first, then run only what serves them.

| Audience | The question they're really asking | Jump to |
|---|---|---|
| **Clinician** | "Will this help me keep a patient safe?" | [§2](#2-the-clinician-8-minutes) |
| **Insurer / payer** | "Can this decide claims correctly, and prove it?" | [§3](#3-the-insurer--payer-12-minutes) |
| **Architect / developer** | "Is this real engineering or a demo?" | [§4](#4-the-architect--developer-15-minutes) |
| **Layperson** | "What does this actually do?" | [§5](#5-the-layperson-5-minutes) |
| **Any audience — provider search** | "Can it find a real doctor who takes this patient?" | [§5a](#5a-provider-search--referral-phase-3-6-minutes) |
| **Any audience — hospitalization risk** | "Who is likely to end up in hospital, and why does it think so?" | [§5b](#5b-hospitalization-risk-phase-8-8-minutes) |

---

## 1. Before any demo

**Read this or your demo will fail in front of people.** The FHIR server is in-memory
(`jdbc:h2:mem:hapi`). It boots **empty every time**, and adjudication **fails closed** — a
member with no clinical record pends rather than approving. If you skip seeding, every claim
pends on `clinical-safety-unavailable` and your "approved" path won't approve.

The seeder handles this. Just always run it.

```bash
# 1. Bring up the full stack (Phase 1 services start automatically as dependencies)
docker compose --profile phase2 up --build -d

# 2. Seed fixtures AND drive all six golden paths (~30s)
python3 data/scripts/seed_claims_demo.py
```

Expected output — the whole Phase 2 story in one screen:

```
seeded patients: Patient/member-000000001 (no allergies), Patient/member-000000009 (…)
• APPROVED  — on-formulary generic
    → outcome=APPROVED  reasons=[—]  decision=DEC-DEMO-APPROVED | total $241.50
• PENDED    — specialty drug, PA required
    → outcome=PENDED  reasons=[prior-auth-required]  decision=DEC-DEMO-PENDED | total $952.00
• ROUTED    — quantity over plan limit
    → outcome=ROUTED_FOR_REVIEW  reasons=[quantity-limit-exceeded]  decision=DEC-DEMO-ROUTED | total $1081.50
• DENIED    — coverage inactive on date of service
    → outcome=DENIED  reasons=[coverage-inactive]  decision=DEC-DEMO-INACTIVE
• DENIED    — non-formulary + quantity (multi-reason)
    → outcome=DENIED  reasons=[non-formulary]  decision=DEC-DEMO-MULTI
• DENIED    — clinical safety (penicillin allergy + amoxicillin)
    → outcome=DENIED  reasons=[clinical-safety-high]  decision=DEC-DEMO-SAFETY
```

**Checklist**

- `docker compose ps` — `fhir`, `triage`, `rxclaim-emulator`, `claims-service` all up.
- Seeder printed **both** patients.
- All six paths printed their expected outcome (the label states it; the arrow shows the truth).
- For the Phase 1 clinician demo only: `ANTHROPIC_API_KEY` (or `CLAUDE_API_KEY`) set in `.env`.
  Phase 2 explanations run **without** a key via `--no-llm`.
- **Tear-down between rehearsals:** `docker compose restart fhir` wipes FHIR. Re-run the seeder.

Ports: FHIR `8080`, triage `8001`, claims-service `8090`, Kong proxy `8000` (`gateway` profile).

---

## 2. The clinician (8 minutes)

**They care about:** the patient in front of them, not your architecture. Does it catch what a
tired human at 2am might miss, and does it explain itself well enough to trust?

**Story arc:** *plain language in → the system reads the chart → it catches a conflict a busy
human could miss → and it never hides behind "the computer says no".*

**Run — Phase 1, natural language:**

```bash
docker compose up --build -d fhir triage
python3 data/scripts/seed_demo.py
docker compose run --rm mcp-agent --query "Check refill risk for Kristle Mraz"
```

```
🚨 HIGH RISK — Do not dispense without physician review
   Patient: Kristle Mraz  |  RiskAssessment/...
   Reason: Penicillin-class allergy conflicts with Amoxicillin prescription.
```

**Then — the same clinical judgement inside a payer decision:**

```bash
python3 data/scripts/seed_claims_demo.py     # watch the last line
```

> "That last claim is amoxicillin for a patient with a penicillin allergy on file. The claim was
> **denied on clinical-safety grounds** — not cost, not paperwork. Same rule engine you just saw
> in the clinical workflow, reused inside the payer's decision."

**What to say:**

- "The AI doesn't decide anything clinical. It reads the chart and explains. A **deterministic
  rule engine** makes the call — the same input always gives the same answer."
- "Every assessment cites its evidence — the specific medication and allergy records it used.
  You can audit it, not just believe it."
- "If the safety check can't run — the service is down, the chart won't load — the claim
  **pends for a pharmacist**. It does not quietly approve. We treat 'I don't know' as different
  from 'it's fine'."

That last point lands harder than anything else with clinicians. It's the difference between a
tool that helps and a tool that hurts you at 2am.

**Do not:** show Java, talk about strangler patterns, or open a FHIR bundle. If asked how it
works: *"it reads the same records your EHR does, using a standard called FHIR."*

**They will ask:**

- *"What if it's wrong?"* — It's a **gate, not a decision**. High risk routes to a human. The
  agent can't approve anything on its own; it has no authority in the system.
- *"Does it learn from me?"* — Not today. The rules are explicit and reviewable. That's a
  deliberate trade: an explicit rule can be audited by a pharmacist; a learned weight can't.
- *"What conflicts does it catch?"* — Drug-allergy today, including class-level (penicillin
  family → amoxicillin). Drug-drug interactions are on the roadmap.

---

## 3. The insurer / payer (12 minutes)

**They care about:** correctness, auditability, appeals, and not rewriting a system that works
and processes real money.

**Story arc:** *your legacy core keeps doing what it's good at → modern rules make the decision
explainable → every decision is auditable and reproducible → nothing had to be rewritten.*

**Run:**

```bash
python3 data/scripts/seed_claims_demo.py
```

Walk the six outcomes as a **decision table**, not a log:

| Claim | Outcome | Why it matters commercially |
|---|---|---|
| on-formulary generic | APPROVED $241.50 | Pricing came from the **legacy core**, untouched |
| specialty drug | PENDED | Prior-auth caught **before** spend |
| quantity over limit | ROUTED | To a human reviewer, with the reason attached |
| coverage inactive | DENIED | Eligibility outranks everything |
| non-formulary + quantity | DENIED | **Multi-reason** — both recorded, not just the first |
| penicillin allergy | DENIED | **Clinical safety**, reusing the existing engine |

**The four points that matter to a payer:**

1. **The legacy core still prices the claim.** `$241.50` came out of the simulated RxClaim/IBM i
   core, in fixed-width DDS records. *"We wrapped it. We didn't rewrite it. Your adjudication
   logic and your actuarial history are intact."* This is the **strangler pattern** — say it
   once, in that plain form.

2. **Multi-reason decisions.** Most legacy cores stop at the first reject code. This one
   accumulates every finding, then applies precedence:

   > "The member gets *all* the reasons at once, not one per appeal cycle. That's fewer appeals,
   > fewer calls, and a member who isn't told 'non-formulary' this week and 'quantity limit'
   > next week."

3. **Deterministic and idempotent.** Same claim, same answer, forever — and a retried
   submission never double-writes:

   ```bash
   pytest e2e/ -k idempotent -q     # resubmit → identical decision, one artefact set
   ```

   > "Pharmacy networks retry. Retries must not create duplicate liability."

4. **Auditable by construction.** Every decision persists a linked FHIR graph — `Claim` →
   `ClaimResponse` → `Task` (if routed) → `Provenance` → `RiskAssessment` — all carrying the
   decision id. *"When a regulator or an appeal asks 'why', the answer is a record, not a
   reconstruction."*

**Then, the explanation layer:**

```bash
docker compose --profile phase2 run --rm claims-agent --no-llm --claim '{"claimId":"DEMO-X","memberId":"000000009","planId":"COM-SILVER","rxcui":"723","ndc":"0093-8675","drugName":"amoxicillin","quantity":30,"daysSupply":30,"dateOfService":"2026-06-01","prescriberNpi":"1234567890","coverageEffective":"2026-01-01","coverageTermination":"2026-12-31","priorAuthOnFile":false,"stepTherapyMet":false}'
```

```
🛑 DENIED
   Decision: DEC-DEMO-X
────────────────────────────────────────────────────────────────
Claim denied. Reason(s): High clinical-safety risk (e.g., drug-allergy conflict).
Decision id: DEC-DEMO-X.
```

> "The AI **explains** the decision. It didn't make it — and `--no-llm` proves it: no model, same
> decision, still explained. The AI is never in the decision path, which is exactly what you want
> when a regulator asks who decided."

**They will ask:**

- *"Is the formulary data real?"* — Grounded in **public disclosure data**: CMS Part D for
  Medicare and ACA-mandated QHP machine-readable formularies for commercial. Curated subsets,
  real structure (tier / PA / step therapy / quantity limit). Sources in `data/reference/`.
- *"Medicare or commercial?"* — Both. The engine is payer-agnostic; plan type is configuration.
- *"What happens when a service is down?"* — Clinical safety **pends**, never auto-approves.
  Persistence is atomic, so a failed write leaves nothing half-recorded and the retry is safe.
- *"How fast could this run for real?"* — Honest answer: unmeasured. No load testing yet —
  it's on the roadmap, and this is a prototype slice, not a production PBM.

---

## 4. The architect / developer (15 minutes)

**They care about:** whether this is engineering or theatre. They will probe for the gap between
the diagram and the repo.

**Story arc:** *the patterns are real and named → local and cloud are the same config → the
environment and even the AI conversations are reproducible → and the project is honest about
what's missing.*

**Open with the request flow, then show it in the tree:**

```
claims-agent ──▶ claims-service ──┬──▶ rxclaim-emulator  (legacy pricing/SOR, internal only)
  (explains)      (façade + ACL   ├──▶ triage-service    (clinical safety, REUSED from Phase 1)
                   + rules engine) └──▶ fhir-service      (Claim/ClaimResponse/Task/Provenance)
```

**The five things worth their time:**

1. **The patterns are load-bearing, not decorative.**
   - *Strangler fig* — `rxclaim-emulator` is a real Spring Boot service with DDS fixed-width
     records and an RPG/CL-flavoured `ADJRXCLM`. It has **no published port**: internal-only,
     mirroring `ingress=internal`. Everything goes through the façade.
   - *Anti-corruption layer* — `acl/LegacyAdapter` is the **only** place byte offsets exist. Show
     `LegacyAdapterTest`, then show `rules/` and point out it has no idea legacy exists.
   - *Repository seam (C3)* — `PayerKb` is an interface; `FilePayerKb` reads files today,
     Postgres later, without the rules engine noticing.

2. **Local ↔ cloud parity is a config fact, not a promise.** The **same DB-less `kong.yml`**
   runs locally and in cloud. Phase 1's Kong (KIC on GKE) is untouched; a documented
   gateway-strangler (S0→S1→S2) migrates it later, with rollback.

   ```bash
   docker compose --profile phase2 --profile gateway up -d   # Kong prints a generated dev key
   ```

3. **The environment is machine-independent.** A devcontainer (`.devcontainer/`) pins Java 21,
   Python, Maven, Docker-in-Docker, kubectl, Helm, Terraform. Same image locally (Docker Desktop)
   or in the cloud (Ona). `.ona/automations.yaml` scripts dependency install and credential
   setup. *"There is no 'works on my machine'. There is no my machine."*

4. **The AI conversations are version-controlled.** This is the part that surprises people. The
   repo uses **two git worktrees**:

   - `/workspaces/fhir-agent` (`main`) — application code, PRs, review.
   - `/workspaces/.ai-chat-history` (`ai-chat-history`) — the full AI conversation archive:
     `ai-chat-documentation/` with raw transcripts, rendered markdown, manifests, and export
     scripts. Never merged into `main`.

   > "Every design conversation that produced this code is committed, indexed, and reviewable —
   > and deliberately isolated from application history so it never pollutes a diff. If AI wrote
   > it, you can read *why*. The chats are provenance, not exhaust."

5. **The decision contract is normative and enforced.** Accumulate-then-resolve;
   `DENY > PEND > REVIEW > approved`; a total order `(severity, domain, ruleId)` so output is
   byte-identical across runs and machines. No wall-clock, no map-iteration order. Tests pin it
   (`RulesEngineTest.deterministicOrder_byDomain_whenTwoDenies`).

**Then earn their trust — volunteer the weaknesses.** They're hunting for what you're hiding;
hand it over:

- **CI doesn't run e2e.** That's how a fail-closed regression reached `main`. Documented as the
  top gap in [`testing-guide.md` §4](./testing-guide.md#4-what-is-not-tested--known-gaps).
- **No load testing.** Scale is designed and documented, not measured.
- **No non-regression snapshots yet** (R19 requires them).
- **The cloud deploy is further away than the plan implies.** Per-service Cloud Run stubs exist
  for the two Java services, but there is **no root Terraform module**, no `deploy-phase2.sh`,
  and nothing has ever been applied. Phase 2b is real authoring work, not one command. (The plan
  says so explicitly now — [§6 cloud-delivery gap](./phase2/plan.md#6-workstreams--milestones).)

Then show [`testing-guide.md` §6](./testing-guide.md#6-case-study-how-a-dead-safety-check-passed-every-test)
— the dead-safety-check case study. Nothing establishes engineering credibility faster than a
precise, unflattering post-mortem of your own bug.

**They will ask:**

- *"Why Java and Python?"* — Reuse, not preference. Triage already existed in Python and works;
  rewriting it would break Phase 1 independence for no gain. The payer-facing façade is Java
  because that's the ecosystem it must live in.
- *"Why not merge the two agents?"* — Coupling Phase 1 to Phase 2 breaks R9. They share
  plumbing, never clinical logic.
- *"Is Phase 1 really independent?"* — `docker compose config --services` prints exactly
  `fhir mcp-agent triage`. CI asserts that string on every PR.
- *"What's the hardest bug you hit?"* — A Java client defaulting to HTTP/2 attempting an h2c
  upgrade against HTTP/1.1-only uvicorn: the POST body silently vanished and FastAPI answered
  `422 body required`. Mocks couldn't see it; a stub-server contract test can.

---

## 5. The layperson (5 minutes)

**They care about:** whether this is useful and whether it's the scary kind of AI. Use zero
jargon. Not "FHIR", not "adjudication", not "agent".

**Open with a shared experience:**

> "You've had a prescription rejected at a pharmacy counter and been told 'insurance won't cover
> it' — with no explanation, and nobody there could tell you why. This is about that moment."

**Show one thing:**

```bash
python3 data/scripts/seed_claims_demo.py
```

Point at exactly two lines:

> "Six prescriptions went to the insurance system. This one was **approved** — $241.50, covered.
> This one was **refused**, and look at the reason: the patient is **allergic to penicillin**, and
> this drug is in the penicillin family. It caught that in about a second, by reading the
> patient's chart."

**Then the part that matters:**

```bash
docker compose --profile phase2 run --rm claims-agent --no-llm --claim '…'
```

> "And it explains itself in plain English. That's the AI's whole job here: **explaining, not
> deciding.**"

**The three ideas to leave them with:**

1. **The AI is the translator, not the judge.** Fixed rules — written by people, reviewable by
   people — make every decision. The AI reads them and explains them in a way a human
   understands. Run it with the AI switched off (`--no-llm`) and the decisions are identical.
   That's not a slogan; it's a flag.

2. **"I don't know" is not "yes".** If the safety check can't run, the prescription goes to a
   **pharmacist**, not through. Most software treats a broken check as no problem found. This one
   refuses to.

3. **Every decision leaves a receipt.** Why it was refused, which rule, what evidence, what
   date. If you appeal, there's a record — not someone's reconstruction months later.

**Good analogy if they want one:**

> "The insurance company's decision-making is a 40-year-old machine that works fine and handles
> real money — nobody sane rips it out. So we built a modern front desk around it. The front desk
> handles the conversation, the explanation, and the paperwork trail. The old machine still does
> the maths it's always done. Over time, the front desk takes over more, one piece at a time,
> and the old machine gets smaller."

**Do not:** show JSON, name a design pattern, or open a terminal any wider than one command.

**They will ask:**

- *"Is a robot deciding my healthcare?"* — No. Rules people wrote decide. The AI explains. And
  anything risky goes to a human.
- *"Is my data safe?"* — All data here is synthetic — invented patients. The real system treats
  every record as protected health information: key-gated access, no identifiers in logs.
- *"Could this replace my pharmacist?"* — The opposite. It's built to send more things *to* the
  pharmacist — that's what the "I don't know" rule does.

---

## 5a. Provider search & referral (Phase 3, 6 minutes)

**A separate story from §1–§5.** Phase 3 shares no service, database, or Kong route with
Phase 1/2 — it's its own opt-in `phase3` compose profile, and a plain `docker compose up` still
starts only Phase 1. Works standing alone after §1's stack, or completely on its own.

**Story arc:** *plain language in → a real MCP protocol call out → real public provider data
back, with the source it came from.*

**Setup — a separate seed step, real public data, not synthetic:**

```bash
docker compose --profile phase3 up --build -d postgres provider-registry
docker compose --profile phase3 run --rm -T provider-curation-agent --states NC --no-llm   # ~20s, real NPPES data
```

> `-T` matters here: some non-interactive environments silently swallow `docker compose run`
> output without it. If a run looks empty, `docker run -d ... && docker logs <container>` always
> shows it.

**Run — the natural-language query:**

```bash
docker compose --profile phase3 run --rm provider-search-agent \
  --query "find an endocrinologist near 27514 who's accepting new patients"
```

Expect a short ranked list of **real** UNC-area endocrinologists — real names, real NPIs, real
addresses — with `accepting_new_patients: unknown` on each (NPPES has no such field; the agent
says so rather than guessing).

**What to say, adapted to whoever's in the room:**

- **Clinician:** "It's reading the same kind of public directory data your referral coordinator
  would, but it does it in a few seconds and every result traces back to a real record — no
  invented doctors."
- **Insurer / payer:** "Sourced entirely from NPPES, the same public registry CMS itself
  publishes — not a paid directory API. Every provider fact is grounded; there's a real test
  suite that independently re-fetches every NPI an answer mentions and asserts it's genuine."
- **Architect / developer:** "This is the platform's first genuine MCP integration — a real
  hand-built server and a real client talking the actual protocol (`initialize` →
  `tools/list` → `tools/call`), not the in-process function dispatch Phase 1's agent uses. The
  client discovers the server's tools live; nothing is hardcoded."
- **Layperson:** "You describe what kind of doctor you need in plain English, and it hands back
  real doctors near you, pulled from the same public directory the government keeps."

**Volunteer the weaknesses, same discipline as §4:**

- Only NC/CA/MT are curated (12,582 real providers) — a bounded pull, not a national census.
- `accepting_new_patients` is always reported `"unknown"`, never guessed — NPPES doesn't carry
  that field.
- No live cloud deployment yet (Phase 3b) — Terraform stubs `validate` cleanly but have never
  been `apply`'d.

**They will ask:**

- *"Is this real data or made up?"* — Real. `data/scripts/provider_ingest/README.md` documents
  the exact source URLs; the groundedness eval independently verifies every NPI an agent states.
- *"Why a separate protocol server instead of just another tool function?"* — To actually learn
  and demonstrate MCP as a real integration boundary, and because it's the natural seam for a
  future non-Python or third-party client to plug into without touching agent code.
- *"Does this connect to the patient's insurance?"* — No — deliberately out of scope. This finds
  a provider; it doesn't check network coverage or benefits.

---

## 5b. Hospitalization risk (Phase 8, 8 minutes)

**A separate story, its own opt-in `phase8` compose profile.** Machine-learning models trained on
the US government's MEPS survey estimate each patient's chance of a hospital admission in the next
12 months, and return it as a standard FHIR `RiskAssessment` — with the records they used. Two are
served: the **promoted production model** (a stay *not* related to pregnancy or childbirth, built only
on what real records supply; decision O59) and the reproduced research prototype (any stay).

**Story arc:** *a patient's own records in → a probability out, with the evidence behind it → a
plain-language answer that says nothing the model didn't → proof it can't peek at the future.*

**Setup (once):** both models come from public MEPS files; the service serves only **promoted**
artifacts (a `PROMOTION.json` naming the decision), so each is promoted after it's built:

```bash
pip install -e client/clinical -e "outcome-prediction-service[api]" -e "outcome-prediction-lab[dev]" \
  -e agent-platform -e outcome-prediction-agent
python -m outcome_prediction.meps.download && python -m outcome_prediction.meps.build \
  && python -m outcome_prediction.model.train          # -> models/gbm-meps25-v1-…  (the prototype)
python -m outcome_prediction.model.promotion retrofit outcome-prediction-service/models/gbm-meps25-v1-* --decision O2
# the production model: confirmed in the lab's round 003, promoted under O59
outcome-prediction-lab promote 003-portable-contract nonobstetric-v2 --decision O59
#    -> models/gbm-meps-portable-v2-nonobstetric-v2-…  (needs the lab round's fitted model)
```

**Before each demo** — the FHIR server is in-memory, so seed it (idempotent, ~80 s first time):

```bash
docker compose --profile phase8 up --build -d fhir outcome-prediction       # scoring service on :8005
python -m outcome_prediction.etl.synthea seed --fhir http://localhost:8080/fhir
# Patient/3208   Leeanna836 Beier427   born 1939-09-08
# Patient/674    Elinor7 Kub800        born 1939-09-08  (deceased — no estimate)    … 10 patients
ollama serve & ollama pull llama3.2:1b        # or: docker run -d -p 11434:11434 ollama/ollama:0.6.5
```

The seed prints each patient's id; on a fresh server they come out the same every time.

**Beat 1 — a patient scored through the API, evidence included:**

```bash
curl -s localhost:8005/health                         # both models, each "promoted_by" its decision
curl -s -X POST localhost:8005/risk/nonobstetric-admission-12m -H 'Content-Type: application/json' \
     -d '{"patient_id": "3208", "as_of": "2024-12-31"}' | python3 -m json.tool
```

The **production model** (`meps-portable-v2`): `probabilityDecimal 0.2334`, the 93rd percentile, a
comparison model's 0.1944, the reasons *"age, comorbidity (Elixhauser score) and the number of
different diagnoses"*, and a `basis` of 18 references — her encounters, claims and the diagnoses
behind each code-derived input. The same call on `/risk/hospitalization-12m` (the prototype) gives
0.1227, the 79th percentile, *"age and coronary heart disease"*, eight references —
`curl localhost:8080/fhir/Condition/3287` is her *Ischemic heart disease (disorder)*, recorded in
2007. Scoring a patient who died (`674`) returns **422: no estimate is made**, not a number.

**Beat 2 — the same patient through the agent:**

```bash
OUTCOME_PREDICTION_URL=http://localhost:8005 outcome-prediction-agent \
  --query "What is the hospitalization risk for patient 3208 as of 2024-12-31?"
```

```
Patient/3208: estimated chance of a hospital admission not related to pregnancy or childbirth between 2024-12-31 and 2025-12-31 — 23.34%.
Percentile among the adults the model was trained on: 93.
A simpler comparison model (age and any prior hospital stay) gives 19.44%.
Inputs raising the estimate most, compared with a typical adult: age, comorbidity (Elixhauser score) and the number of different diagnoses.
Notes from the service about the inputs: household income not recorded: the model scores without it (O53); …
Model gbm-meps-portable-v2-nonobstetric-v2-e8f466f43f88 (contract meps-portable-v2). 12-month planning estimate …
[ESTIMATE]
```

The agent answers with the promoted production model (O77). Every line is a field of beat 1's
`RiskAssessment` — point at them side by side. Then try to break it:
*"Is she high risk?"* (the same numbers, plus "no thresholds have been clinically agreed"),
*"Adjust for her new diabetes"* (the same numbers, plus "can't be adjusted"), *"Rank everyone over
20%"* (`[OUT_OF_SCOPE]`, no tool called). The local 1B model sometimes answers `[NEEDS_PATIENT]` —
just ask again; that's the model failing safely, never a wrong number.

**Beat 3 — it can't see the future:** add a hospital stay *after* the as-of date, and re-score.

```bash
curl -s -X POST localhost:8080/fhir/Encounter -H 'Content-Type: application/fhir+json' -d '{
  "resourceType": "Encounter", "status": "finished", "subject": {"reference": "Patient/3208"},
  "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "IMP"},
  "period": {"start": "2025-03-01T09:00:00Z", "end": "2025-03-06T09:00:00Z"}}'
```

Re-run beat 1 — either model: **identical**, same probability, same basis. Score `"as_of":
"2025-12-31"` and the new stay appears in `basis`: the server has it; the model just isn't allowed to
look past `as_of`.

**Or run all three beats, for both models, as the acceptance test** (brings up anything missing, ~4 min cold):
`pytest e2e/test_outcome_prediction_acceptance.py -v`.

**What to say, adapted to whoever's in the room:**

- **Clinician:** "A planning aid for care management, not a diagnosis. It shows *why* — age, her
  coronary disease — and every reason points to a record you can open. It never says 'high risk':
  nobody has signed off what high means yet."
- **Insurer / payer:** "Trained on free US government survey data, returned as a standard FHIR
  resource with a comparison model and a percentile alongside. Fairness by race, insurance, sex and
  age is reported on every model card — including where it falls short."
- **Architect / developer:** "One feature contract for every source: CSV and FHIR produce the same
  rows, with each difference listed and checked by code. Scoring can't read past `as_of` — beat 3
  is a test, not a slide. The agent orchestrates; code writes every word you see, and a gate drops
  any reply with a number the service didn't return."
- **Layperson:** "It looks at a patient's past year and estimates the chance they'll need a hospital
  stay next year — and shows its working."

**Volunteer the weaknesses, same discipline as §4:**

- Synthea patients are simulated: these numbers are a pipeline check, **never** evidence of accuracy
  (Synthea's coronary-disease rate is 4× MEPS's — the data-quality report flags it).
- The production model was tested once on held-out MEPS panels (AUROC 0.795) — never on a real
  customer's patients; it needs recalibrating on their outcomes first (Phase 8b). Its diagnosis inputs
  rest on Synthea's own SNOMED→ICD-10 map, with code lists still unreviewed (O27, O73).
- Synthea's FHIR folds hospice into home health, office into outpatient, and carries no fill counts
  or income — `Encounter/4202` in beat 1's basis is a hospice admission counted as home health, and
  the input notes say so.
- The 1B local model completes about 6 turns in 10; a larger model raises that, never the safety.

**They will ask:**

- *"Is 12% high?"* — The service deliberately doesn't say: it gives the probability and the
  percentile (79th), and leaves the threshold to a clinical decision nobody has made yet (O24).
- *"Can it use our patients?"* — It reads standard FHIR; it needs recalibrating on your outcomes
  first (Phase 8b). High-cost prediction needs claims, not just records.
- *"Does patient data go to an AI company?"* — No. The default model runs on this machine.

---

## 6. Deeper paths

- Run the tests at any level → [`testing-guide.md`](./testing-guide.md)
- Understand or extend the code → [`developer-guide.md`](./developer-guide.md)
- Why Phase 2 is built this way → [`phase2/requirements.md`](./phase2/requirements.md),
  [`phase2/plan.md`](./phase2/plan.md)
- Why Phase 3 is built this way → [`phase3/prd.md`](./phase3/prd.md),
  [`phase3/design.md`](./phase3/design.md)
- Why Phase 8 is built this way → [`phase8/prd.md`](./phase8/prd.md),
  [`phase8/design.md`](./phase8/design.md)
