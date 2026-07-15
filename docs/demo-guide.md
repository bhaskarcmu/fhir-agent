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

## 6. Deeper paths

- Run the tests at any level → [`testing-guide.md`](./testing-guide.md)
- Understand or extend the code → [`developer-guide.md`](./developer-guide.md)
- Why it's built this way → [`phase2/requirements.md`](./phase2/requirements.md),
  [`phase2/plan.md`](./phase2/plan.md)
