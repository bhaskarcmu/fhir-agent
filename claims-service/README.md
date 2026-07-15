# claims-service — Claims Adjudication Modernisation Layer (Phase 2)

The modern **API façade** over the legacy RxClaim core. It runs the layered benefit/prior-auth
**rules engine** and the **Decision Contract**, reuses the triage service for clinical safety,
and calls the legacy core (rxclaim-emulator) through an **anti-corruption layer**. Consumers
hit only this service (fronted by Kong); the legacy core stays internal.

## What it does
`POST /claims/adjudicate` (JSON canonical claim) → deterministic `AdjudicationDecision`:
0. **Validate the claim** (R17.6). Malformed → `400` + `OperationOutcome`; nothing is
   adjudicated or persisted (see below).
1. Look up the formulary row `(planId, rxcui)` from the payer KB (C3 repository seam).
2. Clinical safety via triage (reused) → risk mapped per R17.5.
3. **Rules engine** (accumulate-then-resolve, R17): eligibility, formulary, prior-auth,
   step-therapy, quantity-limit, clinical safety → findings.
4. Resolve outcome by precedence **DENY > PEND > REVIEW > approved**, with deterministic
   `(severity, domain, ruleId)` ordering; winning-tier findings are the reasons, all findings
   are retained for the explanation.
5. If not a hard denial, call the legacy core via the **ACL** for authoritative pricing.

Outcomes: `APPROVED` / `DENIED` / `PENDED` / `ROUTED_FOR_REVIEW`.

## Intake contract (R17.6)

Three **disjoint** response classes. A *denial* is a decision about a valid claim and is
recorded; a *malformed request* is not a claim and leaves no trace.

| Class | Status | Body | Persisted? |
|---|---|---|---|
| Validation error | `400` | FHIR `OperationOutcome` (`application/fhir+json`) | **No** |
| Adjudication decision (incl. denials) | `200` | `AdjudicationDecision` | Yes — the artefact graph |
| System error (downstream unavailable) | `503` | retry-safe message | No — writes are atomic |

**Required fields.** Two rules set this list: anything a *decision depends on* is mandatory (a
missing value must never be read as a decision input), and string/number bounds mirror the
**legacy fixed-width record**, which right-pads and truncates — so an over-long `memberId` would
silently price a different member.

| Field | Constraint |
|---|---|
| `claimId` | required — the decision/idempotency key |
| `memberId` | required, ≤ 9 chars (legacy MBRID width) |
| `planId`, `rxcui` | required |
| `ndc` | required, ≤ 11 chars (legacy NDC width) |
| `quantity` | > 0, ≤ 99999 (legacy 5-digit field) |
| `daysSupply` | > 0, ≤ 999 (legacy 3-digit field) |
| `dateOfService` | required, ISO-8601 |
| `prescriberNpi` | required, exactly 10 digits |
| `coverageEffective`, `coverageTermination` | required — absence is a data gap, not a denial |

**Optional:** `drugName` (display only — no rule reads it); `priorAuthOnFile` and
`stepTherapyMet` default to `false` when absent, the conservative reading (pends or routes,
never approves).

`OperationOutcome` issues are sorted `(field, message)`, so the same bad request always yields
an identical response.

## Key pieces
- `acl/LegacyAdapter` — builds the 46-char legacy claim record and parses the 59-char response
  (the only class that knows the legacy wire format).
- `rules/RulesEngine` — the Decision Contract, deterministic and unit-tested.
- `kb/PayerKb` + `FilePayerKb` — the C3 seam (file-backed now; swap to Postgres/NoSQL later).
- `client/*` — transports to the legacy core and triage. **Triage fails closed** (see below);
  legacy failure leaves pricing absent. A circuit breaker on triage is future work — it changes
  latency, not the fail-closed policy.

## Clinical safety fails closed (R17.5 — normative)

`RiskLevel.UNKNOWN` means *"the safety check could not be completed"* — member unresolved,
triage down or erroring, or an unrecognised response. It is deliberately **distinct from
`LOW`** ("we checked and it is safe") and maps to **PEND**, never approve:

| Triage result | Finding | Outcome contribution |
|---|---|---|
| `HIGH` | `clinical-safety-high` | DENY |
| `MODERATE` | `clinical-safety-moderate` | REVIEW |
| `LOW` | none | — |
| **`UNKNOWN`** (check could not run) | **`clinical-safety-unavailable`** | **PEND** |

A hard DENY still outranks the PEND (precedence R17.3): a claim denied on eligibility or
formulary grounds needs no safety check to be denied.

Why this is a rule and not a preference: the failure is **silent**. A system that cannot see a
drug-allergy conflict reports no conflict, which is indistinguishable from a safe patient.
Treating "unavailable" as `LOW` approves claims on a check that never ran.

## Build & test
```bash
mvn -f claims-service/pom.xml test          # 52 tests (rules, ACL, KB, pipeline, intake + triage contracts)
```
Mostly pure JUnit (no Spring context, no DB) — hermetic and fast. The exception is
`ClaimIntakeContractTest`, which loads the web layer via `@WebMvcTest` because the intake
contract (Jackson binding, `@Valid`, the `OperationOutcome` advice) only exists there.

## Run locally
```bash
mvn -q -f claims-service/pom.xml -DskipTests package
java -Dpayer-kb.dir=/abs/path/to/data/payer-kb \
     -jar claims-service/target/claims-service-0.1.0.jar   # :8090
# The pipeline runs without triage/legacy up, but it does NOT ignore them: with triage down
# every claim PENDs on clinical-safety-unavailable (fail-closed, above). That is correct
# behaviour, not a broken environment — bring triage up for a meaningful local run.
```
`payer-kb.dir` must resolve to the repo's `data/payer-kb` (default `../data/payer-kb` works when
run from this module directory).

## FHIR artefacts & idempotency (M4)
On each adjudication the service persists an auditable **FHIR R4 artefact graph** to the
platform FHIR server as one **transaction bundle** (`fhir/FhirArtifactBuilder`): `Claim`,
`ClaimResponse` (`request` → Claim), `Task` (when routed), `Provenance` (`target` → all), and
`RiskAssessment` (on a clinical finding). One `decisionId` is stamped on every resource
(identifier + `meta.tag`), giving the R18.2 mandatory links.

Idempotency (R18): each entry is a conditional create (`ifNoneExist=_tag=…|decisionId`) and the
bundle is atomic, so a retry never duplicates or half-writes the graph; an intake check
(`existingDecision`) returns the prior decision instead of re-adjudicating. A FHIR outage
surfaces as **503** (retry-safe — nothing is half-persisted, R17.6). `fhir.base-url` configures
the server.

## Scope
Delivers the deterministic decisioning core, the persisted idempotent FHIR artefact graph,
member→FHIR-patient resolution, and the fail-closed clinical-safety gate. Wired into
compose/gateway with the real emulator + triage.

**Deferred:** a BigQuery audit plane (C4), a circuit breaker on triage, and the Postgres
implementation behind the C3 seam. See [`docs/phase2/plan.md` §16](../docs/phase2/plan.md#16-future-work).

## Cloud (design/stub — Phase 2b)
`Dockerfile` + `infra/main.tf` — a Cloud Run **stub** for the edge-facing façade (behind Kong),
the only caller of the internal emulator. **Stub means stub:** it is not referenced by any root
Terraform module, and nothing has been applied. See the
[cloud-delivery gap](../docs/phase2/plan.md#6-workstreams--milestones).
