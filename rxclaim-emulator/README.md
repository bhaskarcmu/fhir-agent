# rxclaim-emulator — simulated legacy IBM i / RxClaim adjudication core (Phase 2, M2)

A Spring Boot service that **stands in for the legacy RxClaim engine** (historically IBM i,
Db2 for i, RPG/CL). In the modernization strangler snapshot it owns the **member
system-of-record, drug pricing, and accumulators**; the modern `claims-service` wraps it
behind a façade + anti-corruption layer (M3) and **consumers never call it directly**.

It deliberately speaks a **legacy contract**: fixed-width (DDS-style) records over a thin
REST façade, backed by DB2/SQL400-style tables. This is what makes the anti-corruption layer
(M3) real translation work rather than cosmetic.

## What it does (`ADJRXCLM`)
`core/RxClaimCore.adjRxClm()` models an RPG/CL program named **ADJRXCLM** ("Adjudicate Rx
Claim"):
1. **Member eligibility** from `MBRMST` (coverage active on date of service) — else NCPDP **65**.
2. **Product pricing** from `DRGMST` (AWP × qty + dispensing fee) — unknown NDC → NCPDP **70**.
3. **Pricing**: 20% legacy coinsurance → patient pay / plan pay.
4. **Accumulators**: updates running out-of-pocket in `ACCMST`.
5. Returns a legacy response record (status + reject code + amounts + auth number).

Scope note: formulary, prior-auth, and clinical-safety rules are **NOT** here — those are the
modern layer's job (claims-service / triage). This core rejects only for member eligibility
and unknown product, matching the "money + system-of-record stays legacy" snapshot.

## Legacy data shapes
- **Tables** (`resources/schema.sql`, DB2/SQL400-style names): `MBRMST` (member master),
  `DRGMST` (drug master: AWP + dispensing fee), `ACCMST` (accumulators). H2 locally; Cloud
  SQL/Neon (Db2-for-i stand-in) in cloud.
- **Fixed-width records** (`legacy/`): `LegacyClaimRecord` (46 chars) in, `LegacyResponseRecord`
  (59 chars) out, with implied-decimal packed amounts and CCYYMMDD dates. Field layouts are
  documented as DDS record formats in those classes.

## API (internal only)
`POST /rxclaim/adjudicate` · `Content-Type: text/plain` · body = a 46-char claim record;
returns a 59-char response record. `GET /actuator/health` for probes. Runs on **:8091**.

Example claim record (member 000000001, lisinopril `51655-999`, qty 30, 30 days, DOS 2026-06-01):
```
000000001 51655-999  0003003020260601 1234567890
# (spaces shown for the padded NDC field; total length 46)
```

## Build & test
```bash
mvn -f rxclaim-emulator/pom.xml test
```
Tests pin H2 via test properties, so they pass even when the shell exports
`SPRING_DATASOURCE_URL` / `NEON_*` (the same ambient-DB quirk noted for fhir-service in
CLAUDE.md). To run locally against H2, override the datasource so the ambient var doesn't
redirect it:
```bash
mvn -f rxclaim-emulator/pom.xml -DskipTests package
java -Dspring.datasource.url='jdbc:h2:mem:rxclaim;DB_CLOSE_DELAY=-1' \
     -Dspring.datasource.driver-class-name=org.h2.Driver \
     -Dspring.datasource.username=sa -Dspring.datasource.password= \
     -jar rxclaim-emulator/target/rxclaim-emulator-0.1.0.jar
```

## Cloud (design/stub — Phase 2b)
`infra/main.tf` is a Cloud Run stub with **`ingress=INTERNAL_ONLY`** + an IAM invoker binding
limited to the claims-service account — the Cloud Run equivalent of ClusterIP + NetworkPolicy
(plan C1/R11). Not applied until Phase 2b.
