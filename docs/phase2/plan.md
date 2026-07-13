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
→ anti-corruption translation → decision (approve/reject/pend/route) → persist
FHIR `Claim`/`ClaimResponse`/`Task`/`Provenance`/`RiskAssessment`.

### Reuse boundary (deviation D1)
Clinical safety is delegated to the existing triage HTTP contract
(`{patient_id, medication_id?}` → FHIR `RiskAssessment`). No triage code changes;
Phase 1 stays independent.

## 3. Gateway & local/cloud parity

### Placement changes vs Phase 1
- **Today:** Kong is cloud-only and fronts **only** `/fhir`. Local dev bypasses Kong
  entirely (`FHIR_GATEWAY_URL` defaults direct-to-container).
- **Phase 2 (cloud, later):** add `/claims` and `/triage` routes; provision a
  `claims-service` Kong consumer; the emulator gets **no route** + a NetworkPolicy
  restricting it to `claims-service`. These go in **separate** config files so the
  Phase 1 cloud deploy path (`deploy.sh`, existing `gateway/kong/*`) is untouched.
- **Phase 2 (local):** add an **opt-in DB-less Kong** to compose.

### The two local modes (parity switch)
```bash
docker compose up -d                          # DEFAULT: Phase 1 only, no Kong, no keys
docker compose --profile phase2 up -d         # + claims-service, rxclaim-emulator, claims-agent (direct calls)
docker compose --profile phase2 --profile gateway up -d   # + edge Kong fronting everything (parity test)
```
- Default and `--profile phase2` inner loops are **Kong-less** — zero setup.
- `--profile gateway` runs **DB-less Kong** (declarative `kong.yml`, in-memory, a
  committed **local-only** dev key). **No Helm, no Neon, no key provisioning.**
- Switching is config-only via env vars: `FHIR_GATEWAY_URL`, `TRIAGE_SERVICE_URL`,
  and a new `CLAIMS_GATEWAY_URL` (default direct; point at Kong for gated mode).

### Known parity friction (tracked, not hidden)
Kong is configured two ways — **KIC CRDs** (cloud) and a **declarative `kong.yml`**
(local DB-less). They express the same 3 routes + 4 plugins in different dialects.
Mitigation: keep both (small) and add a test asserting they define the same
routes/plugins. Single source of truth via `deck` is a later option.

### Gotchas
- Local Kong **admin** must not use `:8001` (taken by `triage`); map to `:8081`.
  Proxy stays `:8000` to match the cloud port-forward convention.

## 4. Isolation strategy (enforcing R9)

The dependency arrow points **Phase 2 → Phase 1 only**.

| Shared surface | How Phase 1 stays independent |
|---|---|
| `docker-compose.yml` | New services carry `profiles: [phase2]` / `[gateway]`; Phase 1 services get no profile → plain `up` is byte-for-byte today's. Verify with `docker compose config`. |
| Cloud deploy | `deploy.sh` and `gateway/kong/*` untouched. Phase 2 routes/manifests live in new files (`gateway/kong/phase2/`, a future `deploy-phase2.sh`). |
| Tests | Phase 2 tests in new packages; CI keeps a "Phase 1 only" job. `pytest.ini` extended, never narrowed. |
| Seeding | New `data/scripts/seed_claims_demo.py` + `data/payer-kb/`; `seed_demo.py` untouched. Use `FHIR_GATEWAY_URL` (consistency with seed_demo/agent). |
| `client/clinical` | Additive methods only (e.g. `get_coverage`) following the `_parse_*` pattern; no existing signature changes. Java services use their own FHIR access. |
| `mcp-agent` | Untouched — claims explanation is a **separate** `claims-agent` (D3). |
| `.ona/automations.yaml` | Append new Python pkgs to the `installDependencies` `pip install -e` list; add build tasks with `dependsOn: installDependencies`. Don't replace. |

**Safety net:** tag `phase1-v1` (pushed) = known-good, independently deployable snapshot.

