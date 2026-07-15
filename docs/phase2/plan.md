# Phase 2 — Implementation Plan

> Architecture, topology, and sequencing for the requirements in
> [`requirements.md`](./requirements.md). **No application code exists yet.**

## 1. Target architecture

Phase 2 **extends** the Phase 1 skeleton (`mcp-agent → triage → fhir`) rather than
altering it. Two new Java/Spring Boot services and one new Python agent are added.

```
                         ┌──────────── EDGE PLANE (Kong) ────────────┐
claims-agent ──apikey──▶ Kong proxy ─ key-auth ─ rate-limit ─ log/metrics
(Phase 2, NEW)            │   /claims ──▶ claims-service   (façade, NEW)
                          │   /fhir   ──▶ fhir-service     (existing)
mcp-agent ───────────────┘   /triage ──▶ triage-service   (existing, now routable)
(Phase 1, UNCHANGED)      └───────────────────┬────────────────────┘
                                              │ claims-service orchestrates:
              ┌───────────────────────────────┼──────────────────────────────┐
              ▼ (FHIR reads/writes)            ▼ (clinical safety, REUSE)      ▼ (PRIVATE, direct)
        fhir-service:8080              triage-service:8001            rxclaim-emulator (NEW)
        (HAPI R4)                      POST /triage/refill-risk       DDS records, DB2/SQL400
              │                        (UNCHANGED)                    tables, ADJRXCLM function
              ▼                                                              │
        FHIR resources:                                                      ▼
        Claim, ClaimResponse,                                        legacy claims tables
        Task, Provenance,                                            (Postgres / JSON fixtures)
        CoverageEligibilityResponse
```

**Two planes (the core placement rule):**
- **North–south / edge** — external callers → platform. Auth, rate-limit, quota,
  logging live here. **Kong owns it.** Routes: `/claims`, `/fhir`, `/triage`.
- **East–west / internal** — service → service. The **`rxclaim-emulator` lives
  here and has no edge route** — that is what makes the API-façade / anti-corruption
  story real rather than cosmetic. The agent never calls the legacy core.

## 2. Components

| Component | Type | Plane | New? | Responsibility |
|---|---|---|---|---|
| `claims-service` | Java 21 / Spring Boot | Edge (façade) + orchestration | **NEW** | Claim intake, validation, **anti-corruption layer**, **layered benefit/PA rules**, pipeline orchestration, FHIR artefact persistence |
| `rxclaim-emulator` | Java 21 / Spring Boot | Internal (private) | **NEW** | Simulated legacy IBM i / RxClaim core: DDS-style records, DB2/SQL400 tables, RPG/CL-style `ADJRXCLM` function |
| `claims-agent` | Python (Anthropic tool-use) | Client | **NEW** | Explains adjudication outcomes in natural language; no clinical logic |
| `triage-service` | Python / FastAPI | Internal | reuse | Drug-allergy + duplicate-therapy via `POST /triage/refill-risk` — **unchanged** |
| `fhir-service` | HAPI R4 | Edge (data) | existing | Persistence & clinical backbone — **unchanged** |
| `mcp-agent` | Python | Client | existing | Phase 1 refill agent — **unchanged** |

### Adjudication pipeline (inside `claims-service`)
Claim → member eligibility → coverage/benefit → formulary → prior-auth →
**clinical safety (call triage)** → **legacy adjudication (call rxclaim-emulator)**
→ anti-corruption translation → **accumulate findings from every stage** → resolve to
one outcome by the **Decision Contract precedence** (§10, R17) → persist the linked FHIR
artefact graph (§11, R18): `Claim`/`ClaimResponse`/`Task?`/`Provenance`/`RiskAssessment`.
The pipeline order is also the deterministic `domain_order` tie-break (R17.4). No stage
short-circuits — all applicable rules run so multi-reason denials aggregate (PRD §9.4).

### Reuse boundary (deviation D1)
Clinical safety is delegated to the existing triage HTTP contract
(`{patient_id, medication_id?}` → FHIR `RiskAssessment`). No triage code changes; Phase 1
stays independent. Triage's result maps to a clinical finding per R17.5 (`HIGH`→DENY,
`MODERATE`→REVIEW, `LOW`→none). **Known limitation:** triage is first-match-wins so it
returns only its top finding — sufficient for a safety gate, noted in §8.

## 3. Gateway & local/cloud parity

### Placement changes vs Phase 1
- **Today:** Kong is cloud-only and fronts **only** `/fhir`. Local dev bypasses Kong
  entirely (`FHIR_GATEWAY_URL` defaults direct-to-container). Note: `triage`/`mcp-agent`
  are **not cloud-deployed at all today** — only Kong + `fhir-service` are (`deploy.sh`).
