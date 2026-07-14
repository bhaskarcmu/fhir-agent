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
- An **opt-in** `--profile gateway` runs a **DB-less Kong** locally with **zero manual
  setup** (no Helm, no Neon). The dev API key is **generated at `docker compose up`** by
  a bootstrap entrypoint and templated into both `kong.yml` and the client env — it is
  **never committed to git** (keeps the repo gitleaks-clean; see R14).
- **Gateway model is hybrid, not one-Kong-for-all** (see plan §5, C2 + gateway-strangler):
  Phase 1's KIC/Helm Kong keeps serving `/fhir` in cloud **untouched**; the **DB-less
  Kong is the canonical Phase 2 gateway**, using the same declarative `kong.yml` locally
  and in cloud. Folding Phase 1's route onto the DB-less Kong is a later, reversible
  migration — **not** a Phase 1 rework.

### R11 — Gateway placement & internal isolation
- The **edge Kong** fronts `claims-service`, `fhir-service`, and `triage-service`.
- The `rxclaim-emulator` is on the **internal plane** with **no gateway route**.
  **Isolation controls follow the platform each component runs on** (hybrid, per C1):
  on **Cloud Run** (the Phase 2 target) the emulator uses **`ingress=internal` + IAM
  invoker + VPC connector**; the GKE equivalent (ClusterIP + NetworkPolicy) applies only
  to any component that actually runs on GKE. Locally it is simply not exposed.
- The agent reaches services **through the façade / gateway**, never the legacy core.

### R12 — Data integrity & provenance
Every adjudication decision is auditable: a `Provenance` per decision and the FHIR
API (never the raw DB) is the contract for all application logic.

### R13 — Reference data hygiene
Use **curated fixtures** (small RxNorm/ICD subset, formulary, PA rules, 4 plan
definitions) checked into a `data/payer-kb/` folder; **check existing FHIR data
first** before seeding. No full terminology loads. No AMA-licensed CPT beyond the
tiny curated sample. Sources are confirmed (RxNav, NLM/CDC ICD-10, CMS Part D
Formulary PUF, Synthea) and catalogued under `data/reference/`. Grounding is
**real published data, never fabricated** (per PRD §10.5).

**R13.1 — Payer coverage grounding (Medicare *and* commercial).** Both plan types are
grounded in real public disclosure data so the demo isn't Medicare-only:
- **Medicare:** the **CMS Part D Formulary PUF** — real per-NDC tier / PA / step-therapy /
  quantity-limit.
- **Commercial / private:** the *internal* PA criteria and pricing of private insurers are
  proprietary, but ACA-mandated *disclosure* data is **public and downloadable** and carries
  the adjudication metadata we need. Ground representative commercial plans (Commercial
  Silver/Gold, Employer PPO) in:
  - **ACA Essential Health Benefits (EHB)** benchmark plans — what must be covered.
  - **QHP (Qualified Health Plan) machine-readable formulary files** (healthcare.gov / CMS
    Marketplace PUFs) — per-drug **tier + prior-auth + step-therapy + quantity-limit** flags.
  - *(Optional)* **Transparency-in-Coverage** MRFs for pricing/network realism (large; pricing-focused).
- **The engine stays payer-agnostic:** plan type is a **configuration layer** (federal →
  plan → customer), so Medicare and commercial are the *same* engine with different config —
  mirroring how a real PBM adjudicates both. We ground the *structure*; proprietary PA
  criteria/pricing internals remain out of scope. Exact verified source URLs live in the
  `data/reference/` catalog; the commercial plan definitions + NDC↔RxCUI crosswalk are
  built in **M1**.

### R14 — Security & privacy (treat claims data as if PHI)
- **PHI-safe logging:** do not emit patient/member identifiers to logs. (Fix the
  existing Kong `file-log` behaviour that logs `request.uri` such as `/fhir/Patient/123`;
  scrub identifiers or treat those logs as a restricted PHI store.)
- **AuthN/Z:** static Kong API keys are acceptable for the prototype, but design for
  **OAuth2/OIDC + scopes (SMART-on-FHIR)** as the path (Kong OIDC plugin; the clinical
  client already anticipates OAuth). Consumers are least-privilege.
