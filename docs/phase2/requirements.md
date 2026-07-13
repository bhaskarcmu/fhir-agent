# Phase 2 — Agreed Requirements

> This is the **contract for what we build**, not a restatement of the PRD.
> It records what we agreed to implement, what we deliberately cut, and where we
> **deviated from the PRD**. Source PRD: *Prescription Claim Adjudication
> Modernization Platform — Phase 2 Scope (DRAFT)*, archived verbatim at
> [`source-prd.md`](./source-prd.md).

## Goal

Demonstrate a **prescription claim adjudication modernisation slice** that a
clinician/reviewer can drive end to end: a claim is submitted, adjudicated
deterministically against a wrapped legacy core plus benefit/prior-auth rules and
reused clinical-safety checks, and the decision is persisted as auditable FHIR
artefacts and explained in plain language by an agent.

Framing (for narrative): AI **explains and orchestrates**; deterministic services
**decide**. The legacy core is **wrapped, not rewritten**. Architecture shows the
**strangler**, **API façade**, and **anti-corruption layer** patterns.

---

## Functional requirements

### R1 — Claim intake
Accept a prescription claim request through a single Java/Spring Boot **API
façade**. Validate it, map it to a canonical claim domain object, and run it
through the adjudication pipeline. Consumers never call the legacy core directly.

### R2 — Legacy adjudication core (simulated)
A separate **`rxclaim-emulator`** service stands in for an IBM i / RxClaim legacy
core with a **convincing legacy shape**:
- Fixed-width / DDS-style record layout for its request/response.
- DB2/SQL400-flavoured table naming, backed by PostgreSQL (or JSON fixtures).
- An RPG/CL-style adjudication function name (e.g. `ADJRXCLM`).
- It is **private**: reachable only by the claims façade, never exposed at the edge.

### R3 — Anti-corruption layer
The claims façade translates the legacy record shape into the canonical
FHIR-aligned domain model, so legacy quirks never leak into the rest of the platform.

### R4 — Benefit + prior-authorization rules (new, deterministic, Java)
A deterministic rules engine covering the **new** adjudication domains:
- **Eligibility** — coverage active on the date of service.
- **Formulary** — on/off formulary, tier, PA flag, quantity limit.
- **Prior authorization** — high-cost / flagged drugs require PA on file.
- **Benefit / quantity / age** rules as needed to reach the rule-count target below.

Rules are **layered** (per PRD §9.5) so the layers can change independently:
1. Federal/public policy (CMS NCD/LCD-inspired).
2. Plan configuration (per plan design).
3. Customer-specific overrides.

**Rule-count target (canonical):** a representative **15–20 rules across ~8
domains** (eligibility, provider, formulary, prior-auth, clinical, coding, medical
necessity, quantity). Not all need to be exercised by the demo.

### R5 — Clinical safety (REUSED, not rebuilt)
Drug-allergy and duplicate-therapy checks are **not reimplemented**. The claims
façade calls the **existing Phase 1 `triage-service`** (`POST /triage/refill-risk`,
unchanged) over HTTP for clinical-safety evaluation. This is the CDS sub-module.

### R6 — Decision artefacts (FHIR, Da Vinci-aware, generic)
Each adjudication persists auditable FHIR R4 resources to the existing HAPI server:
- `Claim` / `ClaimResponse` (approve / reject / pend / route-to-review).
- `Task` for manual review when routed.
- `Provenance` (one per decision) and `RiskAssessment` for the audit trail.
- `CoverageEligibilityResponse` where appropriate.

Resources are **structured and named to nod to Da Vinci PAS / CRD and CMS-0057-F**
but are **generic R4** — full PAS profile conformance is out of scope (see D6).

### R7 — Explanation agent (SEPARATE from Phase 1 agent)
A dedicated **`claims-agent`** calls the claims façade and explains, in natural
language, why a claim was approved, rejected, pended, or routed — in the style of
PRD §9.4. It is a **new, separate agent**, not an extension of the Phase 1
`mcp-agent`. It holds **no clinical/business logic** (that lives in the services).
It may share only non-clinical plumbing (Anthropic client setup, tool-loop
scaffolding, output formatting) with the Phase 1 agent.

### R8 — Runnable demo
The whole flow runs locally via Docker Compose, seeded with a dedicated claims
demo dataset, producing 4–5 golden-path outcomes:
1. **Approved** — on-formulary, tier 1, coverage active, no conflicts.
2. **Rejected** — coverage inactive on date of service.
3. **Pended → review Task** — high-cost drug, no PA on file.
4. **Safety alert** — penicillin allergy + amoxicillin (reuses Phase 1 triage; ties Phase 1 → Phase 2).
5. *(stretch)* **Multi-reason** — non-formulary + quantity limit (matches PRD §9.4 sample).

---

## Non-functional requirements

### R9 — Phase 1 independence (HARD CONSTRAINT)
Phase 1 must stay **independently runnable, testable, and cloud-deployable** with
zero Phase 2 components present.
- `docker compose up` starts **only** Phase 1 (fhir, triage, mcp-agent), unchanged.
- Phase 1 test suites and `deploy.sh` behave exactly as at tag `phase1-v1`.
- Dependency direction is **Phase 2 → Phase 1 only**; nothing in Phase 1 references Phase 2.
- All changes to shared files (compose, `.ona`, `pytest.ini`, `client/clinical`,
  gateway config) are **additive** — no existing signature, contract, service name,
  port, or ordering changes.