- **Phase 2 (cloud, Phase 2b):** DB-less Kong adds `/claims` and `/triage` routes; the
  emulator gets **no route** and `ingress=internal` (Cloud Run). Phase 1's KIC Kong +
  `deploy.sh` + `gateway/kong/*` are **left untouched** — see the gateway-strangler below.
- **Phase 2 (local):** add an **opt-in DB-less Kong** to compose.

### The two local modes (parity switch)
```bash
docker compose up -d                          # DEFAULT: Phase 1 only, no Kong, no keys
docker compose --profile phase2 up -d         # + claims-service, rxclaim-emulator, claims-agent (direct calls)
docker compose --profile phase2 --profile gateway up -d   # + edge Kong fronting everything (parity test)
```
- Default and `--profile phase2` inner loops are **Kong-less** — zero setup.
- `--profile gateway` runs **DB-less Kong** (declarative `kong.yml`, in-memory). The dev
  API key is **generated at `up`** by a bootstrap entrypoint and templated into `kong.yml`
  + the client env — **never committed** (R10, gitleaks-clean). **No Helm, no Neon, no
  manual key provisioning** — still one command.
- Switching is config-only via env vars: `FHIR_GATEWAY_URL`, `TRIAGE_SERVICE_URL`,
  and a new `CLAIMS_GATEWAY_URL` (default direct; point at Kong for gated mode).

### Parity dialect — resolved by decision C2
Earlier this section flagged a drift risk between Kong's cloud config (KIC CRDs) and the
local `kong.yml`. **C2 removes it for Phase 2:** the DB-less declarative `kong.yml` is the
single source of truth, used **both** locally and for the Phase 2 cloud gateway (fronting
Cloud Run URLs in cloud, containers locally). Phase 1's KIC config is **not migrated** —
it keeps serving `/fhir` untouched until the gateway-strangler step below.

### Gateway-strangler — hybrid, with a reversible migration
The gateway is the **one genuinely cross-phase artifact**. Rather than a risky rewrite,
the two gateways coexist and Phase 2 strangles the old one on our schedule:

| State | Phase 1 KIC Kong | Phase 2 DB-less Kong | `/fhir` served by |
|---|---|---|---|
| **S0 (today)** | `/fhir` (GKE) | — | KIC |
| **S1 (Phase 2b deploy)** | `/fhir` (GKE, untouched) | `/claims`, `/triage` (Cloud Run) | KIC |
| **S2 (opt-in migration)** | idle / removed | `/claims`, `/triage`, **`/fhir`** | DB-less |

- **Transition:** at S2, add the `/fhir` route (already proven in the local `kong.yml`)
  to the DB-less Kong and cut DNS/ingress over.
- **Rollback:** re-point to the KIC Kong (still present through S1→S2); it is only
  decommissioned after S2 is confirmed healthy.
- **Ownership:** platform/SRE owns the cutover + rollback runbook; the S0→S1 steps
  require **no** change to Phase 1 (independence preserved, R9).

### Gotchas
- Local Kong **admin** must not use `:8001` (taken by `triage`); map to `:8081`.
  Proxy stays `:8000` to match the cloud port-forward convention.

## 4. Isolation strategy (enforcing R9)

The dependency arrow points **Phase 2 → Phase 1 only**.

| Shared surface | How Phase 1 stays independent |
|---|---|
| `docker-compose.yml` | New services carry `profiles: [phase2]` / `[gateway]`; Phase 1 services get no profile → plain `up` is byte-for-byte today's. Verify with `docker compose config`. |
| Cloud deploy | `deploy.sh` and `gateway/kong/*` (KIC) untouched. Phase 2 uses a **separate** DB-less `gateway/kong/kong.yml` + `infra/terraform/` + `deploy-phase2.sh`; Phase 1's GKE path is never modified (gateway-strangler, §3). |
| Tests | Phase 2 tests in new packages; CI keeps a "Phase 1 only" job. `pytest.ini` extended, never narrowed. |
| Seeding | New `data/scripts/seed_claims_demo.py` + `data/payer-kb/`; `seed_demo.py` untouched. Use `FHIR_GATEWAY_URL` (consistency with seed_demo/agent). |
| `client/clinical` | Additive methods only (e.g. `get_coverage`) following the `_parse_*` pattern; no existing signature changes. Java services use their own FHIR access. |
| `mcp-agent` | Untouched — claims explanation is a **separate** `claims-agent` (D3). |
| `.ona/automations.yaml` | Append new Python pkgs to the `installDependencies` `pip install -e` list; add build tasks with `dependsOn: installDependencies`. Don't replace. |

**Safety net:** tag `phase1-v1` = known-good, independently deployable snapshot.

## 5. Cloud architecture — compute, data, security, observability, scalability

