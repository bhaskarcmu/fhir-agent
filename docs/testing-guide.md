# Testing Guide

What is tested today, how to run it at every level, and how to write new tests that earn their
keep. Counts are a snapshot (verified at time of writing); the commands are the source of truth.

- **"Is this change safe?"** → §2, run the level that covers it.
- **"What does this project actually test?"** → §1 and §3, including what it *doesn't* (§4).
- **"How do I write a good test here?"** → §5, and read §6 first — it is the reason §5 says what
  it says.

---

## 1. The levels, in this codebase's terms

Test-level vocabulary is used inconsistently across the industry, so here is what each term
means *here*, with a real example you can open.

| Level | Question it answers | Knows internals? | Needs a running stack? | Example |
|---|---|---|---|---|
| **Unit** | Does this one class do its job? | Only its public API | No | `RulesEngineTest` |
| **White box** | Does an internal invariant hold? | Yes — deliberately | No | `RulesEngineTest.deterministicOrder_byDomain_whenTwoDenies` |
| **Component** | Does a whole service's logic hang together? | No — treats the service as the unit | No (fakes downstream) | `AdjudicationPipelineTest` |
| **Interface / contract** | Do two services actually agree on the wire? | No — asserts the boundary | A stub server, not the real stack | `HttpTriageClientTest` |
| **End-to-end** | Does a real claim get the right answer through real services? | No | Yes — the live stack | `e2e/test_golden_paths.py` |
| **Independence** | Is Phase 2 still additive (R9)? | n/a | No | CI `phase1` job |
| **Smoke** | Is a deployed instance alive and sane? | No | Yes — a deployed target | `client/platform/integration_test.py` |

The distinction that matters most here is **interface vs. component**. A component test with a
mocked HTTP client proves your code calls *your mock* correctly. It cannot prove your code and
the other service agree. §6 is a true story about exactly that costing several milestones.

## 2. Running the tests

**Everything that needs no stack** (the fast loop — run this before every commit):

```bash
# Python — all suites (config in pytest.ini)
pytest

# Java — the two Phase 2 services
mvn -f claims-service/pom.xml test
mvn -f rxclaim-emulator/pom.xml test
```

**A single level or suite:**

```bash
pytest client/clinical/tests                  # FHIR client library
pytest triage-service/src/triage/tests        # clinical rules + API
pytest mcp-agent/tests                        # Phase 1 agent
pytest claims-agent/tests                     # Phase 2 explanation agent
pytest data/scripts                           # loader/seeder logic

pytest provider-registry-service/src/provider_registry/tests  # Phase 3 taxonomy/proximity search
pytest data/scripts/provider_ingest                            # Phase 3 real NPPES/NUCC/ZCTA ETL
pytest provider-curation-agent/tests                            # Phase 3 ingestion-narration agent
pytest provider-mcp-server/tests                                # Phase 3 real MCP handshake
pytest provider-search-agent/tests                              # Phase 3 MCP client + groundedness eval

mvn -f claims-service/pom.xml test -Dtest=RulesEngineTest        # one class
mvn -f claims-service/pom.xml test -Dtest=HttpTriageClientTest   # the contract test
```

Several Phase 3 suites need a local Postgres (`docker compose --profile phase3 up -d postgres`,
then `TEST_DATABASE_URL=postgresql://provider_registry:provider_registry@localhost:5432/provider_registry`)
and self-skip — not error — when it's unreachable, same convention as the rest of this project.
`provider-search-agent`'s groundedness eval additionally self-skips without an Anthropic key,
since it makes real, billed API calls.

**End-to-end** (needs the stack; self-skips if it is not up, so it is safe to collect anywhere):

```bash
docker compose --profile phase2 up --build -d
pytest e2e/
```

`e2e/conftest.py` seeds the FHIR fixtures itself — you do **not** need to run the demo seeder
first. This matters: the demo FHIR server is in-memory, so it boots empty every time.

**Phase 1 independence** (the R9 guarantee — reproduce CI locally):