## 5. k8s pattern for new services (deferred to Phase 2 cloud)
Mirror `fhir-service/k8s/` per new Java service: `namespace` (or reuse a namespace
labelled `app.kubernetes.io/managed-by: kong` for Kong routability), `configmap`
(non-secret env), `secret.yaml.example` (imperative create, never commit real),
`service` (ClusterIP, name matches Kong backend + pod selector), `deployment`
(`IMAGE_PLACEHOLDER` convention, actuator health probes). New services won't need
HAPI's 180s startup delay — tune probes accordingly. Emulator = ClusterIP + a
NetworkPolicy allowing only `claims-service`.

## 6. Workstreams / milestones

| # | Milestone | Deliverable | Depends on |
|---|---|---|---|
| **M0** | Recon (read-only) | Run PRD §11.3 FHIR counts against live server; document existing data so we seed only the gap. Note compose/README HAPI version drift (`v7.2.0` vs `8.8.0`) and `FHIR_GATEWAY_URL` vs `FHIR_BASE_URL` for later cleanup. | — |
| **M1** | Payer knowledge base | Curated `data/payer-kb/` (formulary, PA rules, 4 plans, RxNorm/ICD subset) as JSON/YAML. Data only. | M0 |
| **M2** | `rxclaim-emulator` | Spring Boot legacy core: DDS-style records, DB2/SQL400 tables, `ADJRXCLM` function, legacy response. | M1 |
| **M3** | `claims-service` core | Spring Boot façade + anti-corruption layer + layered rules engine; calls emulator + triage; writes FHIR. Da Vinci-aware naming. | M1, M2 |
| **M4** | Pipeline & artefacts | Wire the pipeline; emit `Claim`/`ClaimResponse`/`Task`/`Provenance`/`RiskAssessment`/`CoverageEligibilityResponse`. | M3 |
| **M5** | `claims-agent` | Separate explanation agent over the claims façade; shares only non-clinical plumbing with `mcp-agent`. | M4 |
| **M6** | Local wiring & demo | Compose services under `phase2` profile; DB-less Kong under `gateway` profile; `seed_claims_demo.py`; 4–5 golden paths. | M4, M5 |
| **M7** | Tests & narrative | Per-service tests; Phase-1-only CI job; README/section reinforcing the interview narrative. | M6 |
| **M8** | *(later)* Phase 2 cloud | k8s manifests per service, `deploy-phase2.sh`, Kong `/claims` + `/triage` routes, emulator NetworkPolicy. | M7 |

Each new service ships **both** a compose entry and (at M8) a k8s manifest set, so
"local ↔ cloud" is structural.

## 7. Directory layout (proposed, additive)
```
claims-service/        # NEW — Java/Spring Boot façade + rules + ACL
rxclaim-emulator/      # NEW — Java/Spring Boot legacy core (sibling to epic-/athena-emulator, NOT inside them)
claims-agent/          # NEW — Python explanation agent
data/payer-kb/         # NEW — curated formulary/PA/plan fixtures
data/scripts/seed_claims_demo.py   # NEW
gateway/kong/phase2/   # NEW — Phase 2 routes/plugins (cloud), applied separately
gateway/kong/kong.yml  # NEW — DB-less declarative config for the local gateway profile
docs/phase2/           # THIS planning set
```

## 8. Risks & open questions
- **Config-dialect drift** (KIC vs `kong.yml`) — mitigated by a parity test (§3).
- **Compose HAPI version drift** — reconcile in M0 before building around it.
- **`client/clinical` additions** — keep strictly additive; Java services should not
  depend on the Python client.
- **PRD open items** (COB, CPT licensing, NCPDP SCRIPT depth, naming) — tracked in
  `requirements.md`; none block M0–M7.
- **Scope creep into full PAS/terminology** — explicitly out of scope (D6, D7).

## 9. Definition of done (Phase 2, local)
- `docker compose --profile phase2 up` + `seed_claims_demo.py` → the 4 core golden
  paths produce correct `ClaimResponse` + explanation, end to end.
- `--profile gateway` variant passes the same flow through Kong with a key.
- `docker compose up` (no profiles) + all Phase 1 tests + `deploy.sh` behave exactly
  as at `phase1-v1`.
