# Phase 4 Design — Epic Emulator

**Status:** DRAFT — no milestones started; see [`README.md`](./README.md) for the canonical
status statement. Companion to [`prd.md`](./prd.md). Open questions are resolved in §14 using
best judgement, same convention as Phase 2/3.
**Terminology:** internal work is tracked as milestones (M1, M2, ...) — never "Phase 4.x". A
future **Phase 4b** would name a live-cloud-deployment phase, mirroring Phase 2b/3b, if one is
ever needed — nothing in Phase 4 requires it (see §11).

---

## 1. Target architecture

```
 ┌──────────────────────────────────┐
 │ mcp-agent / triage-service          │  EXISTING, unmodified consumers.
 │ (FHIR base URL is env-configured)     │  Re-point the FHIR base URL at
 └───────────────┬──────────────────┘  epic-emulator to exercise Epic-like
                 │                      behavior (PRD UC1); default config
                 │ HTTPS, bearer token   is unchanged (still points at
                 │ (simulated SMART       fhir-service directly).
                 │  Backend Services)
                 ▼
 ┌────────────────────────────────────────────────┐
 │  epic-emulator (Spring Boot, NEW)                  │  one process, one Maven
 │                                                       │  build, own top-level dir
 │  ┌───────────┐  ┌────────────────┐  ┌────────────┐  │
 │  │ auth filter│  │ extension        │  │ quirk        │  │  three interceptors,
 │  │ (JWT client │  │ interceptor        │  │ interceptors   │  │  direct method calls
 │  │ assertion → │  │ (Medication/         │  │ (pagination,     │  │  only — no network
 │  │ bearer token)│  │ AllergyIntolerance)    │  │ required params,  │  │  hop between them
 │  │             │  │                          │  │ error shape)         │  │  (PRD FR7)
 │  └───────────┘  └────────────────┘  └────────────┘  │
 │                    proxy/pass-through core               │
 └───────────────┬────────────────────────────────┘
                 │ HTTP — plain FHIR R4 requests, unchanged
                 ▼
 ┌──────────────────────────────────┐
 │ fhir-service (HAPI JPA, unmodified) │  single source of truth;
 │ existing seeded Synthea data          │  no new fixtures (PRD G4)
 └──────────────────────────────────┘
```

**Where this sits relative to the existing platform:** `epic-emulator` joins the internal,
east-west plane — same posture as `rxclaim-emulator` (internal-only, never on the Kong edge). It
is a new hop **in front of** `fhir-service`, not a replacement for it; every other service's
default wiring is unchanged (PRD non-goal: no absorbed logic from `triage-service`/
`claims-service`, and no changes to either).

**Why a proxy, not a standalone service with its own store** (recap of PRD §9): `fhir-service`'s
already-seeded data stays the single source of truth, so no second fixture pipeline has to be
built or kept in sync. Accepted tradeoff: exercising `epic-emulator` for real requires
`fhir-service` running too.

## 2. Package layout (new)

```
epic-emulator/
  src/main/java/.../auth/        SMART Backend Services token endpoint + bearer-token filter
  src/main/java/.../extensions/  Medication/AllergyIntolerance extension backfill + validation
  src/main/java/.../quirks/      pagination, required-param, error-shape interceptors
  src/main/java/.../proxy/       the one class that knows fhir-service's base URL and forwards
                                  requests/responses (the anti-corruption-layer precedent from
                                  claims-service's LegacyAdapter, applied here)
  src/test/java/...
  Dockerfile                     single local-run image (PRD non-goal: nothing beyond this)
  pom.xml                        own Maven build, Java 21 / Spring Boot — same toolchain as
                                  fhir-service and rxclaim-emulator
```

One Maven module, matching the monolith-first framing in the PRD: the four packages above talk
to each other via direct method/field access, not internal HTTP calls or shared DTOs shaped like
a future network contract (PRD §7/§8).

## 3. The three capability areas

### 3.1 Auth emulation

Owns: a token endpoint implementing the SMART App Launch Backend Services flow, and a servlet
filter that gates every proxied FHIR call behind a valid bearer token. Nothing downstream
(extension handling, quirks, the proxy core) needs to know how the token was obtained — they only
see "request has/hasn't got a valid token," which is exactly the kind of shared-vs-separate
coupling question the PRD's G6 note wants surfaced in practice (does the extension/quirk work
ever need auth *context*, not just a yes/no gate?).

### 3.2 Extension handling

Owns: injecting Epic-specific extensions into Medication/AllergyIntolerance responses and
accepting them on writes. Deliberately **read-time backfill, not a data migration** — see §5.

### 3.3 Quirk simulation

Owns: the three named behavioral deviations from base R4 (§6). Each is implemented as its own
interceptor so a request can be affected by zero, one, or more of them without the others knowing.