- **Secrets:** managed via **GCP Secret Manager + Workload Identity** in cloud (no
  secrets in git or plain k8s Secrets); local uses `.env` as today.
- **In transit / at rest:** TLS everywhere **including the gateway proxy** (close the
  Phase 1 no-TLS-on-proxy gap); encryption at rest on all managed data stores.
- **Injection safety:** the legacy emulator's SQL/400-style tables use parameterized
  queries; the anti-corruption layer is the input-validation boundary.
- **Supply chain:** container image vulnerability scanning before deploy.

### R15 — Observability
- **Distributed tracing** across the adjudication fan-out (claims → emulator + triage
  + fhir) via **OpenTelemetry** (W3C `traceparent`) → Cloud Trace; Kong propagates at
  the edge. One claim = one trace.
- **Metrics** via Micrometer/Prometheus (Java) and Prometheus (Python) → Google
  Managed Prometheus (already declared in `kong-values.yaml`): per-stage latency,
  and business metrics (approvals/denials/pends, rule-fire counts).
- **Correlation IDs** in PHI-scrubbed structured logs; health/readiness endpoints on
  every new service.

### R16 — Deployability
- **Container-first**: every service is a container, runnable locally via Compose and
  deployable to cloud with config-only differences.
- **IaC + CI/CD**: **Terraform** for GCP infra (Cloud Run, Cloud SQL/Neon, Secret
  Manager, Artifact Registry, networking) and **GitHub Actions** (build → scan → push →
  deploy). Supersedes hand-run bash. Cloud artifacts + tests are produced **from each
  milestone** (design + stub + test throughout); **live** deploy is Phase 2b (see D8).

### R17 — Decision Contract (normative)
Adjudication must be **deterministic and reproducible**: the same claim + same reference
data ⇒ the same decision, every time. Because multiple checks can fail at once, the
engine is **accumulate-then-resolve**, *not* the triage service's first-match-wins.

**R17.1 — Outcome set.** `ClaimResponse.outcome` is exactly one of:
`approved` · `denied` · `pended` (needs PA / info) · `routed-for-review` (manual).
Mapped to FHIR `ClaimResponse.outcome` (`complete` | `error` | `partial`) with a
platform `decision` code in `ClaimResponse.disposition` + a coded reason list.

**R17.2 — Rule evaluation.** Every applicable rule in the catalog is evaluated (no
short-circuit); each emits zero or more **findings**: `{rule_id, domain, severity, code,
message, basis[]}`. `severity ∈ {DENY, PEND, REVIEW, INFO}`.

**R17.3 — Outcome precedence (deterministic resolution).** After collecting all findings:
1. any `DENY` finding ⇒ **denied**;
2. else any `PEND` finding ⇒ **pended**;
3. else any `REVIEW` finding ⇒ **routed-for-review**;
4. else ⇒ **approved**.
`INFO` findings never change the outcome (annotation only). All findings of the winning
tier are returned as reasons (multi-reason aggregation, per PRD §9.4).

**R17.4 — Tie-breaks / determinism.** Findings are ordered by
`(severity_rank, domain_order, rule_id)` — a total order — so the reason list is stable
across runs and implementations. `domain_order` is the fixed pipeline order
(eligibility → provider → formulary → PA → clinical → coding → medical-necessity →
quantity). No wall-clock, map-iteration, or set ordering may affect output.

**R17.5 — Triage → finding mapping.** The reused triage `RiskAssessment` maps to a
clinical-domain finding: `HIGH` ⇒ `DENY`; `MODERATE` ⇒ `REVIEW`; `LOW` ⇒ no finding.
(Known limitation: triage returns only its first match — sufficient for a safety gate;
documented in the plan.)

**R17.6 — Error taxonomy (distinct from denials).** Three disjoint response classes:
- **Validation error** (malformed/unresolvable claim) → HTTP 400 + `OperationOutcome`;
  **no** `ClaimResponse` persisted.