> **Cloud is a first-class concern from every milestone**, not back-loaded: each service
> ships its Terraform + Cloud Run config, cloud contract/smoke tests (against emulators &
> stubs), and OTel wiring from *its* milestone. Only the **live/paid GCP deploy** is late
> (**Phase 2b**, per the revised D8). Writing services stateless/12-factor with the C3
> repository seam now makes that deploy a config step, not a rewrite. Decisions are C1–C4.

### C1 — Compute: hybrid — GKE for Phase 1 (untouched) + Cloud Run for Phase 2 (new)
This is **additive, with no Phase 1 rework**:
- **Phase 1 stays on GKE exactly as today** — KIC Kong + `fhir-service` (HAPI). Not moved,
  not modified. HAPI stays always-on there (its ~3-min cold start, the 180s probe).
- **New Phase 2 services** (`claims-service`, `rxclaim-emulator`, `claims-agent`) are
  **stateless request/response → Cloud Run** (scale-to-zero, concurrency autoscale).
- **`triage` in cloud is greenfield** — it is *not* cloud-deployed today, so putting it on
  Cloud Run is a new deploy, not a migration.
- **Isolation follows the platform** (no dual control for one component): the emulator on
  Cloud Run uses **`ingress=internal` + IAM invoker + VPC connector** (the GKE
  ClusterIP+NetworkPolicy equivalent applies only to GKE workloads). Emulator has **no
  gateway route** either way.
- Spring cold-start on Cloud Run is mitigated with `min-instances` and, if needed, GraalVM
  native / CRaC.

### Modernization state — the strangler snapshot we depict
The prototype captures a **deliberate mid-migration snapshot**, not a green-field or a
finished migration. This makes the strangler *legible*: it says exactly what has been
peeled off the legacy core and what has not.

**Strangled → modern (Java/Spring + reused Python + FHIR):**
- Intake / API / validation / canonicalization (the façade + anti-corruption layer).
- **Benefit-determination rules** — eligibility, formulary status, prior-auth requirements,
  quantity limits (the layered rules engine).
- **Clinical decision support** — drug-allergy, duplicate-therapy (reused `triage-service`).
- **Decision orchestration + audit/interop** — the Decision Contract (§10) and FHIR
  artefacts (`Claim`/`ClaimResponse`/`Task`/`Provenance`).

**Still legacy (IBM i / RxClaim core — wrapped, not rewritten):**
- The authoritative **adjudication transaction** (`ADJRXCLM`) that posts the claim.
- **Pricing / financials** (ingredient cost, dispensing fee, copay/coinsurance, plan-pay).
- **Systems-of-record** — member/coverage master and **accumulators** (deductible / OOP
  running balances).

**Why this split:** you strangle the *decisioning and experience* first (high value, lower
blast radius) and migrate **money + system-of-record last** (highest risk, most encoded).
The pipeline order (§2) reflects this — modern rule checks run *in front of* the legacy
call, so each future strangler step pulls another responsibility forward until the core can
be retired.

**Trajectory:** past = legacy did everything → **now** = rules/experience/audit modern,
pricing/SOR legacy → next = extract pricing, then accumulators/coverage SOR, then retire
`ADJRXCLM`. (We apply the same pattern to infrastructure — the gateway-strangler, §3.)

### C2 — Gateway: DB-less Kong everywhere
One declarative `kong.yml` fronts everything in **both** environments (Cloud Run URLs as
upstreams in cloud; containers locally). Single config dialect → no drift (see §3). Kong
itself runs as a container (Cloud Run `min-instances ≥ 1`, or small GKE). Edge routes:
`/claims`, `/fhir`, `/triage`; emulator has none.

### C3 — Data: managed, scalable, with a documented NoSQL path
| Data | Store (now) | Scale path |
|---|---|---|
| FHIR resources | Postgres (Neon, autoscaling + `-pooler`) | read replicas; HAPI partitioning / Elasticsearch search |
| Formulary / PA rules | **Postgres behind a repository interface** | swap to **Bigtable/Firestore** (key: `plan_id+NDC → rule`) — the true high-cardinality KV pattern |
| Legacy emulator tables | Postgres (SQL/400-style) | small/reference; stays relational |
| Decision audit | **FHIR `Provenance`/`RiskAssessment`** in HAPI | add a **BigQuery** analytics plane later (C4) |

The repository interface for formulary/PA is the key seam: build on Postgres now, make
Bigtable/Firestore a swap, never a rewrite. Claim intake is written **Pub/Sub-ready**
(accept → enqueue → adjudicate) so bursts decouple; caching/rate-limit scale via
Memorystore (Redis) — Kong's documented `redis` policy upgrade.

**Why relational *and* NoSQL (the trade-off, stated explicitly):** money and truth need
**ACID** (atomic, consistent, isolated, durable) — you cannot lose, double, or corrupt a
payment or an accumulator — so the **claim-of-record + accumulators are relational**
(Postgres / Db2 for i). Formulary/PA is a **high-cardinality key-value read**
(`plan_id + NDC → rule`, tens of millions of combinations, read-heavy, changes quarterly),
which is exactly what a **NoSQL KV store** does at scale — so there we trade strict
consistency for horizontal scale, which a quarterly formulary tolerates and money does not.

