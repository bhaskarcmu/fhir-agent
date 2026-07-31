# epic-emulator — Epic-flavored proxy in front of fhir-service (Phase 4)

> **Status: M1 built (skeleton + pass-through proxy).** M2 (auth emulation), M3 (extension
> handling), M4 (quirks), and M5 (acceptance case) are not started — see
> [`docs/phase4/README.md`](../docs/phase4/README.md) for the canonical Phase 4 status.
>
> This module was reserved as an empty placeholder back in Phase 2
> ([`docs/phase2/plan.md` §16](../docs/phase2/plan.md#16-future-work), deviation
> [D2](../docs/phase2/requirements.md#deviations-from-the-prd)) alongside a sibling
> [`athena-emulator`](../athena-emulator/README.md). That sibling **remains a placeholder** —
> Phase 4 builds out only the Epic half. The original two-emulator "portability isn't provable
> with just one edge" framing (see `athena-emulator/README.md`) is not fulfilled by Phase 4 alone;
> whether `athena-emulator` is ever built is a separate, later decision.

## What it does

Sits in front of [`fhir-service`](../fhir-service/README.md) and reproduces enough of Epic's real,
publicly documented integration behavior — its SMART Backend Services auth flow, its custom
extensions on Medication/AllergyIntolerance, and three named proprietary API quirks — that the
rest of the platform can be developed and tested against Epic-like behavior without a live Epic
connection. Full rationale: [`docs/phase4/prd.md`](../docs/phase4/prd.md); architecture:
[`docs/phase4/design.md`](../docs/phase4/design.md).

**M1 scope (this milestone):** a pass-through core only. Every request is forwarded to
`fhir-service` unchanged and its response returned unchanged — no auth gate, no extensions, no
quirks yet. Those land in M2–M4 as interceptors layered around the same entry point.

## How the proxy works

- `fhir.base-url` (default `http://localhost:8080`) is the **root** of `fhir-service` — not
  including `/fhir`. The incoming request's own path (e.g. `/fhir/Patient/123`) is forwarded
  verbatim, so pointing a consumer's FHIR base URL at `http://localhost:8092/fhir` instead of
  `http://localhost:8080/fhir` works with no path rewriting.
- `proxy/FhirProxyClient` is the one class that knows how to reach `fhir-service` (same
  anti-corruption-layer shape as `claims-service`'s `LegacyAdapter`/`HttpLegacyClient`). It
  forwards method, headers (minus hop-by-hop and anything the JDK `HttpClient` itself restricts),
  and body byte-for-byte, and returns the upstream status/headers/body unmodified.
- `proxy/FhirProxyController` claims every other path (`/**`); Spring Boot's actuator handler
  mapping is registered ahead of it, so `/actuator/health` stays served locally rather than being
  forwarded upstream.

## API

Whatever `fhir-service` exposes, unchanged — `GET`/`POST`/`PUT`/`DELETE`/`PATCH`/`HEAD` on any
path. `GET /actuator/health` for probes. Runs on **:8092**.

## Build & test

```bash
mvn -f epic-emulator/pom.xml test
```

3 tests (no DB, no ambient-datasource gotcha to worry about — this module has no datasource at
all): pass-through `GET`, pass-through `POST` with body/content-type, and a check that
`/actuator/health` is handled locally rather than proxied. The test stands up a stub
"fhir-service" with the JDK's own `HttpServer` (same dependency-free pattern as `claims-service`'s
`HttpTriageClientTest`) rather than pulling in a mocking library for one proxy target.

## Run locally

```bash
mvn -q -f epic-emulator/pom.xml -DskipTests package
java -Dfhir.base-url=http://localhost:8080 -jar epic-emulator/target/epic-emulator-0.1.0.jar
# fhir-service must be running at :8080 separately — see fhir-service/README.md.
```

## Non-goals (this module, this phase)

- Not a fork of `fhir-service` — generic R4 behavior stays there; this module only adds
  Epic-specific deviations on top.
- Not a claims/adjudication core — that's `rxclaim-emulator`, a deliberately different category
  (non-FHIR, transactional legacy).
- Not absorbing `triage-service` or `claims-service` decision logic — see
  [`docs/phase4/decisions.md` E6](../docs/phase4/decisions.md).
- Not a certified or complete Epic implementation — an emulator for development and testing, never
  a conformance claim.
