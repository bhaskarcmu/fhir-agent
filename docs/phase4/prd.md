# Phase 4 PRD — Epic Emulator

**Status:** DRAFT — planning only, no implementation started.
**Companion doc:** [`design.md`](./design.md) — architecture, package layout, the three quirks'
concrete pinned choices, and the milestone plan (no separate `plan.md`; Phase 3 already
consolidated that into `design.md`, and this phase follows the same convention).
**Decision index:** [`decisions.md`](./decisions.md) tracks every decision below with a status
(Accepted / Partially delivered / Superseded), same convention as Phase 2/Phase 3.
**Canonical status:** see [`README.md`](./README.md) — other documents link there rather than
restate it.
**Extends:** Phase 1 (refill-triage), Phase 2 (claims adjudication), Phase 3 (provider search) — all
unmodified.
**Owner:** TBD
**Terminology note:** internal work within Phase 4 is tracked as **milestones** (M1, M2, ...),
never as "Phase 4.x" — "Phase" is reserved for top-level platform phases only: Phase 1, Phase 2,
Phase 3, Phase 4 (this doc), and a future **Phase 4b** cloud-deployment phase, mirroring Phase 2b
and Phase 3b.
**Access-assumption note:** this PRD assumes developer access to Epic's public documentation and
sandbox is simple, free, self-service registration — not a procurement/vetting process. That
assumption is stated once here (§6, §9) and will be validated and detailed fully in the follow-on
design doc; nothing in this PRD depends on it being wrong in an expensive way (see §9).

---

## 1. Problem statement

`fhir-service` is intentionally EHR-agnostic — it speaks base FHIR R4 and nothing more. Nothing in
the platform today exercises what it's actually like to integrate against **Epic**: Epic's
SMART-on-FHIR backend-services auth flow, Epic's custom profiles/extensions on top of base R4
resources, or Epic's well-documented proprietary quirks (non-standard pagination, required search
parameters, error shapes). Building and testing against a real Epic sandbox isn't practical as a
routine dependency of everyday development.

Phase 4 builds **epic-emulator**: a single deployable service that sits in front of
`fhir-service` and reproduces enough of Epic's real, *publicly documented* behavior that the rest
of the platform can be developed and tested against realistic Epic-like behavior, without a live
Epic connection.

**Why one monolith, not three services.** The three areas below (auth, extensions, quirks) are
sub-features of one new, unbuilt module whose internal boundaries are not yet known — they may
turn out to share more state than expected (auth context needed by extension validation, shared
request/response shaping across "quirks"), or they may not. Committing to service boundaries
before any real code exists risks locking in a guessed cut. Phase 4 builds them together, in one
Spring Boot process, and captures what real building reveals about the coupling (G6); Phase 5
decomposes along evidence, not the guess below.

**Candidate capability areas** (hypotheses to validate during Phase 4, not commitments):

1. **Epic auth emulation** — SMART App Launch "Backend Services" OAuth2 flow (client-credentials-
   style, JWT client assertion).
   *In plain terms:* before any system can read a patient's chart from real Epic, it has to prove
   who it is — not with a password, but through an automated handshake where the requesting app
   presents a signed digital assertion and Epic hands back a temporary access pass. This emulates
   that same checkpoint, using Epic's specific version of the handshake.
2. **Epic custom profile & extension handling** — scoped to extensions on Medication/
   AllergyIntolerance resources, tied to the existing prescription-refill-risk-triage reference
   workflow — not "any Epic extension."
   *In plain terms:* Epic doesn't just store records in the shared, generic format — it adds its
   own extra fields on top, including on medications and allergies. This emulates just those extra
   fields, for just the two record types the platform's existing drug-allergy check already reads.
3. **Epic proprietary quirks** — bounded to exactly three: non-standard pagination/`_count`
   behavior, a non-standard required search-parameter combination, and `OperationOutcome`
   error-shape deviations.
   *In plain terms:* beyond login and data format, Epic's API just *behaves* differently in
   documented ways — how many results come back per page, what filters you're required to
   include together, and how it phrases an error. The three chosen quirks each sample a
   **different layer** of that rather than three variations on one theme: **how results come
   back** (pagination), **what you're allowed to ask for in the first place** (the required
   parameter combination), and **how you're told something went wrong** (the error shape).

   These three are named as *categories* here; the exact resource and parameter each one attaches
   to is a concrete design choice, pinned down in [`design.md`](./design.md) §6/§14 — not decided
   in this PRD.

## 2. Goals

- **G1:** Emulate Epic's SMART App Launch Backend Services OAuth2 flow (JWT client assertion →
  short-lived access token) in front of `fhir-service`, conformant to Epic's own published
  backend-services auth documentation.
- **G2:** Emulate Epic's custom extension handling on Medication and AllergyIntolerance resources
  only — validating and injecting Epic-specific extensions on top of `fhir-service`'s base R4 data.