```bash
docker compose config --services | sort | paste -sd' ' -   # must print exactly: fhir mcp-agent triage
```

**The FHIR service** (inherited HAPI starter suite):

```bash
# Unset SPRING_DATASOURCE_URL / NEON_* first, or MdmTest boots against a live DB and
# fails on auth — an environment problem wearing a test-failure costume.
cd fhir-service && ./mvnw clean verify
```

**Smoke tests against a live target** (script-style, not pytest — they call `sys.exit`, which is
why `pytest.ini` deliberately excludes them):

```bash
python3 client/clinical/smoke_test.py         # library against a live FHIR server
python3 client/platform/integration_test.py   # direct FHIR-server integration
# fhir-service/src/test/smoketest/*.http — REST Client requests for manual probing
```

## 3. What is tested today

**Java — our services (60 tests)**

| Suite | Tests | Level | Covers |
|---|---:|---|---|
| `ClaimIntakeContractTest` | 14 | interface/contract | The R17.6 error taxonomy's three disjoint classes: malformed → 400 + `OperationOutcome` with nothing adjudicated; decision → 200 (a denial is not an error); system error → 503 |
| `RulesEngineTest` | 12 | unit + white box | Every rule; precedence (R17.3); deterministic ordering (R17.4); fail-closed `UNKNOWN` → PEND |
| `HttpTriageClientTest` | 9 | interface/contract | Real HTTP round-trip to a stub triage: request body carries `patient_id`; every failure mode → `UNKNOWN` |
| `AdjudicationPipelineTest` | 8 | component | The R8 golden paths at decision level; patient id reaches triage; unavailable check pends |
| `FhirArtifactBuilderTest` | 3 | unit | The artefact graph shape (R18.2) |
| `LegacyAdapterTest` | 3 | unit + white box | Fixed-width legacy record parsing (the ACL boundary) |
| `FilePayerKbTest` | 2 | unit | Formulary lookup via the C3 repository seam |
| `AdjudicationServiceTest` | 1 | component | Intake idempotency — resubmit returns the prior decision, persists once (R18.3) |
| `rxclaim-emulator` (`LegacyRecordTest`, `RxClaimCoreTest`) | 8 | unit + white box | DDS record layout; `ADJRXCLM` legacy adjudication |

**Python (113 tests)**

| Suite | Tests | Covers |
|---|---:|---|
| `triage-service/src/triage/tests` | 40 | Drug-allergy rules + the FastAPI contract |
| `client/clinical/tests` | 35 | FHIR parsing into clinical domain types |
| `data/scripts` | 19 | Bundle loading/validation logic (server-independent) |
| `mcp-agent/tests` | 11 | Phase 1 agent tool-use and demo flow |
| `claims-agent/tests` | 8 | Explanation rendering and tools |

**End-to-end (7 tests)** — `e2e/test_golden_paths.py`: the six golden paths (approved, pended,
routed, denied-inactive, denied-multi-reason, denied-clinical-safety) plus idempotent resubmit,
against the live stack.

**FHIR service** — 78 `@Test` methods inherited from the HAPI FHIR JPA starter, plus our
`VersionedUrlFallbackValidationSupportTest`. Mostly upstream coverage; we own the validation
fallback and the custom bean/interceptor tests.

**Python — Phase 3 (83 tests, on top of the 113 above — 196 total)**