### Reliability & scale patterns (request path)
Concrete patterns the services implement so scale never costs correctness:
- **Load-level with a queue, don't just rate-limit.** A spike is absorbed by a queue
  (Pub/Sub/SQS) and processed at a steady pace (nobody is dropped); gateway rate-limiting is
  a last-resort safety valve, not the primary defense. Consumers autoscale on queue depth.
  (Queues deliver at-least-once → consumers must be idempotent, R18.3.)
- **Circuit breaker on the legacy call.** Calls to the IBM i core are wrapped in a breaker:
  after repeated failures it **opens** and fails fast (or pends) instead of piling up threads
  and cascading a platform-wide outage; a **half-open** probe restores it. One sick
  dependency degrades gracefully rather than taking everything down.
- **No partial persistence (R18.4).** A decision's artefacts are written all-or-nothing
  (FHIR transaction bundle or a compensating action), so a mid-flight failure leaves nothing
  half-written — which is what makes the client's retry clean and safe.

### C4 — Audit/analytics: FHIR Provenance now, BigQuery later
Every decision persists a FHIR `Provenance` with the R18 referential invariants. A
scalable BigQuery decision-warehouse + rule-fire dashboard is **deferred to Phase 2b**
(designed now, not built).

### Security (R14) & observability (R15) in cloud
- **Secrets** → GCP Secret Manager + Workload Identity. **TLS** terminated at the edge
  incl. the proxy. **PHI-safe logging** — scrub identifiers (fixes the Kong `file-log`
  URI leak). **AuthN** stays API-key for the prototype, OIDC/JWT the documented path.
- **Tracing** → OpenTelemetry (`traceparent`) across the fan-out → Cloud Trace; **metrics**
  → Managed Prometheus (per-stage latency + approvals/denials/pends/rule-fires).
- **IaC/CI-CD (R16)** → Terraform (Cloud Run, Cloud SQL/Neon, Secret Manager, Artifact
  Registry, networking) + GitHub Actions (build → scan → push → deploy).

*(GKE reference — for Phase 1, which stays on GKE: `fhir-service/k8s/` = namespace
labelled `app.kubernetes.io/managed-by: kong`, ClusterIP `service`, `deployment` with
`IMAGE_PLACEHOLDER`, actuator probes. New Phase 2 services target Cloud Run per C1, so
they do not add GKE manifests unless a component is deliberately placed on GKE.)*

## 6. Workstreams / milestones

> **Status: M0–M7 are complete.** The slice runs end to end locally: submit a claim →
> deterministic decision → FHIR artefact graph → plain-language explanation. **M8 (Phase 2b,
> the live cloud deploy) has not started** — its Terraform is authored but never applied.
> What comes next is §16.

Cloud is threaded through every milestone (design + stub + test), per the revised D8; the
**Cloud touchpoint** column is the artifact/test produced *then* (not live-deployed until
Phase 2b). Stakeholder deliverables per milestone are in §13.

| # | Milestone | Deliverable | Cloud touchpoint (design/stub/test) | Depends on |
|---|---|---|---|---|
| **M0** | Recon (read-only) | Run PRD §11.3 FHIR counts against live server; seed only the gap. Note compose/README HAPI drift (`v7.2.0` vs `8.8.0`) and `FHIR_GATEWAY_URL`/`FHIR_BASE_URL`. | Target topology diagram (GKE+Cloud Run hybrid); `infra/terraform/` skeleton. | — |
| **M1** | Payer knowledge base | Curated `data/payer-kb/` (formulary, PA rules, 4 plans, RxNorm/ICD subset). Sources confirmed in prework (see `data/reference/`). | C3 **repository interface** defined for formulary/PA (Postgres impl + a NoSQL-emulator impl behind the same seam). | M0 |
| **M2** | `rxclaim-emulator` | Spring Boot legacy core: DDS records, DB2/SQL400 tables, `ADJRXCLM`, legacy response. Parameterized queries (R14). | Terraform module + **Cloud Run service config** for the emulator (`ingress=internal`); cloud **smoke test in CI** (deploy to emulator/stub). | M1 |
| **M3** | `claims-service` core | Façade + ACL + layered rules engine; calls emulator + triage; **Decision Contract** (§10, R17). | OTel tracing wired; health/readiness; Cloud Run config; **contract tests** (R19). | M1, M2 |
| **M4** | Pipeline & artefacts | Wire pipeline; accumulate→resolve; emit the linked artefact graph (§11, R18): `Claim`/`ClaimResponse`/`Task`/`Provenance`/`RiskAssessment`/`CoverageEligibilityResponse`. | Trace of one claim across services; **idempotency/replay tests** (R18.3); Managed-Prometheus metric names. | M3 |
| **M5** | `claims-agent` | Separate explanation agent over the façade; non-authoritative (R17.8); shares only non-clinical plumbing with `mcp-agent`. | Cloud Run config; PHI-safe log assertions in CI. | M4 |
| **M6** | Local wiring & demo | Compose `phase2` profile; DB-less Kong `gateway` profile (generated dev key); `seed_claims_demo.py`; 4–5 golden paths. | `kong.yml` == the cloud gateway config (C2); gateway-strangler runbook drafted (§3). | M4, M5 |
| **M7** | Tests & narrative | Full **test matrix** (§12, R19); Phase-1-only CI job; README/platform narrative. | End-to-end cloud **dry-run** (Terraform plan + CI deploy to stubs, no live spend); Phase-2b deploy runbook. | M6 |
| **M8 = Phase 2b** | *(separate deliverable)* **Live cloud** | Terraform **apply** to GCP: Cloud Run + Cloud SQL/Neon + Secret Manager + Artifact Registry; DB-less Kong live; emulator `ingress=internal`; OTel→Cloud Trace + Managed Prometheus live; gateway-strangler S1→S2. First real GCP spend. | *(this is the live deploy)* | M7 |