- **G3:** Emulate exactly three named Epic quirks (pagination, a required search-parameter
  combination, `OperationOutcome` error shape) — no open-ended "quirks" backlog.
- **G4:** Ship as one deployable Spring Boot application — new top-level `epic-emulator/`
  directory, one Maven build — proxying real FHIR data through to `fhir-service`. No new data/
  fixture pipeline.
- **G5:** Prove it works using the platform's own existing acceptance case: re-point the
  prescription-refill-risk-triage flow at `epic-emulator` instead of `fhir-service` directly, and
  confirm it produces the same clinical answer.
- **G6:** Produce a short, concrete written note on which of the three areas shared state/logic in
  practice and which stayed cleanly separate — the evidence Phase 5's decomposition uses.

## 3. Non-goals (this phase)

- **Independent deployability of the three capability areas.** No confirmed boundary exists yet to
  split along — see §1.
- **Absorbing `triage-service` or `claims-service` decision logic.** Epic emulation is a
  protocol/format concern (what does a request/response look like to something calling an
  Epic-flavored API); clinical risk and claims adjudication are business-logic concerns that
  already live in, and are independently validated in, their own services. `epic-emulator` does not
  reimplement or duplicate either — Phase 4's acceptance case (G5) *exercises* `triage-service`
  through `epic-emulator`'s proxy, it does not fold triage logic into it. Same reasoning excludes
  `claims-service`.
- **Emulating any Epic extension beyond Medication/AllergyIntolerance,** or any quirk beyond the
  three named ones. Both lists are closed for this phase; anything else discovered goes on a Phase
  5 backlog, not into Phase 4 scope.
- **Validating against a live/paid Epic sandbox as a build dependency.** Correctness is judged
  against Epic's public documentation (§6); a free sandbox registration, if simple to obtain, is a
  nice-to-have cross-check, not something Phase 4 blocks on.
- **Production hardening, real secrets, or real credential handling.** The emulated auth flow uses
  dummy keys only (§6).

## 4. Users & use cases

**Primary user:** a developer on this platform, not a clinician — someone who needs to build or
test against Epic-like behavior without a real Epic integration.

- **UC1 — Swap the FHIR base URL.** A developer points an existing consumer (`mcp-agent` /
  `triage-service`) at `epic-emulator` instead of `fhir-service` and runs the existing refill-risk
  scenario, confirming the clinical answer is unchanged despite going through Epic-flavored auth,
  extensions, and quirks.
- **UC2 — Obtain a token the Epic way.** A developer registers a test client against
  `epic-emulator`'s simulated backend-services flow (JWK/public key registration → signed JWT
  client assertion → access token), mirroring what a real Epic App Orchard registration requires,
  but free and self-service.
- **UC3 — Read Epic-flavored clinical data.** A developer requests a Medication or
  AllergyIntolerance resource through `epic-emulator` and gets the base R4 resource back with
  Epic-specific extensions layered on.
- **UC4 — Hit a quirk on purpose.** A developer issues a request that exercises one of the three
  named quirks (pagination, the required search-parameter combination, or a triggered error
  condition) and observes Epic-shaped behavior that differs from `fhir-service`'s default.

## 5. Functional requirements

| # | Requirement |
|---|---|
| FR1 | `epic-emulator` exposes a FHIR R4-compatible HTTP surface that proxies read/search/create/update requests through to `fhir-service`'s existing REST API; resource types with no emulated behavior pass through unchanged. |
| FR2 | Protected endpoints require a bearer token obtained via a simulated SMART Backend Services flow: a registered client presents a signed JWT client assertion and receives a short-lived access token, conformant with Epic's published backend-services auth guide. |
| FR3 | Responses for Medication and AllergyIntolerance resources are augmented with Epic-specific extensions before being returned; requests containing those extensions are accepted and round-trip correctly on write. |
| FR4 | At least one search operation exhibits Epic's non-standard pagination behavior (e.g., enforcing/capping `_count`, non-default `Link`-relation behavior) instead of `fhir-service`'s default HAPI pagination. |
| FR5 | At least one search operation enforces a documented Epic-specific required parameter combination, rejecting an otherwise-valid base-R4 request that omits it, with an Epic-shaped rejection. |
| FR6 | Error responses for the conditions exercised by FR2/FR5 use Epic's `OperationOutcome` shape/deviations, not `fhir-service`'s default HAPI error body. |
| FR7 | All Epic-specific behavior (auth, extensions, quirks) is implemented as interceptors/filters within one Spring Boot process — no network calls between the three capability areas. |
| FR8 | Every credential/key used by the emulated auth flow is unambiguously test-only (dummy keys, non-production markers in logs/config) — never resembles a real production secret. |
| FR9 | The existing prescription-refill-risk-triage scenario, re-pointed at `epic-emulator` instead of `fhir-service`, produces the same `RiskAssessment` outcome as it does against `fhir-service` directly. |

## 6. Non-functional requirements