| Suite | Tests | Level | Covers |
|---|---:|---|---|
| `provider-registry-service` | 34 | unit + interface | Taxonomy fuzzy match, haversine proximity search, the three error-taxonomy classes, rate limiting. DB-free tests (validation/taxonomy/rate-limit) run with no `DATABASE_URL`; DB-backed tests self-skip when Postgres is unreachable |
| `provider-mcp-server` | 14 | unit + interface (real handshake) | 7 `registry_client` tests (mocked HTTP); 7 **real MCP protocol** integration tests — genuine `initialize`/`tools/list`/`tools/call` against real subprocesses, including a real SDK schema-validation rejection and a real `not_found` path |
| `data/scripts/provider_ingest` | 12 | unit + interface | Real NPPES/NUCC/ZCTA fetch/parse/join logic (mocked HTTP, no network) plus DB-backed idempotency tests for `run_ingestion.py` |
| `provider-curation-agent` | 13 | unit + component | Deterministic summary rendering (no DB); ingestion-tool orchestration, mixed mocked-subprocess and DB-backed (self-skip) |
| `provider-search-agent` | 10 | unit + end-to-end (real LLM) | 7 tool-use-loop tests, Anthropic client and MCP session both mocked; **3 real groundedness-eval tests** making genuine, billed Claude API calls through the full real stack |

**CI** (`.github/workflows/tests.yml`) — five jobs: `phase1` (independence: Phase 1 suites pass
with no Phase 2 packages installed, and the default compose stack is unchanged), `phase2-java`,
`phase2-python`, `phase3-python` (the full Phase 3 suite against a real Postgres service
container — DB-backed tests actually run in CI, not just self-skip locally), `phase3-terraform`
(`terraform validate` in a matrix across all four Phase 3 Terraform stubs).

## 4. What is *not* tested — known gaps

Documenting these honestly is part of the test strategy. Each is a real hole, not a shrug.