Every service ships its Compose entry **and** its Terraform/Cloud Run config **from its own
milestone** (M2–M5), so by M7 the cloud path is fully authored and stub-tested; Phase 2b is
`terraform apply`, not new construction. Services are stateless/12-factor with the C3
repository seam from day one.

## 7. Directory layout (proposed, additive)
```
claims-service/        # NEW — Java/Spring Boot façade + rules + ACL
rxclaim-emulator/      # NEW — Java/Spring Boot legacy core (sibling to epic-/athena-emulator, NOT inside them)
claims-agent/          # NEW — Python explanation agent
data/payer-kb/         # NEW — curated formulary/PA/plan fixtures
data/scripts/seed_claims_demo.py   # NEW
gateway/kong/kong.yml  # NEW — DB-less declarative config, single source of truth (local + cloud, C2)
infra/terraform/       # NEW (M8) — Cloud Run, Cloud SQL/Neon, Secret Manager, Artifact Registry
docs/phase2/           # THIS planning set
```
(Phase 1's existing `gateway/kong/*` KIC config is left untouched; the DB-less
`kong.yml` is the Phase 2 target per C2.)

## 8. Risks & open questions
- **Config-dialect drift** — *resolved* by C2 (DB-less `kong.yml` is the single source of
  truth for Phase 2; Phase 1 KIC untouched via the gateway-strangler, §3).
- **Two gateways during transition** — accepted and bounded by the strangler states
  S0→S1→S2 with a rollback path (§3); no forced Phase 1 rework.
- **Cloud Run cold starts** — Spring Boot/HAPI cold-start; mitigate with `min-instances`
  (always-on HAPI + Kong), GraalVM native / CRaC if needed (C1).
- **Triage under-reports for aggregation** — first-match-wins returns one finding; fine as
  a safety gate (R17.5), but a full multi-reason clinical list would need a triage change
  (out of scope — keeps Phase 1 independent).
- **PHI in gateway logs** — Kong `file-log` logs request URIs with identifiers; scrub or
  treat as restricted (R14) — applies to Phase 1 today too.
- **Compose HAPI version drift** — reconcile in M0 (`v7.2.0` vs `8.8.0`) before building around it.
- **`client/clinical` additions** — keep strictly additive; Java services should not
  depend on the Python client.
- **PRD open items** (COB, CPT licensing, NCPDP SCRIPT depth, naming) — tracked in
  `requirements.md`; none block M0–M7.
- **Scope creep into full PAS/terminology/NoSQL/BigQuery** — out of scope / deferred to
  Phase 2b (D6, D7, C3, C4).

## 9. Definition of done (Phase 2, local)
- `docker compose --profile phase2 up` + `seed_claims_demo.py` → the 4 core golden
  paths produce correct `ClaimResponse` + explanation, end to end, satisfying the
  **Decision Contract** (§10) and the **audit invariants** (§11).
- The full **test matrix** (§12) is green, including idempotency/replay and the
  Phase-1-independence test.
- `--profile gateway` variant passes the same flow through Kong with a **generated** key.
- `docker compose up` (no profiles) + all Phase 1 tests + `deploy.sh` behave exactly
  as at `phase1-v1`.
- Cloud is **authored and stub-tested** (Terraform plan clean, CI cloud smoke tests
  green) — live GCP deploy is Phase 2b, not required for local DoD.

---

## 10. Decision Contract (normative — implements R17)

Adjudication is **accumulate-then-resolve**, not the triage engine's first-match-wins.
Every applicable rule runs; findings are collected, then a single outcome is resolved
deterministically.