- **Toolchain.** Java 21, Spring Boot, Maven — identical to `fhir-service`; no new stack introduced.
- **Deployability this phase.** A single local-run Dockerfile only. No Kubernetes manifests, no
  Kong routes, no per-area CI pipelines (see skip table, §7).
- **Correctness source-of-truth.** Epic's own public developer documentation (the "Epic on FHIR"
  portal) — specifically its per-resource API pages (documented search-parameter support and
  Epic-specific extensions per resource) and its published SMART Backend Services auth guide.
  Phase 4 targets conformance with **one fixed version** of that documentation (picked and recorded
  in the design doc), since Epic's documented behavior varies by client software version.
- **Access assumption (stated once, to be validated in the design doc).** Epic's developer program
  is assumed to allow free, self-service registration with no health-system affiliation required,
  granting access to the documentation above and a shared non-production sandbox. Phase 4 is scoped
  so a developer can complete this unassisted, in the normal course of work — not a procurement or
  BAA process. If this assumption turns out to be wrong in some detail, Phase 4 still stands on the
  public documentation alone (§9); live sandbox access is a cross-check, not a build dependency.
- **Security.** Emulated auth must be unmistakably non-production (§FR8). No real PHI, no real
  credentials, anywhere in this module.
- **Data.** No new fixture or seed pipeline. `epic-emulator` proxies to `fhir-service`'s
  already-seeded data (Synthea-based), so existing demo data is reused as-is.

## 7. Out of scope (explicit — the speed argument)

| Skipped in Phase 4 (deferred to Phase 5) | Why it's safe to skip now |
|---|---|
| Separate repos/builds per capability area | No confirmed boundary to split along yet |
| Per-area Dockerfiles / container images | One process to run and iterate on locally |
| K8s manifests, Kong routes per area | No independent-deployability claim is being made |
| Inter-area REST contracts / DTOs / serialization | No network boundary exists yet — direct method calls are correct, not sloppy |
| Per-area CI pipelines, cross-network integration tests | Nothing to integration-test across yet |
| `triage-service` / `claims-service` decision logic, absorbed into this module | Different concern (clinical/claims logic vs. protocol emulation); those services stay independently owned and are only *called through*, per §3 |
| Any Epic extension beyond Medication/AllergyIntolerance, any quirk beyond the three named | Open-ended scope is the one thing that would blow the speed goal |

## 8. Success metrics

- All three capability areas (FR1–FR6) demonstrably working end-to-end in one running process.
- Zero artifacts from the §7 table exist in the repo at the end of Phase 4 — checkable by
  inspection.
- No internal package-level interfaces/DTOs between the three areas that mimic a future REST
  boundary — checked at code review, not just by artifact absence.
- FR9 (the refill-risk-triage acceptance case) passes with an unchanged clinical outcome.
- A short written coupling note (G6) exists, naming which areas shared state/logic and which
  stayed cleanly separate.

## 9. Decisions (resolving open questions using best judgement)

These were open questions during planning; resolved here so the build isn't blocked. Each is a
reversible call — flag any you want changed before the design doc is written.

- **Integration architecture: proxy in front of `fhir-service`,** not a standalone service with its
  own embedded store. Chosen over the standalone alternative because it keeps `fhir-service`'s
  already-seeded data as the single source of truth (no duplicate fixtures to build or keep in
  sync). Accepted tradeoff: both services must run together for any real end-to-end test — unlike
  a standalone emulator, which would run alone but need its own seed data.
- **Repo location: new top-level `epic-emulator/` directory,** own Maven build — matches this
  repo's existing per-service layout, and follows the same shape as `rxclaim-emulator/` (a
  same-repo precedent: an internal, single-process Spring Boot service that convincingly emulates a
  real system's non-standard contract in front of the platform's real data).
- **Extension and quirk scope are closed lists, not open categories** (Medication/
  AllergyIntolerance only; exactly three quirks) — the concrete mechanism keeping Phase 4 sized in
  days, not weeks, per the stated speed goal.
- **`triage-service` and `claims-service` logic is explicitly excluded from `epic-emulator`.**
  Both are already independently built and validated; Phase 4 exercises `triage-service` through
  the emulator (FR9) but does not duplicate its rules, and does not touch `claims-service` at all
  this phase.
- **Epic access: assumed free and self-service** (§6), not a procurement process. If wrong in
  detail, the public per-resource documentation alone is sufficient for Phase 4; nothing here is
  built to depend on live sandbox access.

## 10. Forward note for Phase 5

Decomposition boundaries should be derived from what Phase 4 actually reveals about coupling and
change patterns (G6) — not from the three-area list above verbatim. If two areas turn out to share
significant state, that's a signal they may belong in the same service even after decomposition;
that is the intended payoff of building monolith-first, and it is what makes the Phase 4 → Phase 5
sequence a real engineering decision rather than a staged one.

**G6 is delivered:** [`coupling-note.md`](./coupling-note.md), captured after M1–M5 were actually
built and verified live, not guessed in advance.
