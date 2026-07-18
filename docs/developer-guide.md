# Developer Guide

How this codebase is put together, the rules that hold it together, and how to continue the
work without breaking it. Read this before your first change.

- **New to the project?** Read §1–§3, then run the demo ([`demo-guide.md`](./demo-guide.md)).
- **About to write code?** §4 (where things live) and §5 (invariants) are the load-bearing ones.
- **Something behaving weirdly?** §7 is a list of traps that have already cost real hours.
- **Looking for what to build next?** [`phase2/plan.md` §16](./phase2/plan.md#16-future-work)
  (Phase 2) or [`phase3/README.md`](./phase3/README.md) (Phase 3b).

---

## 1. The one-paragraph mental model

A clinician (or a claims reviewer) asks a question in plain language. An **LLM agent
orchestrates** — it decides which tools to call and how to phrase the answer. It never decides
anything clinical or financial. Those decisions come from **deterministic services**: a rules
engine, a legacy adjudication core, and a clinical-safety rule engine. Every decision is
written to a FHIR server as an auditable artefact graph.

Two sentences carry most of the design:

> **AI explains and orchestrates; deterministic services decide.**
> **The legacy core is wrapped, not rewritten.**

If a change would violate either, it is almost certainly the wrong change.

## 2. The three phases

The repo contains three related systems. Phase 1 and Phase 2 share a FHIR server and a triage
service; Phase 3 shares neither — it has its own Postgres registry and touches `fhir-service`
not at all.

**Phase 1 — Prescription refill risk triage.** A clinician asks *"Check refill risk for Kristle
Mraz"*. The agent resolves the patient, pulls medications and allergies, and the triage service
flags drug-allergy conflicts.

```
mcp-agent ──▶ triage-service ──▶ fhir-service
 (LLM tool-use)   (drug-allergy rules)   (HAPI FHIR R4)
```

**Phase 2 — Prescription claim adjudication.** A claim is submitted, adjudicated against a
simulated legacy core plus benefit/prior-auth rules plus the *reused* Phase 1 triage service,
and the decision is persisted as FHIR artefacts and explained in plain language.

```
claims-agent ──▶ claims-service ──┬──▶ rxclaim-emulator  (legacy pricing + member SOR)
  (explains)      (façade + ACL   ├──▶ triage-service    (clinical safety — REUSED)
                   + rules engine) └──▶ fhir-service      (decision artefact graph)
```

**Phase 2 is strictly additive.** A plain `docker compose up` still starts only Phase 1. This
is a hard constraint (R9), enforced by a CI job — see [`testing-guide.md`](./testing-guide.md).

**Phase 3 — Provider search & referral.** A clinician asks *"find an endocrinologist near
27514 who's accepting new patients"*. `provider-search-agent` decomposes the free text, then
talks to `provider-mcp-server` over a **real MCP protocol connection** (not an in-process
function call) to resolve a specialty, search by proximity, and fetch full records — all
backed by real public NPPES/NUCC/Census data, never a paid aggregator or invented result.

```
provider-search-agent ──MCP──▶ provider-mcp-server ──HTTP──▶ provider-registry-service ──▶ Postgres
   (LLM client/host)          (protocol boundary,           (deterministic taxonomy +
                                no clinical logic)            proximity search — the only
                                                               service with business logic)

provider-curation-agent ──subprocess──▶ data/scripts/provider_ingest/ ──▶ Postgres
   (narrates ingestion runs,             (real NPPES/NUCC/Census pulls,
    non-authoritative)                    idempotent upserts)
```

**Phase 3 is also independent, but in a stronger sense than Phase 2:** it shares no service,
no database, and no Kong route with Phases 1/2 — everything new is internal-only (no edge
routes at all). It is also the first genuine MCP protocol boundary in the repo:
`provider-search-agent` discovers `provider-mcp-server`'s tools live via a real `tools/list`
call rather than hardcoding them, unlike `mcp-agent`'s in-process tool dispatch. Full detail:
[`phase3/design.md`](./phase3/design.md).

## 3. Request lifecycle of one claim

Follow this path once and the codebase stops being mysterious. Every step is in
`claims-service/src/main/java/com/payer/claims/`:

| # | Step | Package | What happens |
|---|---|---|---|
| 1 | HTTP intake | `api/` | JSON claim in; validation errors → 400 + `OperationOutcome` (never a denial — R17.6) |
| 2 | Idempotency check | `pipeline/` | `decisionId = "DEC-" + claimId`. Already decided? Return the prior decision, write nothing (R18.3) |
| 3 | Formulary lookup | `kb/` | `PayerKb` interface → `FilePayerKb` reads `data/payer-kb/`. This is the **C3 repository seam** (swap for Postgres without touching rules) |
| 4 | Patient resolution | `fhir/` | Member id → FHIR `Patient/member-{id}` |
| 5 | Clinical safety | `client/` | `HttpTriageClient` calls the reused triage service. **Fails closed** — see §5 |
| 6 | Rules evaluation | `rules/` | `RulesEngine` accumulates findings, then resolves by precedence |
| 7 | Legacy pricing | `client/` + `acl/` | Unless hard-denied: `HttpLegacyClient` sends a fixed-width record; `LegacyAdapter` (the ACL) parses the reply into domain types |
| 8 | Artefact build | `fhir/` | `FhirArtifactBuilder` composes `Claim` → `ClaimResponse` → `Task` → `Provenance` → `RiskAssessment` |
| 9 | Persist | `fhir/` | One atomic transaction bundle with conditional creates — all or nothing (R18) |

`domain/` holds the shared vocabulary (`CanonicalClaim`, `Finding`, `Outcome`, `RiskLevel`,
`Severity`, `FormularyEntry`). It depends on nothing else, and everything depends on it.

### Why the rules engine looks the way it does

It **accumulates then resolves** — it does not stop at the first match:

```java
// every applicable rule runs and emits a Finding …
if (!claim.coverageActiveOnDos())      f.add(Finding.of(..., Severity.DENY,   "coverage-inactive", ...));
if (formulary == null || !covered)     f.add(Finding.of(..., Severity.DENY,   "non-formulary", ...));
if (paRequired && !paOnFile)           f.add(Finding.of(..., Severity.PEND,   "prior-auth-required", ...));
// … then precedence decides the outcome: DENY > PEND > REVIEW > approved
```

This exists so a claim denied for three reasons can *say* all three. `reasons` is the winning
tier (what the member is told); `allFindings` is everything (what the explanation agent and the
audit trail get). Findings are sorted by a total order — `(severity, domain, ruleId)` — so the
same claim produces byte-identical output on every run and on any machine. Determinism is a
requirement, not a nicety (R17.4): a payer must be able to reproduce a decision months later.

## 3a. Request lifecycle of one provider search

The Phase 3 analogue, and the place to look if you're touching `provider-search-agent` or
`provider-mcp-server`:

| # | Step | Where | What happens |
|---|---|---|---|
| 1 | Spawn the server | `provider_search_agent/agent.py` | `StdioServerParameters(command=sys.executable, args=["-m", "provider_mcp"], env=...)` — a real child process, not a library import. `env` must be passed explicitly; the `mcp` SDK only inherits a safe-listed subset (`HOME`, `PATH`, …) — see §7 |
| 2 | Handshake + discovery | `agent.py` | Real MCP `initialize`, then `tools/list` — the agent learns the three tools' schemas at runtime, it does not hardcode them |
| 3 | Schema translation | `agent.py` | `inputSchema` → Anthropic's `input_schema` (field rename only, content untouched), then the normal tool-use loop |
| 4 | Tool call | `agent.py` → `provider_mcp/server.py` | Every call goes through `session.call_tool()` — real MCP `tools/call`, never an in-process function |
| 5 | Protocol → HTTP | `provider_mcp/registry_client.py` | Thin translation to `provider-registry-service`'s HTTP API. `provider-mcp-server` holds no clinical/business logic itself |
| 6 | Deterministic answer | `provider_registry/{taxonomy,location,registry}.py` | Fuzzy taxonomy match (`rapidfuzz`) or haversine proximity search, both against real ingested Postgres data — never an LLM call |
| 7 | Narration | `agent.py` system prompt | Every provider fact must trace to a literal tool result; a zero-result or ambiguous answer gets a clarifying question, never a substituted specialty or silently widened radius |

Three tools, all in `provider_mcp/schemas.py`: `resolve_specialty`, `search_providers_near`,
`get_provider`. Error taxonomy (design.md §8.4): `validation_error`/`not_found`/
`upstream_unavailable` set `isError: true`; a zero-result search is a normal `200` the agent
must report honestly, not paper over.

`provider-curation-agent` is a separate, simpler lifecycle: it shells out to
`data/scripts/provider_ingest/`'s deterministic scripts, then reads the **authoritative**
result back from Postgres (`ingestion_runs` + `anomaly_flags`) — never from subprocess stdout
text — before narrating it. It is not an MCP client; ingestion is batch/offline, out of the MCP
boundary the search agent uses for queries.

## 4. Repo map

| Path | What it is | Language |
|---|---|---|
| `fhir-service/` | HAPI FHIR JPA R4 server (H2 local, Neon PostgreSQL cloud) | Java 21 |
| `triage-service/` | FastAPI drug-allergy rule engine → FHIR `RiskAssessment` | Python |
| `mcp-agent/` | Phase 1 Anthropic tool-use CLI orchestrator (**no clinical logic**) | Python |
| `claims-service/` | Phase 2 adjudication façade: ACL + rules + Decision Contract | Java 21 |
| `rxclaim-emulator/` | Simulated legacy IBM i / RxClaim core (DDS records, DB2/SQL400 tables, `ADJRXCLM`) | Java 21 |
| `claims-agent/` | Phase 2 explanation agent (**non-authoritative**) | Python |
| `client/clinical/` | Domain-abstracted FHIR client library (shared: agent + triage) | Python |
| `client/platform/` | Direct FHIR-server integration tests | Python |
| `gateway/` | Kong config — KIC (Phase 1, GKE) and DB-less (Phase 2) | YAML / Helm |
| `data/payer-kb/` | Curated formulary / PA / plan fixtures | CSV / JSON |
| `data/reference/` | Reference-data source catalog (CMS Part D, ACA/QHP) + fetch scripts | Python |
| `data/scripts/` | Synthea generation + demo seeders | Python |
| `data/scripts/provider_ingest/` | Real NPPES/NUCC/Census ETL → Phase 3's Postgres registry | Python |
| `e2e/` | Golden-path tests against a live stack | Python |
| `provider-registry-service/` | Phase 3's **only** service with business logic: taxonomy match + proximity search over real provider data | Python |
| `provider-mcp-server/` | The real, hand-built MCP server — first genuine protocol boundary in the repo | Python |
| `provider-search-agent/` | The real MCP client/host; discovers tools live, no `--no-llm` fallback | Python |
| `provider-curation-agent/` | Phase 3's non-authoritative ingestion-narration agent (mirrors `claims-agent`) | Python |
| `<service>/infra/main.tf` | Per-service Cloud Run **stubs** — `claims-service`, `rxclaim-emulator`, and all four Phase 3 services have one; `infra/terraform/` is a **root module composing the Phase 3 stubs only** (M7) — Phase 1/2 still has no root module and nothing has been applied anywhere ([gap](./phase2/plan.md#6-workstreams--milestones)) | HCL |
| `epic-emulator/`, `athena-emulator/` | Placeholders — EHR-specific customisations, not yet implemented | — |

### Boundaries that are deliberate

- **`mcp-agent` and `claims-agent` are separate.** They share no clinical logic. Merging them
  would couple Phase 1 to Phase 2 and break R9.
- **`provider-search-agent` and `provider-curation-agent` are separate**, for the same reason —
  querying and ingestion-narration are different concerns with different authority levels
  (decisions.md P1).
- **`client/clinical` speaks clinical domain terms, never raw FHIR bundles.** Callers ask for
  "this patient's active medications", not for a search URL.
- **`client/clinical` and `client/platform` serve different audiences** and must not modify each
  other's code.
- **The Java services never depend on the Python client**, and vice versa. They talk over HTTP.
- **`rxclaim-emulator` has no published port.** It is reachable only inside the compose network,
  mirroring the cloud `ingress=internal` posture. Everything goes through `claims-service`.
- **`provider-mcp-server` holds no clinical/business logic.** It is a thin MCP-to-HTTP
  translator in front of `provider-registry-service`, the same "call the deterministic service,
  don't import it" pattern `mcp-agent` uses for `triage-service`.
- **The MCP protocol boundary must not be bypassed.** `provider-search-agent` must reach
  `provider-mcp-server` only through `session.call_tool()` — never an in-process import of
  `provider_mcp`'s handlers. The whole point of Phase 3 is a genuine client/server split; a
  shortcut import would quietly turn it back into `mcp-agent`'s old in-process dispatch.

## 5. Invariants — break these and something important breaks

**R9 — Phase 1 independence.** Phase 2 is additive. `docker compose up` with no profile must
start exactly `fhir mcp-agent triage`. CI asserts this literally.

**R17 — The Decision Contract.** Deterministic, accumulate-then-resolve, precedence
`DENY > PEND > REVIEW > approved`, stable `(severity, domain, ruleId)` ordering. No wall-clock,
no map-iteration order, no set ordering may reach the output.

**R18 — Idempotency.** Every artefact carries the `decisionId`. Resubmitting a claim returns the
prior decision and writes nothing. Persistence is one atomic transaction — never partial.

**The clinical-safety check fails closed.** This one is subtle and worth internalising.
`RiskLevel.UNKNOWN` means *"the check could not be completed"* and is deliberately distinct from
`LOW` (*"we checked and it is safe"*). Triage down, member unresolvable, unrecognised response —
all yield `UNKNOWN`, which the rules engine maps to **PEND** (a human decides), never approve.

The reason this is a rule rather than a preference: the failure is **silent**. A system that
cannot see a drug-allergy conflict reports no conflict — which looks exactly like a safe
patient. This is not hypothetical; it is what actually happened here. The safety check was dead
for several milestones, every demo path stayed green, and nothing failed. If you add another
external check, decide up front what its *unavailable* state means, and make that state
unrepresentable as "fine".

**The agent is non-authoritative (R17.8).** `claims-agent` explains decisions. It never makes,
alters, or second-guesses one. If the agent is down, adjudication is unaffected.

**The ACL is the only place legacy formats exist.** Fixed-width records, offsets, and legacy
status codes live in `acl/` and `rxclaim-emulator/`. If a DDS offset leaks into `rules/`, the
anti-corruption layer has failed at its one job.

**Phase 3 — agents never fabricate a provider fact.** `provider-search-agent`'s system prompt
requires every NPI, name, address, or specialty it states to be literally present in an MCP
tool result. This is not just a style rule: the `test_groundedness_eval.py` test (M6) exists
specifically to catch a regression here — it independently re-fetches every NPI an agent
transcript mentions and asserts it resolves to a real record, including a zero-match query
asserted to produce zero fabricated NPIs.

**Phase 3 — `npi_status` defaults to excluding deactivated providers.** NPPES never reports a
deactivated status in practice (every sampled record, hundreds, came back `"A"`), but the
schema and the search path assume it can happen and filter it out by default; `GET
/v1/providers/{npi}` still returns a deactivated record explicitly rather than a bare 404, so a
caller with a stale NPI sees *why*, not an error indistinguishable from a data problem.

**Phase 3 — the MCP protocol boundary is not a formality.** `provider-mcp-server` is the
repo's first genuine client/server split (vs. `mcp-agent`'s in-process tool dispatch). Tool
schemas are flat objects, not `oneOf` unions — see §7 — and cross-field validation
(`location` needs exactly one of `zip` or `lat`+`lon`) is enforced downstream in
`provider-registry-service`'s Pydantic models, not in the MCP schema itself.

## 6. Local development loop

```bash
# Python packages (editable installs + test tooling)
python -m pip install -e "client/clinical[dev]" -e "triage-service[dev]" -e "mcp-agent[dev]" -e "claims-agent[dev]" \
  -e "provider-registry-service[dev]" -e "provider-curation-agent[dev]" -e "provider-mcp-server[dev]" -e "provider-search-agent[dev]"

# Java services
mvn -f claims-service/pom.xml test          # fast: unit + contract tests, no stack needed
mvn -f claims-service/pom.xml package       # build the jar

# The whole Phase 2 stack
docker compose --profile phase2 up --build -d
python3 data/scripts/seed_claims_demo.py    # seeds FHIR fixtures + drives the golden paths

# The whole Phase 3 stack (own Postgres — no fhir-service involved, self-contained)
docker compose --profile phase3 up --build -d postgres provider-registry
docker compose --profile phase3 run --rm -T provider-curation-agent --states NC --no-llm  # seeds real data; -T: see §7
docker compose --profile phase3 run --rm provider-search-agent --query "find an endocrinologist near 27514"
```

Running a Java service directly against the compose stack (faster than rebuilding the image on
every change):

```bash
java -jar claims-service/target/claims-service-0.1.0.jar \
  --payer-kb.dir=$PWD/data/payer-kb \
  --rxclaim.base-url=http://localhost:8091 \
  --triage.base-url=http://localhost:8001 \
  --fhir.base-url=http://localhost:8080/fhir
```

Ports: FHIR `8080`, triage `8001`, claims-service `8090`, rxclaim-emulator `8091` (internal
only), Kong proxy `8000` (`gateway` profile), Phase 3 Postgres `5432`, provider-registry-service
`8002`. `provider-mcp-server` has no port — it's spawned as a stdio child process, never a
standing compose service.

## 7. Traps that have already cost hours

**Ambient environment variables leak into services and tests.** `SPRING_DATASOURCE_URL`,
`NEON_*`, and `FHIR_GATEWAY_URL` may be set in your shell. `fhir-service` tests then boot
against a live database and fail on auth — an env problem wearing a test-failure costume. Unset
them before `./mvnw verify`. Likewise `FHIR_GATEWAY_URL=localhost:8080/fhir` on the host leaks
into the triage *container*, where `localhost` is the container itself and nothing answers. Pass
the compose-network address explicitly:
`FHIR_GATEWAY_URL=http://fhir:8080/fhir docker compose up -d`.

**HAPI rejects purely numeric client-assigned ids.** `PUT Patient/000000009` → 400. This is why
demo patients use `member-000000009` — the prefix makes the logical id non-numeric.

**FHIR search is index-backed and lags; reads are immediate.** A resource you just wrote is
readable by id straight away but may not appear in a search for a beat. Member→patient
resolution therefore uses `read Patient/member-{id}`, not an identifier search. If you find
yourself adding a sleep before a search, prefer a read.

**The demo FHIR server is in-memory.** `jdbc:h2:mem:hapi` — restarting the `fhir` container
wipes every patient. Any test or demo that needs clinical data must seed it. The e2e suite does
this itself in `e2e/conftest.py`; don't assume a warm server.

**uvicorn is HTTP/1.1-only.** Java clients that default to HTTP/2 attempt an h2c upgrade against
it, and the POST body silently vanishes — FastAPI answers `422 body required` while your code
looks correct. `HttpTriageClient` pins `HttpClient.Version.HTTP_1_1`. If you add another Java →
Python call, do the same.

**Spring DI and multiple constructors.** `FilePayerKb` has two; the `@Value` one needs
`@Autowired` or the context fails at runtime, not compile time. Unit tests won't catch it — only
actually booting the service will.

**Live Claude mis-serializes `oneOf`-typed MCP tool parameters.** Found in Phase 3 M6:
`provider-mcp-server`'s original `search_providers_near` schema used a `oneOf` union for
`location` (`{zip}` vs `{lat, lon}`). Live Claude reliably serialized the whole thing as a JSON
*string* instead of a native object — reproduced 12/12 consecutive attempts, not a flake. Fixed
by flattening to a plain object and pushing the "exactly one of zip, or lat+lon" rule into a
downstream Pydantic validator in `provider-registry-service`. If you're about to add a `oneOf`
to any tool schema in this repo — MCP or otherwise — flatten it instead. See
[[llm-tool-schema-oneof-unreliable]], design.md §14, decisions.md P17.

**`docker compose run` silently swallows stdout without `-T`.** In this sandbox (and possibly
others), `docker compose run --rm provider-curation-agent ...` without `-T` produces no visible
output even though the container ran successfully — it allocates a pseudo-TTY that the
non-interactive harness doesn't drain. Always pass `-T` when scripting a Phase 3 CLI agent
non-interactively. If output still doesn't show up, `docker run -d ... && docker logs
<container>` is a reliable fallback that sidesteps the issue entirely.

**Identically-named `tests/test_*.py` files collide across packages.** This repo runs pytest
with `--import-mode=importlib` and every package has its own `tests/__init__.py`. Two files
with the *same name* in different packages (e.g. `claims-agent/tests/test_tools.py` and an
originally-identically-named file under `provider-curation-agent/tests/`) resolve to the same
dotted module name and silently collide in `sys.modules` — one file's tests run twice, the
other's never run, **with a passing exit code throughout**. Before adding any new `tests/`
file, check it's unique repo-wide: `find . -path '*/tests/test_*.py' -printf '%f\n' | sort |
uniq -d`. See [[pytest-test-filename-collision]], design.md §14, decisions.md P15.

**A dropped character in a taxonomy code produces a silent false negative, not an error.**
Found in Phase 3 M6: live Claude once transcribed a NUCC taxonomy code between tool calls with
a character dropped, producing a plausible-looking but wrong code. `search_providers_near`
correctly found zero matches for the (nonexistent) code and returned a normal 200 — so nothing
*failed*, the agent just confidently reported "no providers found" for a specialty that had
plenty. Fixed with a verified format pattern (`^[0-9A-Z]{9}X$`, checked against all 883 real
NUCC codes) rejecting malformed codes before they reach the search. The general lesson: a
zero-result 200 downstream of free-text-derived input can be masking a malformed-input bug
upstream, not an honest "no matches."

## 8. Adding things

**A new adjudication rule.** Add the check to `RulesEngine.evaluate` so it emits a `Finding`
with a `Severity`; add its domain to `DOMAIN_ORDER` if new (this fixes its position in the
deterministic sort). Add a golden test per rule *and* a combination test that exercises
precedence against an existing rule. Never return early — accumulate.

**A new formulary attribute.** Extend `FormularyEntry`, the `data/payer-kb/` fixture and its
generator script, then the rule that consumes it. Fixtures are governed (R19): a changed
expected decision needs its own commit with a rationale.

**A new downstream service call.** Put the transport in `client/` behind an interface, keep
domain types out of the wire format, and decide explicitly what *unavailable* means (see §5).
Write a contract test with a stub HTTP server — not a mock. See
[`testing-guide.md`](./testing-guide.md) for why that distinction matters here.

**A new FHIR artefact.** Add it to `FhirArtifactBuilder`, link it to the decision (`decisionId`
identifier + a reference into the graph), and include it in the single transaction bundle. Add
it to the R18.2 audit-graph assertions.

**A new MCP tool (Phase 3).** Define its schema in `provider_mcp/schemas.py` as a **flat
object** (no `oneOf` — see §7), add the handler in `provider_mcp/server.py` translating to a
`provider-registry-service` HTTP call, and set `isError: true` only for the three real error
classes (`validation_error`/`not_found`/`upstream_unavailable`) — a zero-result search is a
normal 200. `provider-search-agent` needs no code change to pick it up: it discovers tools live
via `tools/list`. Add it to design.md §8.3's tool contract table.

## 9. Git workflow and the two worktrees

This project intentionally uses **two Git worktrees**. Treat them as independent environments:

- `/workspaces/fhir-agent` — branch `main`. Application code, features, tests, PRs.
- `/workspaces/.ai-chat-history` — branch `ai-chat-history`. The AI conversation archive and its
  tooling. Never merged into `main`.

For application code: never commit to `main`; branch and open a PR; never merge your own branch.
Before any Git write, be explicit about **current worktree, current branch, intended target
branch**. Full rules — including the archive's separate workflow — are in
[`../CLAUDE.md`](../CLAUDE.md), mirrored for Cline in `.clinerules`.

## 10. Where to continue

**Phase 2:** Milestones M0–M7 are complete; the system runs end to end locally. The prioritised
backlog — including the live cloud deploy (Phase 2b), the circuit breaker, the Postgres swap
behind the C3 seam, and NCPDP reject-code fidelity — is in
[`phase2/plan.md` §16](./phase2/plan.md#16-future-work).

**Phase 3:** Milestones M1–M7 are complete; the system runs end to end locally with real
public provider data. Everything left is **Phase 3b** — live GCP deployment (`terraform apply`
+ `deploy-phase3.sh`, neither ever run against real cloud credentials), a full-state ingestion
run (only NC/CA/MT are curated today), and the stdio→network transport switch
`provider-mcp-server` would need to run as a standing service. See
[`phase3/README.md`](./phase3/README.md) and [`phase3/design.md` §13.1](./phase3/design.md).

Design rationale, if you need to know *why* rather than *what*:
[`phase2/requirements.md`](./phase2/requirements.md) / [`phase2/plan.md`](./phase2/plan.md) for
Phase 2, [`phase3/prd.md`](./phase3/prd.md) / [`phase3/design.md`](./phase3/design.md) /
[`phase3/decisions.md`](./phase3/decisions.md) for Phase 3.