**Finding** (emitted by any rule): `{rule_id, domain, severity, code, message, basis[]}`,
`severity ∈ {DENY, PEND, REVIEW, INFO}`.

**Outcome precedence** (first tier with any finding wins):

| Rank | If any finding has severity | `outcome` | FHIR `ClaimResponse.outcome` |
|---|---|---|---|
| 1 | `DENY` | `denied` | `error` (with reasons) |
| 2 | `PEND` | `pended` | `partial` |
| 3 | `REVIEW` | `routed-for-review` | `partial` (+ `Task`) |
| 4 | *(none of the above)* | `approved` | `complete` |

`INFO` never changes the outcome. **All** findings of the winning tier are returned as
reasons (multi-reason aggregation, PRD §9.4).

**Determinism / tie-break:** findings are sorted by a total order
`(severity_rank, domain_order, rule_id)`, where `domain_order` = the fixed pipeline order
(eligibility → provider → formulary → PA → clinical → coding → medical-necessity →
quantity). No wall-clock, hash-map iteration, or set ordering may influence output.

**Triage mapping (R17.5):** `HIGH`→`DENY`, `MODERATE`→`REVIEW`, `LOW`→no finding.

**Error taxonomy (R17.6) — three disjoint classes:**

| Class | Trigger | HTTP | Persisted |
|---|---|---|---|
| Validation error | malformed / unresolvable claim | 400 + `OperationOutcome` | none |
| Adjudication decision | approved/denied/pended/routed | 200 + `ClaimResponse` | full graph (§11) |
| System error | emulator/triage/FHIR unavailable | 502/503 + `OperationOutcome` | none (retry-safe) |

**Example (matches PRD §9.4):** a claim that is eligible + in-network but non-formulary
(PA required) **and** over quantity limit → findings `[formulary:PEND, quantity:REVIEW]`
→ precedence rank 2 → **`pended`**, reasons = both findings, plus a review `Task`.
Canonical request + `ClaimResponse` example payloads are committed per golden path,
grounded in the Da Vinci PAS shapes and the real Synthea `Claim`/`EOB` samples.

**Agent non-authoritative (R17.8):** the `claims-agent` only narrates a persisted
`ClaimResponse`; it can never change an outcome.

## 11. Audit graph & idempotency (normative — implements R18)

**One `decisionId`** per adjudication, stamped on every artefact. **Mandatory links:**

```
Provenance.target ─┬─▶ Claim  ◀── ClaimResponse.request
                   ├─▶ ClaimResponse ──(if routed)──▶ Task.focus
                   └─▶ Task?                          Task.reasonReference ─▶ ClaimResponse
RiskAssessment (clinical) ──basis / decisionId──▶ the decision
Provenance.agent = adjudicating service (claims-service)
```
A decision missing any mandatory link is a defect (asserted by e2e tests, §12).

**Idempotency — four sites, all required (R18.3):**

| Site | Key | Behaviour on retry |
|---|---|---|
| Intake | client idempotency key / claim business id | return existing `ClaimResponse`, no duplicate |
| FHIR writes | `identifier`/`decisionId` via `If-None-Exist` | conditional create — no double-persist |
| Emulator (`ADJRXCLM`) | `decisionId` | same legacy result, no double side-effect |
| Async (if C3 Pub/Sub) | `decisionId` dedupe | at-least-once safe |

**No partial persistence (R18.4):** one decision's writes are all-or-nothing (transaction
bundle or compensating cleanup); a system error leaves no half-written decision.

## 12. Test matrix (normative — implements R19)

| Layer | Asserts | Ties to |
|---|---|---|
| API contract | request/`ClaimResponse` schema + error taxonomy | R17.6/R17.7 |
| Rules golden | claim → expected findings/outcome, per rule **and combinations** | R17.3/R17.4 |
| End-to-end golden paths | the 4–5 R8 scenarios: `ClaimResponse` + full audit graph | R8/R18.2 |
| Non-regression snapshot | stored `ClaimResponse` snapshots; catalogue growth can't silently change existing decisions | R17 |
| Idempotency / replay | resubmit + retry at each §11 site → no duplicates, stable output | R18.3 |
| Phase-1-independence | `docker compose up` (no profiles) starts only Phase 1 | R9 |
| Cloud smoke (stub) | Terraform plan clean; CI deploy to emulators/stubs green | R16 |

**Golden-fixture governance:** fixtures under `data/payer-kb/` + per-service `testdata/`,
each generated by a committed script; changing an expected decision requires an explicit
fixture-update commit with rationale (review gate).

## 13. Stakeholder × milestone deliverables

What each audience can expect after each milestone (see §6 for the engineering detail).