- **Adjudication decision** (approved/denied/pended/routed) → HTTP 200 + `ClaimResponse`.
- **System error** (emulator/triage/FHIR unavailable) → HTTP 502/503 + `OperationOutcome`;
  **no partial decision** persisted; safe to retry (see R18).

**R17.7 — Canonical schemas.** The request (canonical claim) and `ClaimResponse` have
fixed schemas with committed example payloads for every golden path, grounded in the
Da Vinci PAS shapes and the real Synthea `Claim`/`EOB` samples from the data prework.

**R17.8 — Agent is non-authoritative.** The `claims-agent` explanation is **never** part
of the decision and can never alter an outcome; it only narrates a persisted
`ClaimResponse`. The deterministic services are the sole source of decisions.

### R18 — Audit referential invariants & idempotency (normative)
**R18.1 — One decision id.** Each adjudication has a single `decisionId` stamped on every
artefact (as `identifier`/`meta.tag`) so the full chain is queryable by that id.

**R18.2 — Mandatory links.** Every decision persists a connected graph:
`ClaimResponse.request → Claim`; `ClaimResponse.outcome`/reasons present; if routed,
`Task.focus → ClaimResponse` and `Task.reasonReference`; `Provenance.target →
[Claim, ClaimResponse, Task?]` with `agent` = the adjudicating service; `RiskAssessment`
(clinical) linked via `basis`/`decisionId`. A decision missing any mandatory link is a
defect (enforced by tests, R19).

**R18.3 — Idempotency (four sites, all required).**
- **Intake:** the client supplies an idempotency key (or a claim business identifier);
  re-submitting the same key returns the **existing** `ClaimResponse`, never a duplicate.
- **FHIR writes:** use conditional create (`If-None-Exist` on `identifier`/`decisionId`)
  so a retried write never double-persists artefacts.
- **Legacy emulator call:** `ADJRXCLM` is invoked idempotently (keyed by `decisionId`);
  a retry returns the same legacy result, no double side-effects.
- **Async (if the C3 Pub/Sub path is adopted):** consumers are idempotent because
  delivery is at-least-once; `decisionId` is the dedupe key.

**R18.4 — No partial persistence.** Artefact writes for one decision are all-or-nothing
from the caller's perspective (transaction bundle or compensating cleanup); a system
error leaves **no** half-written decision (per R17.6).

### R19 — Test matrix & golden-fixture governance (normative)
"Per-service tests" is insufficient. The minimum matrix:
- **API contract tests** — request/`ClaimResponse` schema + the R17.6 error taxonomy.
- **Rules golden tests** — input claim → expected findings/outcome, **per rule and for
  combinations** that exercise R17.3 precedence + R17.4 tie-breaks.
- **End-to-end golden paths** — the 4–5 R8 scenarios, asserting `ClaimResponse` **and**
  the R18.2 audit graph.
- **Non-regression snapshots** — stored `ClaimResponse` snapshots; catalogue growth must
  not silently change existing decisions.
- **Idempotency / replay tests** — resubmit + retry at each R18.3 site; assert no
  duplicates and stable output.
- **Phase-1-independence test** — `docker compose up` (no profiles) starts only Phase 1.

**Golden-fixture governance:** fixtures live under `data/payer-kb/` + per-service
`testdata/`; each is generated by a committed script (reproducible), and any change to an
expected decision requires an explicit fixture-update commit with rationale (review gate).

---

## Out of scope for Phase 2

- Coordination of Benefits (COB) and a full PBM platform (per PRD §5.3).
- Full **Da Vinci PAS** profile conformance (we only *nod* to it — see D6).
- Full terminology loads (RxNorm/ICD-10 at 500–1,000+); curated subsets only.
- **Live cloud deployment (real GCP spend)** — deferred to **Phase 2b** (D8). Cloud is
  *not* out of scope: cloud **design, IaC, stubs, and tests are produced from each
  milestone**; only the live/paid deploy is late. Phase 1's proven cloud path stays untouched.