## 4. Auth flow — concrete contract

1. **Registration (dev-simple, not a real vendor process).** A test client's public key (JWK) is
   registered with `epic-emulator` via a config file or in-memory store at startup — no UI, no
   approval workflow. This mirrors the *shape* of Epic's real backend-services client
   registration (a client presents a public key up front) without the real-world app-registration
   overhead, consistent with the PRD's "keep developer access simple" instruction.
2. **Token request.** Client `POST`s to `epic-emulator`'s token endpoint with
   `client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer` and a JWT client
   assertion signed with the private key matching its registered JWK.
3. **Validation.** `epic-emulator` validates the JWT signature against the registered public key
   and issues a short-lived bearer access token (JWT or opaque, backed by an in-memory store).
4. **Gated calls.** Every subsequent proxied FHIR request requires `Authorization: Bearer <token>`.
   Missing/invalid/expired → `401` with the Epic-shaped `OperationOutcome` from §6/quirk C.

All keys involved are dummy, generated for local dev use only, and clearly marked non-production
in logs and config (PRD FR8) — never handled or logged as if they were real secrets.

## 5. Extension handling — concrete approach

**Correction found while building M3:** the PRD says "Medication" generically. Checked what the
reference workflow (`triage-service` / `client/clinical`) actually reads, rather than assuming —
it queries **`MedicationRequest`** (`GET /MedicationRequest?patient=...&status=active`), never the
`Medication` catalog resource. M3 targets `MedicationRequest` + `AllergyIntolerance` concretely;
"Medication" in the PRD's higher-level language should be read as this resource, per decision E12.

**Write path:** unchanged pass-through. A stock HAPI R4 server (`fhir-service`) accepts arbitrary,
unrecognized extensions on a resource by default — nothing needs to strip or specially handle
them. So a client that writes a `MedicationRequest`/`AllergyIntolerance` resource with Epic-style
extensions through `epic-emulator` just has those extensions stored by `fhir-service` as-is, and
they round-trip naturally on the next read (PRD FR3, "round-trip correctly on write").

**Read path:** the only active piece. When `epic-emulator` proxies a `MedicationRequest` or
`AllergyIntolerance` read/search — bare resource **or** inside a search-result `Bundle` — and the
returned resource does **not** already carry the expected Epic extension, the extension
interceptor backfills a default one before returning it to the caller. This is what makes the
*already-seeded* Synthea data (which has no Epic extensions) look Epic-flavored without any new
fixture pipeline (PRD G4) — the backfill is synthetic and read-time only, never persisted back to
`fhir-service`. Idempotent: a resource that already carries the extension (e.g., one a client just
wrote) is left alone, never duplicated.

**Which extensions, concretely:** one placeholder extension per resource type, clearly namespaced
under a same-repo placeholder domain — **not** a claim about real Epic extension URLs, same
honesty posture as §6's quirk placeholders and decision E10 (Epic's own specifics remain
unverified):

| Resource | Extension URL (placeholder) | Value |
|---|---|---|
| `MedicationRequest` | `http://epic-emulator.local/fhir/extensions/medication-therapy-class` | `valueString: "synthetic-epic-emulator-backfill"` |
| `AllergyIntolerance` | `http://epic-emulator.local/fhir/extensions/allergy-source-system` | `valueString: "synthetic-epic-emulator-backfill"` |

The value is deliberately a synthetic marker, not invented clinical content — M3's job is proving
the *backfill-and-round-trip mechanism* works, not guessing what real Epic data would say.

## 6. Quirks — concrete pinned choices (starting design, pending validation)

These are working design choices, not verified facts about real Epic behavior — each is flagged
for confirmation against the pinned Epic documentation version (§7) during M2–M4, the same way
Phase 3 distinguished assumed vs. measured values rather than asserting a guess as fact.

| Quirk | Where it applies | Design choice (to validate) |
|---|---|---|
| **A — Pagination/`_count`** | A search on the resource type exercised by the acceptance scenario (Medication/AllergyIntolerance) | Cap effective `_count` at a fixed maximum regardless of what the caller requests; force the caller to follow `Bundle.link[relation=next].url` verbatim (an opaque, emulator-issued token) rather than construct its own offset. |
| **B — Required search-parameter combination** | `MedicationRequest` search | Require `patient` **and** `status` together; a request with `patient` alone — which `fhir-service`/base R4 would happily answer — is rejected with `400` even though nothing downstream actually needed the stricter rule. |
| **C — `OperationOutcome` error shape** | Every rejection `epic-emulator` itself generates (auth failures, quirk B, malformed extension writes) | Add a custom coding to `issue[].details.coding` under a clearly-labeled placeholder system (e.g. `http://epic-emulator.local/fhir/error-codes` — **not** a real Epic URI, a same-repo placeholder) plus a short, Epic-style verbose `diagnostics` string. |