| After | Exec / Business | Product Owner | Solution Architect | Developer | Security / Compliance | SRE / Platform |
|---|---|---|---|---|---|---|
| **M1** | data-grounding story (real CMS/RxNorm) | KB scope + plan definitions | C3 repository seam | payer-KB fixtures + schema | data provenance/licensing note | Terraform skeleton |
| **M2** | "legacy core is wrapped" narrative | emulator scope | ACL boundary + legacy contract | emulator API + golden fixtures | injection-safe queries reviewed | emulator Cloud Run config + CI smoke |
| **M3** | modernization-layer story | decision behaviour defined | **Decision Contract** + trace design | `claims-service` API + contract tests | PHI-safe logging wired | OTel→trace; health probes |
| **M4** | first adjudicated-claim demo | golden-path outcomes | audit graph + determinism proof | pipeline + idempotency tests | audit-chain + idempotency evidence | metrics names; replay tests |
| **M5** | plain-language explanation demo | explanation UX | agent-non-authoritative boundary | `claims-agent` + plumbing reuse | agent logs PHI-clean | agent Cloud Run config |
| **M6** | full local end-to-end demo | all golden paths runnable | gateway-strangler runbook | compose/profiles + seed | gated-path (Kong) auth verified | `kong.yml` == cloud gateway |
| **M7** | platform narrative + docs | demo script + acceptance | end-to-end architecture proof | full test matrix green | full security evidence pack | Phase-2b deploy runbook + Terraform plan |
| **M8 (2b)** | live cloud demo | live acceptance | production-shaped topology | deployed services | secrets/TLS/scan in prod posture | live deploy + observability |

## 14. Engineering standards (platform-wide)

The standards every Phase 2 service inherits by default — the "right thing is the easy
thing." These are enforced via templates + CI gates (not just review), and map to the
normative requirements.

| Standard | What it means | Enforced by | Maps to |
|---|---|---|---|
| **API / contract-first** | Define & version the interface (OpenAPI / FHIR profiles) before building; no breaking change without a new version | contract tests in CI; schema review | R17.7 |
| **12-factor services** | Stateless, config/secrets from the environment, disposable, one build many envs → autoscale + local↔cloud by config | Cloud Run/compose parity; config lint | C1, R10 |
| **PHI-safe-by-default** | Privacy is the default path: encryption, least-privilege, **no identifiers in logs/traces** (log `decisionId`, not member id) | log scrubbing + CI check; secret scanning (gitleaks) | R14 |
| **Test + review gates** | No merge without passing tests, coverage threshold, and ≥1 peer approval | CI required checks; branch protection | R19 |
| **Observability by default** | Every service born instrumented — traces (one claim = one trace), metrics, correlation IDs; reliability as an **SLO** | OTel + Managed Prometheus templates | R15 |
| **ADRs (Architecture Decision Records)** | Significant/irreversible decisions recorded (context, options, choice, trade-offs); supersede, don't edit | ADR file per decision, reviewed like code | (this planning set already *is* ADRs: D1–D8, C1–C4, R17–R19) |

**Adoption approach (how, not just what):** co-author the standard with the senior
architects + change champions + outside input (a tailored "constitution"), gather feedback,
then enforce **incrementally** — new code and the code it touches — through **automated CI
gates first, peer review second.** Automation is what makes standards hold across 50+
engineers without heroics.

## 15. Delivery & PR strategy

One PR per milestone is the default (each independently reviewable, mergeable, and
revertable; each keeps Phase 1 green per R9), with three refinements:

| Milestone | PR? | Notes |
|---|---|---|
| **M0** | **No PR** | Read-only recon; findings go in the M1 PR description |
| **M1** | Yes | Payer-KB — includes commercial/ACA grounding (requirements R13) |
| **M2–M5** | Yes (one each) | M3 **splittable** (M3a scaffold+ACL, M3b rules+contract) if large |
| **M6** | Yes | Compose profiles + DB-less Kong + seed + golden paths |
| **M7** | Yes (thin) | e2e/contract matrix + Phase-1-only CI job + narrative |
| **M8 = Phase 2b** | Yes (2–3) | Live cloud: infra, gateway-strangler cutover, CI/CD |

Principles:
- **Tests ship *in* each milestone PR** (per R19) — M7 is the integration/e2e capstone, not
  "where testing happens."
- **Cloud artifacts ship *in* each service's PR** (Terraform/Cloud Run config + stub tests) —
  only the *live* deploy is deferred to Phase 2b.
- **Additive only**: new services under the `phase2` compose profile so merging to `main`
  never activates Phase 2 in the default path.
- Each PR description references its **milestone + the R/C items it satisfies**.
- **Sequential off `main`** (merge M2, branch M3 off updated `main`, …) for clean review;
  stacked PRs only when parallelism is worth the rebase cost.
- Never self-merge — PRs are prepared and kept current for review.

## 16. Future work

M0–M7 are done. This is the prioritised backlog, roughly in the order a new contributor should
pick it up. Each item says *why it matters* — a backlog without rationale becomes a wish list.