### R10 — Local ↔ cloud parity, easily switchable
- The **same logical topology** exists locally and in cloud; switching is config-only.
- **Local default is Kong-less** (fast inner loop, no API keys, no setup).
- An **opt-in** `--profile gateway` runs a **DB-less Kong** locally with **zero
  setup** (no Helm, no Neon, no key provisioning; a committed local-only dev key).
- Cloud continues to use the existing KIC/Helm Kong.

### R11 — Gateway placement
- **One** Kong gateway on the **edge plane**, fronting `claims-service`,
  `fhir-service`, and `triage-service`.
- The `rxclaim-emulator` is on the **internal plane** and has **no gateway route**
  (enforced by NetworkPolicy in cloud; not exposed in compose).
- The agent reaches services **through the façade / gateway**, never the legacy core.

### R12 — Data integrity & provenance
Every adjudication decision is auditable: a `Provenance` per decision and the FHIR
API (never the raw DB) is the contract for all application logic.

### R13 — Reference data hygiene
Use **curated fixtures** (small RxNorm/ICD subset, formulary, PA rules, 4 plan
definitions) checked into a `data/payer-kb/` folder; **check existing FHIR data
first** before seeding. No full terminology loads. No AMA-licensed CPT beyond the
tiny curated sample.

---

## Out of scope for Phase 2

- Coordination of Benefits (COB) and a full PBM platform (per PRD §5.3).
- Full **Da Vinci PAS** profile conformance (we only *nod* to it — see D6).
- Full terminology loads (RxNorm/ICD-10 at 500–1,000+); curated subsets only.
- **Phase 2 cloud deployment** — this phase is **local-first**; Phase 2 cloud
  tooling comes later so Phase 1's proven cloud path stays untouched (see D8).
- Any modification to Phase 1 behaviour, contracts, or deploy path.

---

## Deviations from the PRD

These are the places where **what we agreed to build differs from the DRAFT PRD**.
Each is intentional.

| # | PRD says | We agreed to | Why |
|---|---|---|---|
| **D1** | Benefit + Prior-Auth **Rules Service in Spring Boot** (§6.2/6.3), implying all rules in Java | **Hybrid**: new adjudication rules (eligibility/formulary/PA/benefit) in Java; **reuse existing Python `triage-service`** for drug-allergy + duplicate-therapy | Those two domains are already built and tested in Python (rules 9 & 10). Rebuilding in Java duplicates logic and risks Phase 1 independence. Still gives a strong Java/Spring modernization story for the façade + emulator + ACL + new rules. |
| **D2** | Legacy emulator described as part of the claims stack | Legacy emulator is its **own top-level module** `rxclaim-emulator/`, a **sibling** to (not a member of) the EHR emulators (`epic-`/`athena-emulator`) | The existing emulators are **EHR FHIR sandboxes**; a legacy claims-adjudication core is a **different category** (non-FHIR, transactional). Keeping it separate avoids muddying that concept. |
| **D3** | "MCP Explanation Agent" as slice 3 (§6.3) | A **separate `claims-agent`**, not an extension of the Phase 1 `mcp-agent` | Keeps Phase 1 independent (no feature-flagging/coupling in the refill agent). Shares only non-clinical plumbing. |
| **D4** | Kong "exists"; local gateway unspecified | **One edge Kong** fronting claims+fhir+triage; emulator strictly private; **new opt-in DB-less Kong compose profile** for local parity; **default local stays Kong-less** | Closes the parity gap (local never exercised Kong before) without imposing any setup burden on the daily dev loop. |
| **D5** | Three scope numbers coexist: "4 checks" (§12.2) vs "15 domains" (§9.2) vs "15–20 rules / 8 domains" (§9.3) | **Canonical:** rule catalog **15–20 rules / ~8 domains**; **4–5 paths** exercised end-to-end by the demo | Removes the internal contradiction; sizes the build to a convincing demo. |
| **D6** | "Anticipates CMS-0057-F"; cites Da Vinci PAS/CRD (§12.1, refs) | **Generic FHIR R4** resources, **structured/named to nod to** Da Vinci PAS/CRD; **no PAS conformance** | Full PAS conformance is weeks of work and over-scoped for a prototype; the nod preserves the talking point cheaply. |
| **D7** | Sizing suggests 500–1,000 ICD/RxNorm (§10.7, §11) | **Curated fixtures** + check-existing-first (PRD's own §11.6 "recommended next move") | Faster, avoids CPT/AMA licensing risk on a public repo, sufficient for a believable demo. |
| **D8** | Implies a GKE/Kong/Neon deployment for the slice | **Phase 2 is local-first; cloud deferred** | Phase 1 is already cloud-tested; Phase 2 cloud maturity comes later. Deferring keeps Phase 1's proven cloud path unmodified. |

### Still-open PRD questions (unchanged, tracked)
Carried forward from PRD §13 for later resolution: COB inclusion, CPT licensing
boundaries, five-service vs three-slice nuance, CDS split-out timing, exact seed
counts, NCPDP SCRIPT depth, and final naming. None block the plan.