**Explicit gap:** the exact real values (true pagination cap, the true required-parameter set for
whichever resource Epic actually documents this on, the true error-coding system/codes) must be
confirmed against the pinned Epic documentation before any of the above is described as
"conformant" rather than "structurally representative." Until §7 is done, treat this table as a
placeholder that is *right in shape*, not yet verified in value.

## 7. Authoritative documentation — the one open action item

Epic's documented API behavior (search-parameter support, extensions, error conventions) varies by
the Epic software version a given health system runs. Phase 4 targets **one fixed version** of
Epic's public "Epic on FHIR" documentation as its correctness reference — but that version has not
been picked yet, because it requires the actual developer-registration step the PRD's access
assumption is about (§6/§9 of `prd.md`).

**First concrete task of M2:** register for Epic's free developer access, record here which
documentation version/date was consulted, and update §6's table from "starting design" to
"confirmed against \<version\>." If registration turns out not to be as simple as assumed, Phase 4
still stands on whatever public documentation is reachable without registration — the PRD does
not make live sandbox access a build dependency.

**What M2 actually found (real attempt, not a guess):** `fhir.epic.com/Documentation?docId=oauth2`
is genuinely public — no login wall — and shows a "Last updated: October 31, 2025" marker, with a
menu entry for "Epic as a Backend OAuth 2.0 Client." The specific technical content of that
section (exact JWT claim requirements, scope-naming convention, token lifetime, rate limits)
did **not** come through a plain page fetch — it's rendered behind the site's own interactive
navigation, not retrievable as static content. **No account registration was attempted** (that's
an inherently human step — email verification, accepting terms — not something this build could
do on its own). So: the site's existence and general shape is confirmed real; Epic's own specific
parameter values remain unverified. M2's auth flow is instead built directly against the
**base SMART Backend Services specification** (HL7/SMART Health IT, itself fully public and
normative — RFC 7523 JWT-bearer client assertion, `client_credentials` grant, RS384/ES384-only
signing) since that's the standard Epic's own flow is documented to follow. This is a legitimate,
citable public source in its own right, not a stand-in for the Epic-specific gap — see decision
E10 in `decisions.md` for the exact status split.

## 8. Integration with the existing platform

- No code changes to `fhir-service`, `triage-service`, `claims-service`, or `mcp-agent`.
- The PRD's acceptance case (FR9) is wired by overriding the FHIR base-URL configuration those
  services already read from (env var/system property), pointed at `epic-emulator`'s port instead
  of `fhir-service`'s, for a single test run. This is a local override, not a new default.