- Any modification to Phase 1 behaviour, contracts, or deploy path.
- **Deferred to Phase 2b (scale path documented + stubbed, not live now):** NoSQL
  formulary store (Bigtable/Firestore) — Postgres-behind-a-repository-interface now,
  tested against a NoSQL emulator (C3); a BigQuery decision-analytics plane — FHIR
  `Provenance` only now (C4); Pub/Sub async intake; Memorystore/Redis caching; OIDC
  (API keys now).

---

## Deviations from the PRD

These are the places where **what we agreed to build differs from the DRAFT PRD**.
Each is intentional.

| # | PRD says | We agreed to | Why |
|---|---|---|---|
| **D1** | Benefit + Prior-Auth **Rules Service in Spring Boot** (§6.2/6.3), implying all rules in Java | **Hybrid**: new adjudication rules (eligibility/formulary/PA/benefit) in Java; **reuse existing Python `triage-service`** for drug-allergy + duplicate-therapy | Those two domains are already built and tested in Python (rules 9 & 10). Rebuilding in Java duplicates logic and risks Phase 1 independence. Still gives a strong Java/Spring modernization story for the façade + emulator + ACL + new rules. |
| **D2** | Legacy emulator described as part of the claims stack | Legacy emulator is its **own top-level module** `rxclaim-emulator/`, a **sibling** to (not a member of) the EHR emulators (`epic-`/`athena-emulator`) | The existing emulators are **EHR FHIR sandboxes**; a legacy claims-adjudication core is a **different category** (non-FHIR, transactional). Keeping it separate avoids muddying that concept. |
| **D3** | "MCP Explanation Agent" as slice 3 (§6.3) | A **separate `claims-agent`**, not an extension of the Phase 1 `mcp-agent` | Keeps Phase 1 independent (no feature-flagging/coupling in the refill agent). Shares only non-clinical plumbing. |
| **D4** | Kong "exists"; local gateway unspecified | **Edge Kong** fronting claims+fhir+triage; emulator strictly private; **opt-in DB-less Kong compose profile** for local parity (default local stays Kong-less); **hybrid gateway** — Phase 1 KIC Kong untouched, DB-less Kong canonical for Phase 2, unified via a gateway-strangler migration | Closes the parity gap without setup burden, and modernizes the gateway without reworking Phase 1's proven cloud path. |
| **D5** | Three scope numbers coexist: "4 checks" (§12.2) vs "15 domains" (§9.2) vs "15–20 rules / 8 domains" (§9.3) | **Canonical:** rule catalog **15–20 rules / ~8 domains**; **4–5 paths** exercised end-to-end by the demo | Removes the internal contradiction; sizes the build to a convincing demo. |
| **D6** | "Anticipates CMS-0057-F"; cites Da Vinci PAS/CRD (§12.1, refs) | **Generic FHIR R4** resources, **structured/named to nod to** Da Vinci PAS/CRD; **no PAS conformance** | Full PAS conformance is weeks of work and over-scoped for a prototype; the nod preserves the talking point cheaply. |
| **D7** | Sizing suggests 500–1,000 ICD/RxNorm (§10.7, §11) | **Curated fixtures** + check-existing-first (PRD's own §11.6 "recommended next move") | Faster, avoids CPT/AMA licensing risk on a public repo, sufficient for a believable demo. |
| **D8** | Implies a GKE/Kong/Neon deployment for the slice | **Hybrid cloud, designed & tested throughout, deployed late:** Phase 1 stays on **GKE (untouched)**; new Phase 2 services target **Cloud Run** (C1); cloud IaC/stubs/tests ship from each milestone; **live** GCP deploy is **Phase 2b** | Adds Cloud Run *alongside* GKE (no Phase 1 rework); keeps cloud a first-class, continuously-tested concern while avoiding GCP spend until the platform is proven locally. Supersedes the earlier "cloud-deferred" framing. |

### Still-open PRD questions (unchanged, tracked)
Carried forward from PRD §13 for later resolution: COB inclusion, CPT licensing
boundaries, five-service vs three-slice nuance, CDS split-out timing, exact seed
counts, NCPDP SCRIPT depth, and final naming. None block the plan.