### Tier 1 — do these first

**1. Run the e2e suite in CI.** The single highest-value gap. CI has three jobs; none brings up
the stack, so `e2e/` only ever runs when a human remembers. A fail-closed change once broke
three e2e tests and reached `main` unnoticed. Needs a compose-based job (`docker compose
--profile phase2 up -d`, wait for health, `pytest e2e/`) with sensible timeouts. Touches CI
config, so agree the approach before building it.
*Why:* the suite that would have caught the last regression isn't watching.

**2. Non-regression decision snapshots (R19).** Store `ClaimResponse` snapshots under per-service
`testdata/`; assert catalogue or rule growth cannot silently change an existing decision. R19
requires this and it does not exist.
*Why:* a payer's worst failure is a decision that changes without anyone deciding to change it.

**3. Assert the audit graph end-to-end (R18.2).** `FhirArtifactBuilderTest` proves the graph is
*built* right; nothing proves it is *stored* right. Extend `e2e/` to read back the persisted
`Claim`/`ClaimResponse`/`Task`/`Provenance`/`RiskAssessment` and assert the links and the
decision id.
*Why:* the audit trail is the product for a regulator; it is currently untested where it lands.

**4. Implement R17.6's validation class.** `ClaimController` handles the system-error class (503
+ safe-retry) but has no `@Valid` and never emits an `OperationOutcome`; a malformed claim gets
Spring's default 400 body. Specified, not built.
*Why:* the error taxonomy is normative, and "specified but unimplemented" is the worst state for
a contract.

### Tier 2 — production-shaped work

**5. Circuit breaker on the triage call.** Today every request to a down triage service waits for
its own timeout, then pends. Under sustained failure that is slow *and* pends a flood of claims.
A breaker fails fast while preserving the fail-closed policy — it changes latency, not the
decision.
*Why:* correct but slow is still an outage.

**6. Exercise the C3 repository seam — Postgres-backed `PayerKb`.** The interface exists and
`FilePayerKb` implements it. Add a Postgres implementation plus the documented NoSQL-emulator
path. No rules-engine change should be needed; if one is, the seam is wrong and that is worth
knowing now.
*Why:* the seam's whole value is the claim that swapping is cheap. Untested, it's a hypothesis.

**7. Member → Patient resolution for real.** `Patient/member-{id}` is a demo affordance. Replace
it with a proper member index (or identifier search against a real system URI), and decide how a
legitimately new member with no clinical record differs from a data-integrity gap — today both
pend (see R17.5's accepted consequence).
*Why:* the current convention silently assumes a naming scheme no real payer has.

**8. NCPDP reject-code fidelity.** Map decisions to real reject codes (65 patient not covered, 70
product not covered, …) alongside the internal reason codes.
*Why:* a pharmacy system speaks NCPDP; internal codes don't reach the counter.

**9. `Task` lifecycle / prior-auth round trip.** PENDED and ROUTED currently terminate. Build the
human-in-the-loop return path: a reviewer resolves the `Task`, and the claim re-adjudicates
idempotently.
*Why:* PEND is a promise to come back. Nothing comes back yet.

### Tier 3 — scale and cloud

**10. M8 / Phase 2b — live cloud deploy.** `terraform apply`: Cloud Run + Cloud SQL/Neon + Secret
Manager + Artifact Registry; DB-less Kong live; emulator `ingress=internal`; OTel → Cloud Trace
and Managed Prometheus; gateway-strangler S1→S2. First real GCP spend — hence deliberately last.
*Why:* the parity path is built and stub-tested; this is cashing it in, not new construction.

**11. Load, performance, and failure-injection testing.** Nothing is measured. Cold starts are a
known Cloud Run risk for Spring Boot/HAPI (C1); `min-instances` is the documented mitigation and
is unverified.
*Why:* every scalability claim in §5 is currently a design argument, not a number.

**12. BigQuery decision-analytics plane (C4).** FHIR `Provenance` now; the analytics plane was
always deferred.
*Why:* "why did approvals drop 4% last month" is a query, not a FHIR search.

**13. Gateway profile coverage in CI.** Kong key-auth and rate limiting are verified by hand.
*Why:* the gateway is the security boundary; hand-verification doesn't survive contributors.

### Carried-over debt worth naming

- **Compose HAPI version drift** — `v7.2.0` in compose vs `8.8.0` referenced in docs.
- **Triage returns only its first match** — fine as a safety gate (R17.5); a full multi-reason
  clinical list needs a triage change, which would touch Phase 1 (R9 — think before doing it).
- **PHI in gateway logs** — Kong `file-log` records request URIs with identifiers; scrub or
  treat as restricted (R14). Applies to Phase 1 today.
- **`epic-emulator/` and `athena-emulator/`** are empty placeholders.
