# epic-emulator — Epic-flavored proxy in front of fhir-service (Phase 4)

> **Status: M1 + M2 + M3 built (pass-through proxy + auth emulation + extension handling).** M4
> (quirks) and M5 (acceptance case) are not started — see
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

**M1 scope:** a pass-through core only. Every request is forwarded to `fhir-service` unchanged and
its response returned unchanged.

**M2 scope:** every proxied call requires a bearer token, obtained via a simulated SMART Backend
Services JWT client-assertion flow.

**M3 scope (this milestone):** `MedicationRequest`/`AllergyIntolerance` reads (bare or inside a
search `Bundle`) get a placeholder Epic-style extension backfilled if missing. Writes are
untouched. The three quirks (M4) are not built yet.

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

## How auth emulation works (M2)

Simulates Epic's SMART App Launch **Backend Services** flow (JWT client-assertion, RFC 7523) —
system-to-system auth with no user/launch context, distinct from the interactive/patient-facing
SMART launch flow:

1. **Register a client** (dev-simple, no approval workflow — decision E8): generate an RSA key
   pair, keep the private key, and add the **public** JWK under `epic.auth.clients` in
   `application.yml`.
2. **Request a token**: `POST /oauth2/token` with `grant_type=client_credentials`,
   `client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer`, and
   `client_assertion` = a JWT signed **RS384** with the private key (`iss`/`sub` = your client id,
   `aud` = this service's `epic.auth.token-endpoint`, plus `jti`/`exp`).
3. `auth/ClientAssertionValidator` checks the signature against the registered public key, that
   `iss`/`sub` match and are known, `aud` matches, `exp` hasn't passed, and `jti` hasn't been
   replayed. On success, `auth/AccessTokenStore` issues a short-lived opaque bearer token.
4. **Use the token**: every other request needs `Authorization: Bearer <token>` —
   `auth/BearerAuthFilter` rejects anything missing/invalid/expired with a plain `401` *before* it
   reaches the proxy. `/oauth2/token` and `/actuator/**` are exempt.

**Known simplifications:** RS384 only (the spec also allows ES384/EC keys — not implemented, a
documented gap, not a silent one — decision E11); the 401 body is plain OAuth2 JSON today, not yet
Epic's `OperationOutcome` shape (that upgrade is M4/FR6, deliberately sequenced there).

## How extension handling works (M3)

`extensions/ExtensionBackfillInterceptor` runs on every proxied `GET` response:

- If the response is (or contains, inside a search `Bundle`) a `MedicationRequest` or
  `AllergyIntolerance` resource **missing** its Epic-style extension, it adds one before returning
  to the caller. This is what makes already-seeded data look Epic-flavored with no new fixture
  pipeline — the backfill is synthetic and read-time only, never written back to `fhir-service`.
- If the extension is **already present** (e.g., a client wrote it earlier), it's left alone —
  never duplicated.
- Any other resource type is returned byte-for-byte untouched, including inside a Bundle where
  some entries are in scope and others aren't.
- **Writes are untouched by this class entirely.** `fhir-service` already stores arbitrary
  extensions, so a client that writes one gets it back unchanged on the next read with no special
  handling needed.

**Placeholder, not real Epic data (decision E12, design.md §5):** the extension URLs
(`.../medication-therapy-class`, `.../allergy-source-system`, both under a same-repo
`epic-emulator.local` placeholder domain) and the synthetic backfill value are structurally
representative stand-ins, not a claim about Epic's real extensions — Epic's own specifics remain
unverified (decision E10). Also corrects the PRD's generic "Medication" wording: the reference
workflow actually reads `MedicationRequest`, so that's what M3 targets.

## API

Whatever `fhir-service` exposes, gated behind a bearer token —
`GET`/`POST`/`PUT`/`DELETE`/`PATCH`/`HEAD` on any path. `POST /oauth2/token` to get a token.
`GET /actuator/health` for probes (no token needed). Runs on **:8092**.

## Build & test

```bash
mvn -f epic-emulator/pom.xml test
```

15 tests, no DB (this module has no datasource at all):

- `FhirProxyIntegrationTest` (3) — pass-through `GET`/`POST` (fetching a real token first, since
  M2 gates everything), and actuator staying local **and** token-free.
- `AuthFlowIntegrationTest` (6) — full client-assertion flow end to end (token issued, then used
  for a real gated proxied call against a stub upstream); no-header, garbage-token, expired-
  assertion, wrong-signing-key, and unknown-client rejections, each asserted at the specific layer
  that should catch it (the gate vs. the token endpoint).
- `ExtensionBackfillIntegrationTest` (6) — backfill on a bare `MedicationRequest` and a bare
  `AllergyIntolerance`; no duplication when already present; an out-of-scope resource type
  (`Patient`) returned byte-for-byte unchanged; a search `Bundle` backfilling only its in-scope
  entries; a write round-tripping its extension unchanged.

All three classes stand up a stub "fhir-service" with the JDK's own `HttpServer` (same
dependency-free pattern as `claims-service`'s `HttpTriageClientTest`) rather than pulling in a
mocking library.

## Run locally

```bash
mvn -q -f epic-emulator/pom.xml -DskipTests package
java -Dfhir.base-url=http://localhost:8080 -jar epic-emulator/target/epic-emulator-0.1.0.jar
# fhir-service must be running at :8080 separately — see fhir-service/README.md.
# You'll also need a registered client (epic.auth.clients) to get past the auth gate — see above.
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