- **CI does not run the e2e suite.** No job brings up the stack. This is the highest-value gap:
  it is precisely why the regression in §6 reached `main`. Fixing it needs a compose-based CI
  job (proposed in [`phase2/plan.md` §16](./phase2/plan.md#16-future-work)).
- **No non-regression snapshots.** R19 requires stored `ClaimResponse` snapshots so catalogue
  growth cannot silently change existing decisions. There is no `testdata/` snapshot corpus yet.
- **The e2e suite asserts the `ClaimResponse`, not the persisted audit graph.** R19 asks e2e to
  assert the R18.2 graph (`Claim`/`ClaimResponse`/`Task`/`Provenance`/`RiskAssessment`) landed
  in FHIR. `FhirArtifactBuilderTest` checks the graph is *built* correctly; nothing checks it is
  *stored* correctly.
- **The `gateway` profile is not exercised in CI.** Kong key-auth and rate limiting are verified
  manually.
- **No load, performance, or soak tests**, and no chaos/failure-injection beyond the unit-level
  fault paths in `HttpTriageClientTest`.
- **Phase 3 cloud deployment has never actually run.** `terraform plan`/`apply` and
  `deploy-phase3.sh` are unexercised against live GCP credentials — only `terraform validate`
  (syntax/schema, no live state) runs anywhere, including in CI. This is Phase 3b's job.
- **Phase 3 taxonomy-match quality is not broadly evaluated.** `resolve_specialty`'s fuzzy
  matcher is unit-tested against specific known inputs, not scored against a broad, representative
  set of real free-text clinical phrasing. The one quality-relevant bug found (a dropped
  character mid-transcription) was caught by running live queries, not by a systematic eval.
- **A true full-state NPPES pull has never been run.** The committed dataset (12,582 providers,
  NC/CA/MT) is a bounded, curated pull — a few pages per taxonomy term per state — not a census.
  Ingestion at full-state scale, and its runtime, is untested.
- **`accepting_new_patients` is always `"unknown"` by design** (NPPES has no such field —
  decisions.md P6), so no test can or should assert a real value for it; this is a documented
  data-source limitation, not a test gap.

## 5. How to write each kind of test here

### Unit tests

One class, no I/O, no Spring context. Assert behaviour through the public API. `RulesEngineTest`
is the model: construct a claim and a formulary entry, call `evaluate`, assert the outcome and
the reason codes.

Rules get **one test per rule** *and* **combination tests**. A rule that works alone but breaks
precedence when combined with another is still broken — the interesting bugs live in the
interaction:

```java
@Test
void unknownRisk_doesNotMaskAHardDenial() {
    var r = engine.evaluate(claim(...), null /* non-formulary */, RiskLevel.UNKNOWN);
    assertThat(r.outcome()).isEqualTo(Outcome.DENIED);              // DENY outranks the PEND
    assertThat(r.allFindings()).extracting(Finding::code)
            .contains("non-formulary", "clinical-safety-unavailable");  // both still recorded
}
```

### White-box tests

Reach for these when an **internal invariant** has no user-visible surface but breaking it
breaks a requirement. Determinism is the canonical example: nothing about the API says findings
are sorted by `(severity, domain, ruleId)`, but R17.4 demands reproducible output, so a test
pins the ordering directly.

Use them sparingly and deliberately. A white-box test is coupled to the implementation *by
design* — that is the point, and also the cost. Legitimate uses here: the deterministic sort
order, DDS byte offsets in `LegacyAdapter`, and the fixed-width legacy record layout. If you
find yourself writing one because the behaviour is hard to reach from outside, that is usually a
design smell, not a testing need.

### Component tests

Treat one service as the unit. Real internals (rules, ACL, pipeline), **fakes at the
boundaries**. `AdjudicationPipelineTest` runs the entire decision flow with a fake legacy client,
a fake triage client, and a stub FHIR client:

```java
private AdjudicationPipeline pipeline(FormularyEntry formulary, TriageClient triage, StubFhir fhir) {
    PayerKb kb = (planId, rxcui) -> Optional.ofNullable(formulary);   // fake KB
    LegacyClient legacy = record -> PAID_RESPONSE;                    // fake legacy core
    return new AdjudicationPipeline(kb, rules, triage, legacy, acl, fhir);
}
```

Prefer small hand-written fakes (a lambda, a record) over a mocking framework. They read better,
they break loudly when an interface changes, and they don't quietly encode assumptions about
call counts that nobody actually cares about.

Component tests should also assert **wiring**, not just outcomes. A value that silently fails to
reach a collaborator is invisible to outcome-only assertions:

```java
@Test
void resolvedPatientId_isHandedToTriage() {
    AtomicReference<String> seen = new AtomicReference<>();
    pipeline(fe(...), (claim, patientId) -> { seen.set(patientId); return RiskLevel.LOW; },
             new StubFhir(Optional.of("P1")))
            .adjudicate(claim(...));
    assertThat(seen.get()).isEqualTo("P1");   // it was once null, and nothing noticed
}
```

### Interface / contract tests

**This is the level this project learned to respect the hard way.** When your code talks to
another service over HTTP, test it over **real HTTP against a stub server** — not against a
mocked client object.

`HttpTriageClientTest` starts a JDK `com.sun.net.httpserver.HttpServer` on a free port (no new
dependency), points the real client at it, and asserts both directions of the contract:

```java
@Test
void sendsPatientIdInTheRequestBody_andMapsHighRisk() throws IOException {
    String url = startStub(200, riskJson("high"));

    RiskLevel risk = new HttpTriageClient(url).assess(claim(), "member-000000009");

    assertThat(risk).isEqualTo(RiskLevel.HIGH);
    // The body must actually arrive — an empty body is the failure this test exists to catch.
    assertThat(lastBody.get()).contains("\"patient_id\"").contains("member-000000009");
}
```

Rules for this level:

1. **Assert the request, not just the response.** Half the contract is what you send. A mock
   cannot fail this assertion, because a mock *is* your assumption about the request.
2. **Cover every failure mode explicitly** — 4xx, 5xx, transport failure, malformed body,
   unrecognised enum value. Each gets its own test, and each must map to a deliberate state.
3. **Decide what "unavailable" means, then pin it in a test.** `UNKNOWN`, never a value that
   reads as success (§6).
4. **Use a stub server, not a mock,** whenever the transport itself could be wrong — different
   HTTP versions, content types, encodings, redirects. Mocks skip the transport, and the
   transport is where these bugs live.

**The inbound flavour.** The same level applies to your *own* API, where the contract is what you
accept and what you refuse. `ClaimIntakeContractTest` uses `@WebMvcTest` rather than calling the
controller as a plain object, because the contract lives in machinery a unit test never runs:
Jackson binding, `@Valid`, and the advice that renders the error. Calling the method directly
skips all three and proves nothing about what an HTTP client sees.

For an inbound contract, assert the **refusals** as carefully as the successes, and assert what
did *not* happen:

```java
verify(service, never()).adjudicateAndPersist(any());   // a malformed claim must not reach the pipeline
```

That "never" is the whole contract: rejection has to happen *before* the work, or something
invalid has already acquired a decision.

### End-to-end tests

Real services, real HTTP, real FHIR. Keep them few, keep them golden-path, and make them
**self-contained**: an e2e suite that depends on someone having run a demo script first is an
e2e suite that passes on your laptop and fails on a fresh machine.

`e2e/conftest.py` seeds its own fixtures by reusing the committed seeder — one reproducible
generator per fixture (R19), rather than a second copy that drifts:

```python
_SEEDER_PATH = Path(__file__).resolve().parents[1] / "data" / "scripts" / "seed_claims_demo.py"
# … imported by path, then:

@pytest.fixture(scope="session", autouse=True)
def seed_fhir_patients() -> None:
    with httpx.Client(timeout=30) as client:
        _seeder.seed_patients(client)
```

E2E tests self-skip when the stack is unreachable (`pytest.mark.skipif`), so they are safe to
collect in any environment but only assert when they can be meaningful.

### Fixture governance (R19)

Fixtures live under `data/payer-kb/` and per-service `testdata/`. Each is generated by a
**committed script**, so it is reproducible. Changing an expected decision requires its own
commit with a rationale — a decision changing silently because a fixture drifted is the exact
failure this rule prevents.

## 6. Case study: how a dead safety check passed every test

Worth reading before you write tests here, because it explains the rules above better than the
rules do.

**The bug.** `claims-service` called the triage service without patient context. Triage
evaluated nothing. The client mapped every failure — including "I couldn't check" — to
`RiskLevel.LOW`. So a penicillin-allergic patient was cleanly **APPROVED** for amoxicillin.

**It survived several milestones.** Here is what each level did, and why:

| Level | Result | Why |
|---|---|---|
| Unit (`RulesEngineTest`) | ✅ passed | Correctly mapped `HIGH` → DENY. It was never *given* `HIGH`. The rules engine was innocent. |
| Component (`AdjudicationPipelineTest`) | ✅ passed | The fake triage returned whatever risk the test supplied. It never asked whether the real client could obtain one. |
| E2E (`test_golden_paths.py`) | ✅ passed | The five golden paths asserted formulary/PA/quantity outcomes. **None of them exercised clinical safety.** |
| Manual demo | ✅ looked perfect | Every path printed its expected outcome. |

Nothing failed, because **the failure mode was silence**. A safety check that cannot see a
conflict reports no conflict — indistinguishable from a safe patient. Green tests were not
evidence of safety; they were evidence that nothing asked the question.

**What actually caught it:** running the full demo and noticing one path printed `APPROVED`
where a human expected `DENIED`. A person, not the suite.

**What the tests would need to have caught it:**

1. **An e2e path for the safety scenario.** The suite had no case where the correct answer
   depended on triage being consulted. A rule with no failing case has no coverage, whatever the
   line count says. → now `E2E-SAFETY`.
2. **A contract test with a real HTTP round-trip.** The client's request body was empty (an HTTP
   version mismatch — see the developer guide's traps). Every mock-based test agreed with the
   client's own assumptions and passed. → now `HttpTriageClientTest`, asserting the request body.
3. **A wiring assertion.** Nothing checked the patient id reached triage. → now
   `resolvedPatientId_isHandedToTriage`.
4. **A fail-closed contract.** `LOW` meant both "safe" and "unknown". Once those are the same
   value, no test *can* tell them apart — the type system has thrown the information away. →
   now `RiskLevel.UNKNOWN` → PEND.

**The transferable lessons:**

- **Test the states you hope never happen.** The unhappy paths are where silent failure lives.
- **A green suite proves the questions you asked have good answers.** It says nothing about the
  questions you didn't ask.
- **Make "I don't know" a distinct value.** If unavailable and safe share a representation, no
  amount of testing recovers the difference.
- **Mocks agree with you. Stub servers don't.** For anything crossing a process boundary, that
  disagreement is the entire value.
- **Demo it to a human.** The whole suite missed this; one person reading one line of output
  found it.

**A coda, from writing this guide.** Making the safety check fail closed broke three e2e tests —
member `000000001` had no FHIR record, so those claims now (correctly) pended. Nobody noticed,
because **CI doesn't run e2e**. The suite that would have caught the regression wasn't watching.
That is now the top gap in §4, and the fix is proposed in the plan.

## 6a. A second case study: the mocked-schema test that couldn't catch a real bug

Shorter, and from Phase 3, but the same shape as §6: a suite that was internally consistent and
still missed a real defect, because it tested against its own assumption rather than the real
boundary.

**The bug.** `provider-mcp-server`'s `search_providers_near` tool originally declared its
`location` parameter as a JSON Schema `oneOf` — `{zip}` or `{lat, lon}`. `provider-search-agent`'s
7 tool-use-loop unit tests all passed: they mock the Anthropic client, so they assert the agent
correctly forwards *whatever the mock returns*. None of them exercised what live Claude actually
does with that schema. Live Claude reliably serialized the whole `location` object as a JSON
*string* instead of a native object — 12/12 consecutive attempts — which `provider-mcp-server`
then rejected on every real call.

**What caught it:** the groundedness eval (`test_groundedness_eval.py`) — the one Phase 3 test
that makes real, billed calls through the full real stack, not a mocked one. It's slow and it
costs money, which is exactly why it's the only test of its kind here; the lesson isn't "make
every test real," it's **"know which of your levels is actually exercising live-model behaviour,
and keep at least one that is."**

**The fix, and the transferable lesson:** flatten the schema; push the cross-field rule
downstream into `provider-registry-service`'s Pydantic validation instead of relying on a JSON
Schema construct an LLM has to serialize correctly. Full detail: developer-guide.md §7,
design.md §14, decisions.md P17. The parallel to §6 is exact: a mock that encodes your own
assumption about the interface cannot fail when that assumption is wrong — only a real boundary
can.

## 7. Traps when testing

- **Ambient env vars.** `SPRING_DATASOURCE_URL` / `NEON_*` make `fhir-service` tests boot against
  a live DB and fail on auth. `FHIR_GATEWAY_URL` leaks from your host into containers. Unset
  before running; pass compose-network addresses explicitly.
- **The FHIR server is in-memory.** Restarting the `fhir` container wipes everything. Never
  assume a warm server — seed in a fixture.
- **Test-order dependence.** If a test only passes after a demo script ran, it is not a test.
- **FHIR search lags; reads don't.** Assert via `read` where you can; if you must search, poll
  rather than sleep (see `seed_patients`).
- **Spring DI failures are runtime-only.** Multiple constructors, missing `@Autowired` — unit
  tests will not catch it. Boot the service.
- **Identically-named `tests/test_*.py` files collide silently across packages.** This repo's
  `--import-mode=importlib` plus per-package `tests/__init__.py` means two files with the same
  name in different packages resolve to the same module and collide in `sys.modules` — one
  suite runs twice, the other never runs, exit code stays green throughout. Check repo-wide
  uniqueness before adding a new test file: `find . -path '*/tests/test_*.py' -printf '%f\n' |
  sort | uniq -d`. Full story: developer-guide.md §7, decisions.md P15.
- **Mocking the Anthropic client tells you nothing about what live Claude actually sends.** A
  mocked tool-use loop only proves your code handles whatever the mock returns — it cannot
  catch a real model quirk like the `oneOf`-serialization bug in §6a. Keep at least one real,
  billed test per agent for exactly this reason (`test_groundedness_eval.py`'s pattern).
