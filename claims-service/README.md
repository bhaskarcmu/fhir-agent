# claims-service — Claims Adjudication Modernisation Layer (Phase 2, M3)

The modern **API façade** over the legacy RxClaim core. It runs the layered benefit/prior-auth
**rules engine** and the **Decision Contract**, reuses the triage service for clinical safety,
and calls the legacy core (rxclaim-emulator) through an **anti-corruption layer**. Consumers
hit only this service (fronted by Kong); the legacy core stays internal.

## What it does
`POST /claims/adjudicate` (JSON canonical claim) → deterministic `AdjudicationDecision`:
1. Look up the formulary row `(planId, rxcui)` from the payer KB (C3 repository seam).
2. Clinical safety via triage (reused) → risk mapped per R17.5.
3. **Rules engine** (accumulate-then-resolve, R17): eligibility, formulary, prior-auth,
   step-therapy, quantity-limit, clinical safety → findings.
4. Resolve outcome by precedence **DENY > PEND > REVIEW > approved**, with deterministic
   `(severity, domain, ruleId)` ordering; winning-tier findings are the reasons, all findings
   are retained for the explanation.
5. If not a hard denial, call the legacy core via the **ACL** for authoritative pricing.

Outcomes: `APPROVED` / `DENIED` / `PENDED` / `ROUTED_FOR_REVIEW`.

## Key pieces
- `acl/LegacyAdapter` — builds the 46-char legacy claim record and parses the 59-char response
  (the only class that knows the legacy wire format).
- `rules/RulesEngine` — the Decision Contract, deterministic and unit-tested.
- `kb/PayerKb` + `FilePayerKb` — the C3 seam (file-backed now; swap to Postgres/NoSQL later).
- `client/*` — resilient transports to the legacy core and triage (triage failure degrades to
  LOW; legacy failure leaves pricing absent — a production build adds a circuit breaker, §5).

## Build & test
```bash
mvn -f claims-service/pom.xml test          # 20 unit tests (rules, ACL, KB, pipeline)
```
Tests are pure JUnit (no Spring context, no DB) — hermetic and fast.

## Run locally
```bash
mvn -q -f claims-service/pom.xml -DskipTests package
java -Dpayer-kb.dir=/abs/path/to/data/payer-kb \
     -jar claims-service/target/claims-service-0.1.0.jar   # :8090
# triage/legacy optional locally — the pipeline degrades gracefully if they're down.
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
M3+M4 deliver the deterministic decisioning core **and** the persisted, idempotent FHIR
artefact graph. **Deferred:** member→FHIR-patient resolution for triage, and a BigQuery audit
plane (C4). **M6** wires it into compose/gateway with the real emulator + triage.

## Cloud (design/stub — Phase 2b)
`Dockerfile` + `infra/main.tf` Cloud Run stub — edge-facing (behind Kong), the only caller of
the internal emulator.