- No new Kong route, no compose profile required to hit the Phase 4 success bar — an opt-in
  compose profile (mirroring Phase 2's pattern) is a reasonable follow-on but not required here.

## 9. Patterns applied

- **Anti-corruption layer / façade** — same shape as `claims-service`'s `LegacyAdapter`: one class
  (`proxy/`) owns all knowledge of how to talk to the thing behind it (`fhir-service`), so nothing
  else needs to.
- **Internal-only emulator of a real system** — same shape as `rxclaim-emulator`: a same-repo
  precedent for a single-process Spring Boot service that convincingly reproduces a real system's
  non-standard contract, never called directly by external consumers.
- **Interceptor pipeline, not a rewrite of the request** — the three quirks and the extension
  backfill are independent, composable interceptors around one proxy call, not three separate
  services or a hand-rolled request-rewriting DSL.

## 10. Observability

- A health endpoint (`/actuator/health` or equivalent), matching `rxclaim-emulator`'s convention.
- Structured logs for auth failures and quirk rejections (useful for a developer debugging why a
  call didn't behave like plain `fhir-service`) — tokens and keys are never logged in full.
- No SLOs/SLIs this phase — this is an internal dev/test tool with no production traffic to set a
  target against, same reasoning Phase 3 used for its own internal services.

## 11. Security / compliance

- All auth material is dummy, generated locally, clearly non-production (PRD FR8, §4 above).
- No real PHI is introduced — `epic-emulator` proxies whatever synthetic data `fhir-service`
  already has seeded.
- Internal-only posture: not fronted by Kong, no edge exposure, matching the `rxclaim-emulator`/
  `provider-registry-service` precedent for internal services.
- No Phase 4b cloud-deployment work is implied or required by this design — see the terminology
  note at the top of this document.

## 12. Milestone plan

- **M1 — Skeleton + pass-through proxy. ✅ Built.** New `epic-emulator/` Maven module; `proxy/`
  forwards all FHIR requests/responses to `fhir-service` unchanged; health endpoint;
  single-container Dockerfile. Definition of done — met: an unmodified FHIR client gets
  byte-identical behavior through `epic-emulator` as through `fhir-service` directly (PRD FR1),
  verified by 3 passing tests against a stub upstream.
- **M2 — Auth emulation. ✅ Built.** `auth/TokenController` (SMART Backend Services JWT
  client-assertion flow, RS384 only — §14) + `auth/BearerAuthFilter` gating every proxied call.
  Definition of done — met: a registered test client completes the flow and uses the resulting
  token for a gated call; missing/invalid/expired tokens are rejected with a plain 401 before
  ever reaching `fhir-service` (PRD FR2, FR8), verified by 6 passing tests (valid flow, no header,
  garbage token, expired assertion, wrong signing key, unknown client). Epic-documentation-version
  pinning (this milestone's other stated task, §7) is **not** fully done — see the real (partial)
  finding recorded in §7 and decision E10.
- **M3 — Extension handling. ✅ Built.** `extensions/ExtensionBackfillInterceptor` (read-time
  backfill, bare resource or inside a search Bundle) + unmodified write pass-through per §5,
  concretely scoped to `MedicationRequest`/`AllergyIntolerance` (decision E12 corrects the PRD's
  generic "Medication" wording). Definition of done — met: a read backfills the expected
  extension on unmodified seeded data; an already-extended resource is left alone, not duplicated;
  a write round-trips its extension unchanged; an out-of-scope resource type (Patient) comes back
  byte-for-byte untouched (PRD FR3), verified by 6 passing tests.
- **M4 — Quirks.** The three interceptors per §6. Definition of done: each of the three quirks is
  independently demonstrable against a real request (PRD FR4–FR6).
- **M5 — Acceptance case + coupling note.** Re-point the existing prescription-refill-risk-triage
  scenario at `epic-emulator` (§8) and confirm an unchanged clinical outcome (PRD FR9, G5); write
  the short coupling note (PRD G6) on which of M2–M4's areas turned out to share state/logic in
  practice.

No milestone here assumes or requires live Epic sandbox access to be *done* — only M2's
documentation-pinning step depends on developer registration, and even that degrades gracefully
per §7.

## 13. Risks

- **Placeholder quirk/extension specifics turn out wrong once §7 is done.** Mitigated by
  explicitly flagging every specific in §5/§6 as unverified until confirmed — nothing here is
  presented as fact prematurely.
- **Two-process local dev friction** (both `epic-emulator` and `fhir-service` must run for any
  real test) — an accepted tradeoff of the proxy architecture, recorded in `prd.md` §9.
- **Scope creep on "quirks" or "extensions."** Mitigated by the closed lists in the PRD (§3/§7) —
  anything discovered beyond the three quirks or the two resource types is Phase 5 backlog, not
  Phase 4 work.

## 14. Decisions (resolving open questions using best judgement)

- **Architecture: proxy in front of `fhir-service`**, not a standalone embedded store — recap of
  `prd.md` §9, reflected in §1 above.
- **Repo location: new top-level `epic-emulator/` directory**, own Maven build — recap of
  `prd.md` §9.
- **Extension round-trip approach: read-time backfill only, no data migration.** Chosen because it
  satisfies "no new fixture pipeline" (PRD G4) with the least new code — writes need no special
  handling at all since `fhir-service` already stores arbitrary extensions.
- **Auth registration is dev-simple** (config-file/in-memory JWK registration, no approval
  workflow) — matches the PRD's instruction to assume easy developer access, and matches the
  *shape* of Epic's real flow without its real-world overhead.
- **No separate `plan.md`.** Following the Phase 3 convention (not Phase 2's): the milestone plan
  lives in this document (§12), and `prd.md` covers goals/requirements/success metrics. See the
  terminology note at the top of `prd.md`.
- **Epic documentation version: not yet pinned.** Explicitly left open (§7) rather than guessed,
  since asserting a specific version without having actually registered would be exactly the kind
  of unverified claim this document is trying to avoid making elsewhere.
- **Client-assertion signing: RS384 only, ES384 not implemented.** The base SMART Backend Services
  spec allows both; supporting EC keys too would add a second key-handling path in
  `ClientAssertionValidator` for marginal M2 value. Documented as a known simplification (§4),
  not a silent gap.
- **401 rejection body is plain OAuth2 JSON, not yet Epic's `OperationOutcome` shape.** §4's own
  narrative anticipated the Epic-shaped error; M2's actual definition of done (above) only requires
  rejection, and the `OperationOutcome` shape is explicitly FR6/quirk C, scoped to M4. Sequenced
  this way on purpose — M4 upgrades this exact response body, it isn't a dropped requirement.
