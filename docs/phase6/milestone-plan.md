# Phase 6 — Agent Platform Hardening + Overall Observability — Milestone Plan

> Sequencing, deliverables, and status for the requirements in [`prd.md`](./prd.md) and the
> architecture in [`design.md`](./design.md). **This is a separate document from `design.md`**,
> a deliberate departure from Phase 3/4's consolidation convention — see
> [`decisions.md` H23](./decisions.md) for why.
>
> **Status is stated once, canonically, in [`README.md`](./README.md).** The Status column
> below is the per-milestone record.

## Order and dependency

Order is by dependency, **not** by the topic numbering in [`design.md` §2](./design.md#2-the-five-topics):

| # | Status | Milestone | Topic(s) | Depends on |
|---|---|---|---|---|
| **M1** | 🔜 Next up | Output Contract & Fail-Closed Enforcement | 5 | — |
| **M2** | ⏳ Not started | Observability, Platform-Wide | 2, 3 | M1 |
| **M3** | ⏳ Not started | Context, Memory & Session Transport | 1, 4 | M2 |
| **M4** | ⏳ Not started | Deploy Resilience & Cost Control | 2 | M2, M3 |
| **M5** | ⏳ Not started | Provider Abstraction & Cross-Model Follow-ups | 4 | M1, M3 |
| **M6** | ⏳ Not started | Policy, Knowledge & Judge | 5 | M1, M5 |
| **M7** | 📋 Planned, not started | Strong Model in Production | 4 | M5 |

**Minimal-viable-cut re-examination is deliberately deferred to the end of M2**, not decided now
([`decisions.md` H23](./decisions.md)). M2's scope grew substantially once it took on closing
Phase 2's R15 platform-wide (H16) — whether "M1+M2" is still a sensible minimal cut, or whether
M2 itself needs splitting, gets decided once M2's real size is known, not guessed here.

---

## M1 — Output Contract & Fail-Closed Enforcement

**Short story:** Every agent turn ends in one of a small set of enum outcomes, code-validated,
with `REVIEW` as the fail-closed catch-all — and a data-layer guard makes sure a broken or
unclear triage response can never quietly look like "safe" in the first place.

**Long story:** Two paired deliverables (see [`design.md` §4.1](./design.md#41-output-safety--m1)
for the full design):

- **Output side** — a tool-with-enum-output parameter on the agent's final answer, purpose-built
  for refill triage, reusing `REVIEW` as the shared platform term for the fail-closed case
  ([`decisions.md` H10](./decisions.md)). Code-validates the model's answer against the enum —
  schema alone isn't trusted. Anything off-contract fails closed to `REVIEW`. The contract's
  shape is standalone, not mirroring `OperationOutcome` or `{error_type, message}`
  ([`H21`](./decisions.md)).
- **Input side** — a Python wrapper around the `triage-service` call, mirroring
  `HttpTriageClient.java`'s precedent ([`H18`](./decisions.md)): any non-2xx, timeout, transport
  failure, or unrecognized risk code maps to an explicit `UNKNOWN` sentinel the enum gate is
  required to treat as `REVIEW`, never safe. Closes the audited gap where `mcp-agent` currently
  bypasses the only real fail-closed precedent in this codebase.
- **Bundled stopgap:** a conservative fixed cap on REPL message-list growth, landing here because
  this milestone already touches the agent loop — not the real M3 budget policy, just closing
  the current zero-bound risk early ([`prd.md` R9`](./prd.md)).
- **Testing:** adversarial tests against a local/weak model (the standing rule starts here, not
  at M5 — [`H11`](./decisions.md)); real HTTP-stub-server tests for the triage-client wrapper
  (the Java precedent's own stub-server rationale applies directly, not object-mocked
  `httpx.post`).
- **Package landing:** `agent-platform/`'s first two modules — the enum-gate/output-validation
  logic and the fail-closed triage-client wrapper.

## M2 — Observability, Platform-Wide

**Short story:** Build the OTel/OTLP tracing-and-metrics backbone for the agent tier, and use the
same architecture to actually close Phase 2's long-open R15 gap in `claims-service`/
`rxclaim-emulator` — designed once, instrumented everywhere it's missing.

**Long story:** The heaviest milestone in the build order — flagged explicitly, since what began
as "instrument one Python CLI agent" now spans four to five services across two languages (see
[`design.md` §4.2](./design.md#42-observability--m2)). Two coordinated tracks under one
architecture:

- **Agent tier:** `gen_ai.*` semantic-convention spans — one trace per agent run, spans per model
  call and per tool call — traceID propagated into the `triage`/`fhir` calls M1's wrapper already
  makes.
- **Java tier:** standard HTTP/DB spans + Micrometer metrics in `claims-service` and
  `rxclaim-emulator`, closing R15 ([`decisions.md` H16](./decisions.md)). `fhir-service` gets its
  missing trace-propagation piece added too — it already has metrics from Phase 1, not tracing.
- **One shared OTLP pipeline** ([`H22`](./decisions.md)), pointed at local Jaeger/Grafana today,
  repointable to Cloud Trace/Managed Prometheus later via config only.
- **PHI redaction designed in from the start** — span-attribute scrubbing mirroring
  `provider-registry-service`'s `sanitize_location()` precedent, extended to fix Kong's
  `file-log` plugin's live raw-URI PHI leak ([`H17`](./decisions.md)) — in scope because this
  milestone's charter is now platform-wide, not agent-tier-only. That specific gateway-config
  change gets its own explicit go-ahead before deploying, separate from general approval for M2.
- **Phase 2 cross-reference, without duplication or hardcoded numbering:**
  `docs/phase2/decisions.md`'s `C5` entry gets its status updated once this ships, worded as
  "closed by a later platform-wide observability effort" — no citation of a specific Phase 6
  milestone number, so it can't go stale if this phase's own numbering shifts.
- **Testing:** trace/span assertions against the local Jaeger backend in CI; PHI-redaction unit
  tests asserting raw identifiers never appear in exported span attributes.
- **Custom attribute taxonomy + configurable depth** ([`decisions.md` H24–H27](./decisions.md)):
  every span gets `fhir_agent.layer`/`.component` (real OTel `code.function.name` alongside a
  custom namespace for architectural meaning — full dictionary in
  [`telemetry-schema.md`](./telemetry-schema.md)), a two-level `TELEMETRY_VERBOSITY` setting
  (`standard` default enriches existing spans only; `detailed` adds per-rule spans in
  `triage-service/rules.py`, the one boundary judged worth the extra volume), and the trace ID is
  surfaced back to the caller (`X-Trace-Id` header / CLI output), not left inside span context
  only Jaeger can read.
- **End-of-milestone checkpoint:** the minimal-viable-cut question (§Order above) gets decided
  here, once M2's actual delivered size is known.

## M3 — Context, Memory & Session Transport

**Short story:** Give the agent a real session concept — Postgres-backed, behind a thin HTTP API
— plus a token-budget policy actually set from M2's real telemetry instead of guessed.

**Long story:** (full design: [`design.md` §4.3](./design.md#43-memory--session--m3--implemented))

- **Transport:** `mcp-agent/src/agent/api.py`, a thin FastAPI wrapper around `run_query` —
  `POST /sessions`, `POST /sessions/{id}/query`, `GET /health`, matching `triage-service`'s
  convention including `X-Trace-Id` headers and a `FastAPIInstrumentor` server span
  ([`decisions.md` H14](./decisions.md)). New opt-in `phase6` docker-compose profile; the
  existing `mcp-agent` CLI service is untouched ([`H33`](./decisions.md)).
- **Store:** a dedicated Postgres instance (`agent-db`), following
  `provider-registry-service`'s connection-pool/`schema.sql`/`init_db.py` convention exactly.
  `messages` stored as JSON text (Anthropic SDK content blocks are Pydantic models needing
  `model_dump(mode="json")` first — confirmed live, not assumed) ([`H28`](./decisions.md)).
- **Memory policy, three axes kept separate:** (1) per-conversation token budget —
  `TOKEN_BUDGET = 40_000`, grounded in two real measured queries (5,404 / 5,381 tokens, read
  from live Jaeger spans, not guessed) ([`H29`](./decisions.md)); compaction drops the single
  oldest turn per call, self-correcting rather than precise-in-one-shot
  ([`H30`](./decisions.md)) — this fully replaces M1's `MAX_REPL_TURNS` stopgap, which is now
  removed from `agent.py`; (2) concurrent-session count — deferred to M4; (3) cross-session
  persistence — the Postgres store itself. Re-fetch-don't-recall enforced throughout — the store
  persists conversation *history*, never a cached clinical read.
- **Backward compatibility:** `run_query`'s return arity is unchanged (still a 2-tuple) — the
  new token count and trace ID are handed back via an optional `stats` dict, so every one of
  M1/M2's existing call sites (across `agent.py` and every test file) stays valid unmodified
  ([`H31`](./decisions.md)).
- **Graceful degradation:** the CLI (`interactive_mode`/`non_interactive_mode`) falls back to
  in-memory-only sessions when `DATABASE_URL` isn't set, mirroring `claims-agent`'s own
  no-API-key fallback — the zero-setup CLI experience is unchanged by default
  ([`H32`](./decisions.md)). The HTTP transport has no such fallback and 503s instead, since an
  HTTP "session" with no persistence isn't a session.
- **Package landing:** `agent-platform/` gains `session_store.py`, `context_budget.py`,
  `init_db.py`, `schema.sql` — reusable by `claims-agent` without a rebuild.
- **Testing:** `agent-platform` — 6 real DB-backed session-store tests (self-skip when Postgres
  is unreachable, same convention as `provider-registry-service`) run against a live Postgres,
  including the Anthropic-SDK-content-block round-trip; 6 pure-logic compaction tests.
  `mcp-agent` — 6 API-layer tests (mocked store/client), 4 compaction-integration tests (a real
  bug caught here: the initial test fixture only had one prior turn, and `compact()` correctly
  refused to drop it — the test was wrong, not the implementation), 6 session-persistence/
  fallback tests. **Live end-to-end smoke test**: created a real session over HTTP, asked two
  real questions (HIGH-risk and LOW-risk), confirmed in Postgres that the session grew to 14
  messages with a correctly-updated token count — not just asserted in mocked tests.
- **A real bug found and fixed while smoke-testing, not left in**: `api.py`'s `trace_id` field
  initially always returned `null` — `current_trace_id()` was being called *after* `run_query`'s
  root span had already closed. Fixed by capturing the trace ID into the `stats` dict while the
  span is still current, the same mechanism as the token count.
- **Deferred, deliberately not built this milestone:** multi-session *concurrency* testing (the
  API can now be called concurrently, but load/concurrency behavior itself is M4's job, tied to
  its rate/cost limiter); a live-local-model run confirming compaction doesn't disorient a
  weaker model's grip on multi-turn context — the mechanism is verified correct by the unit/
  integration tests above, but a live Ollama-driven multi-turn conversation wasn't separately
  run for this milestone.

## M4 — Deploy Resilience & Cost Control

**Short story:** Protect the paid LLM API call with a hybrid rate/cost limiter — alert-only for
real clinical traffic, hard-block only on runaway/bug-driven spend — plus a circuit breaker sized
specifically for that one external dependency, documented as a deliberate divergence from this
repo's usual "no breaker" convention.

**Long story:** (full design: [`design.md` §4.4](./design.md#44-deployment-resilience--cost--m4--implemented))

- **Rate/cost posture:** hybrid ([`decisions.md` H19](./decisions.md)) — `RateCostLimiter`
  tracks tokens in a sliding one-minute window; alert-only past `alert_tokens_per_minute` (traffic
  still allowed through), hard block via `CostLimitExceededError` past
  `hard_backstop_tokens_per_minute`. Both grounded in M3's real per-query measurement
  (~5,400 tokens), not arbitrary numbers: alert ≈ 10 queries/minute, hard backstop ≈ 100
  queries/minute ([`H36`](./decisions.md)).
- **Circuit breaker:** `CircuitBreaker` wraps the LLM API call specifically (closed → open →
  half-open → closed, default 5 consecutive failures / 30s reset, trips on any
  `anthropic.APIError`), diverging explicitly and on the record from `HttpTriageClient.java`'s
  "no breaker" precedent ([`H20`](./decisions.md), [`H35`](./decisions.md), [`H37`](./decisions.md))
  — the LLM API's external, metered, cost-bearing risk profile is materially different from the
  internal service-to-service calls that precedent was written for.
- **Fail-closed, not a crash:** both protections raise a dedicated exception
  (`CircuitOpenError`/`CostLimitExceededError`) that `agent.py` catches at the one call site and
  maps straight onto M1's `AgentDecision.REVIEW` sink ([`H34`](./decisions.md)) — an LLM call that
  couldn't be attempted at all is exactly as safety-relevant as a risk check that came back
  UNKNOWN. A single failure *below* the breaker's threshold still propagates as before M4; `api.py`
  now catches that specific case and returns a clean `502` — a real gap found live-testing with an
  intentionally invalid API key (previously an ungraceful `500`).
- **Concurrent-session-count scaling** (deferred from M3): resolved as a bounded concurrency
  limiter in front of `query_session` specifically, not a session-count cap — what actually
  threatens the API key's rate limits is calls in flight, not sessions in Postgres. Bounded wait
  with a deadline (default 10 slots, 5s wait, then `503`), not an unbounded queue
  ([`H38`](./decisions.md)).
- **Grafana dashboards:** LLM token/cost usage is now a real Prometheus counter/histogram at
  `mcp-agent-api`'s new `/metrics` (`fhir_agent_llm_tokens_total`, `fhir_agent_llm_calls_total`,
  `fhir_agent_llm_call_duration_seconds`, `fhir_agent_rate_limit_alerts_total`) — closing the gap
  M2 deliberately deferred ([`decisions.md` H27](./decisions.md), [`H39`](./decisions.md)),
  scraped the same way the Java services' `/actuator/prometheus` already is. A provisioned
  dashboard (`observability/grafana/provisioning/dashboards/llm-cost-rate.json`, 4 panels) sits
  alongside M2's trace/span panels.
- **Testing:** `agent-platform` — 12 unit tests for `CircuitBreaker`/`RateCostLimiter` in
  isolation. `mcp-agent` — 8 chaos-style integration tests through `run_query` (repeated real
  `anthropic.APIError` subtypes tripping the breaker, hard-backstop blocking, recovery after a
  trip, a metrics-increment check), plus 4 API-layer tests (concurrency-limit `503`, slot release,
  the `502` regression, `/metrics` content). **Live end-to-end**: with an intentionally invalid
  `ANTHROPIC_API_KEY` and the breaker threshold lowered to 2, two real calls against the live
  Anthropic API returned clean `502`s, the breaker opened, and the third call returned a real
  `200` with a `REVIEW` decision and trace ID — confirmed via curl against the running
  `phase6`+`observability` docker-compose stack, not mocks. Restoring a real key recovered normal
  HIGH-risk/DISPENSE-path operation. Grafana's dashboard API and Prometheus's `/api/v1/targets`
  both confirmed live.

## M5 — Provider Abstraction & Cross-Model Follow-ups

**Short story:** Formalize the provider seam so Llama/DeepSeek/local models become config, not
code — making official what M1's local-LLM testing already forced into informal existence. Built
once during M5, then **substantially reworked after a design-review pass** (documented below and
in [`decisions.md` H45-H51](./decisions.md)): the default flipped from Anthropic to self-hosted
Ollama, three provider identities replaced two, and model choice became a real per-session
decision instead of a process-wide constant.

**Long story:** (full design: [`design.md` §4.5](./design.md#45-multi-provider--m5--implemented-reworked-post-review))

- **Three identities, two implementations** ([`decisions.md` H45](./decisions.md), superseding
  H4's "exactly two adapters, Anthropic is the default"): `"anthropic"` (native, used completely
  unwrapped — its response shape already matches what `run_query` expects,
  [`H40`](./decisions.md)), `"ollama"` (self-hosted, the only identity ever selected
  automatically), and `"openai_compatible"` (any other OpenAI-shaped endpoint — DeepSeek API,
  OpenRouter, Groq, a self-hosted vLLM box — never a default). `"ollama"`/`"openai_compatible"`
  share one adapter class; the split exists to answer *who hosts the inference*, the property
  that actually matters for PHI, not which wire protocol is spoken.
- **The default flipped to `"ollama"`** ([`H45`](./decisions.md)) — self-hosted, free, and (the
  actual, primary rationale) PHI never leaves this host when nothing is configured. A present
  `ANTHROPIC_API_KEY` does **not** select Anthropic on its own ([`H46`](./decisions.md)) — only an
  explicit `LLM_PROVIDER` does, since a key's presence alone is too easily accidental to trust
  with that decision. **Disclosed, never silently substituted**: the CLI prints a one-time message
  when the default was actually used, gated on `sys.stdin.isatty()` (that signal only decides
  whether to show the message, never which model runs); the HTTP transport has no TTY concept and
  shows nothing — documented, accepted.
- **`DEPLOYMENT_ENV=production` guardrail** ([`H47`](./decisions.md)): an unset `LLM_PROVIDER`
  becomes a loud error instead of a silent `ollama` fallback when set — a minimal rail pending the
  fuller design in **M7** (below), not a complete environment-tier system yet.
- **Discovery, opt-in and all-or-nothing** ([`H48`](./decisions.md)): `list_anthropic_models()`/
  `list_ollama_models()`/`list_openai_compatible_models()` in `agent_platform.providers`; CLI
  `--list-models`/`--provider`/`--model`; API `GET /models?provider=...`. Never called unless
  explicitly requested; once requested, succeeds or raises — no partial results, no fallback logic.
- **Model choice is per-session/per-process** ([`H49`](./decisions.md)): `agent_sessions` gained
  persisted `provider`/`model` columns (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, live-confirmed
  against a real pre-existing table). `build_client_for(provider, model)` rebuilds the exact
  client for a resumed session or any API query — reading infra config (base URL, API key) from
  the *current* environment only, never a persisted secret.
- **Conversation-history translation** — the actual hard engineering problem — written and tested
  for real, not assumed: `_to_openai_messages()`/`_to_openai_tools()` outbound,
  `_from_openai_response()` inbound, including turning our own `tool_result` entries into separate
  OpenAI `"tool"`-role messages and falling back to an empty tool-call input on malformed JSON
  from a weak model ([`H43`](./decisions.md)) rather than raising.
- **Resilience made provider-agnostic** ([`H42`](./decisions.md)): M4's circuit breaker trips on
  `httpx.HTTPError` too, not just `anthropic.APIError` — otherwise M4's protections would silently
  not cover the ollama/openai_compatible path at all.
- **`gen_ai_system` is explicit** ([`H41`](./decisions.md)), not inferred by `isinstance` — caught
  during implementation when a type-based check mislabeled every existing fake-client test.
- **Testing:** `agent-platform` — 30 unit tests: the translation layer, `build_llm_client()`'s
  full 3-identity/guardrail env var contract, `build_client_for()`, and discovery functions (mocked
  HTTP), no network. `mcp-agent` — 2 **live** integration tests against a real local Ollama
  (`llama3.2:1b`), plus 12 session-persistence/disclosure/API tests. **Ollama is now a required
  test dependency for the live tests specifically** ([`H50`](./decisions.md)) — hard-fail
  (`pytest.fail`), not self-skip, via a shared session-scoped fixture that also pulls the model on
  demand if it isn't present. The large body of fake-client agent-loop tests deliberately stays
  fake-client-only, untouched by Ollama's availability. CI: `~/.ollama/models` cached across runs;
  a dedicated job fails the build if the LLM provider env var is found pinned to a paid/
  third-party value anywhere in CI config — enforced technically, not left to code review
  ([`H50`](./decisions.md)). `agent-platform/tests` now runs in CI too (a pre-existing gap, fixed
  opportunistically) as its own separate pytest invocation — combining it with `mcp-agent/tests`
  in one process collides on both packages' `tests/conftest.py` under `--import-mode=importlib`
  ([`H51`](./decisions.md), a real error hit and fixed during this rework).
- **A real bug found live, not by any mocked test**: running the full CLI end to end against
  real FHIR/triage services and the real Ollama model, `llama3.2:1b` omitted a required tool
  argument entirely; `tools.py`'s `execute_tool` raised an uncaught `KeyError`, aborting the query
  instead of reaching the intended `RISK_UNKNOWN`/`REVIEW` fail-closed path. This gap predates M5
  (present since M1) but no test — mocked or live — had exercised a model weak enough to trigger
  it until now. Fixed with the same structured-error convention `assess_refill_risk` already uses
  elsewhere in that file ([`H44`](./decisions.md)); re-ran the same live CLI query afterward and
  confirmed a clean `REVIEW` decision instead of a crash.
- **Live-validated end to end**: CLI with no `LLM_PROVIDER` set ran a real query against real
  FHIR/triage and the real self-hosted model, zero API key required; `--list-models ollama`
  printed the real locally-pulled models; `DEPLOYMENT_ENV=production` with no `LLM_PROVIDER`
  refused to start with the documented error; `--provider anthropic --model claude-sonnet-4-5`
  correctly used real Claude; a session explicitly pinned to `anthropic` via the live API
  correctly used real Claude for every query even while that process's own default resolved to
  `ollama`; `GET /models?provider=anthropic` returned real model names while
  `GET /models?provider=ollama` (unreachable from inside that container) cleanly 502'd.
- **Known limitation, not solved this milestone**: `mcp-agent-api` running inside docker-compose
  cannot reach a host-run Ollama by default (containers don't see `localhost:11434` on the host) —
  validated instead via the CLI running directly on the host, and via the API's explicit-provider
  path (`anthropic`), which doesn't depend on that networking gap. Wiring an Ollama service into
  the docker-compose stack itself (so the containerized API gets a real free default too) is
  deferred, not yet scheduled.

## M6 — Policy, Knowledge & Judge

**Short story:** `policy.md` goes straight into the system prompt (not RAG); a narrowly-scoped
knowledge base lets the agent cite real regulatory drug-safety text instead of reasoning about it
itself; every response now goes through an LLM-as-judge for soft-quality checks, with code still
enforcing every hard invariant.

**Long story:** (full design: [`design.md` §4.6](./design.md#46-policy-knowledge-judge--m6--implemented))

- **Policy:** `agent_platform/policy.py`'s `load_policy()` reads `mcp-agent/policy.md` once at
  import time, concatenated onto the existing tool-orchestration system prompt — unchanged,
  always-apply, no retrieval ([`decisions.md` H6](./decisions.md), [`H52`](./decisions.md)). A
  missing policy file fails the whole process at startup, not silently at first query.
  `policy.md` covers scope, authority, the same safety invariants M1's gate enforces in code
  (restated as policy text, not duplicated logic), tone, and data handling.
- **Judge:** runs on every response, not a filtered "important" subset
  ([`H11`](./decisions.md), superseding [`H7`](./decisions.md)). Checks soft qualities only via a
  forced `submit_judgment` tool call (groundedness, tone, PHI leak); **structurally incapable of
  overriding a decision** ([`H54`](./decisions.md)) — called strictly after the decision is
  final, result never fed back into any decision path. Deliberately bypasses the shared circuit
  breaker/rate limiter from M4 ([`H53`](./decisions.md)) so a run of judge failures can never trip
  the breaker protecting the real clinical call; fails closed to "inconclusive" on anything going
  wrong, never raises. Evaluated against local/weak-model output from M5 (a live test against
  real Ollama), not only Claude's.
- **Knowledge base** ([`H15`](./decisions.md)): **openFDA Drug Label API**
  (`boxed_warning`/`contraindications`, verified live and actively maintained) and **RxClass
  API** (NLM/RxNav drug-class relationships, verified active) — both new to this repo, distinct
  in domain from `data/payer-kb/`. NLM's Drug-Drug Interaction API is explicitly excluded
  (discontinued January 2024). Retrieval fires only after `triage-service`'s decision exists —
  never before, as an input the agent reasons over: `tools.py`'s `assess_refill_risk` surfaces
  which medication(s) the already-computed risk result flagged, and `agent.py` reacts to that
  code-observable field alone, never re-deriving risk severity itself
  ([`H55`](./decisions.md)). **openFDA is queried by generic name, RxClass by RxNorm code**
  ([`H56`](./decisions.md)) — live-verified during design: this repo's medications carry
  ingredient-level RxNorm codes that 404 against openFDA's product-level `rxcui` field but work
  directly with RxClass. As shipped, wired into `mcp-agent` only (the pilot target) — the
  provisional "which agent consumes it" question is resolved that way for now.
- **Testing:** `agent-platform` — unit tests for the policy loader, the judge (clean/flagged/
  inconclusive/malformed/model-unreachable cases), and both knowledge fetchers (parsing +
  network-failure/not-found cases, mocked). `mcp-agent` — `assess_refill_risk`'s new
  `flagged_medications` field (including that a medication-fetch failure never affects the
  already-computed risk result), `decision_block`'s citation/judgment rendering (including that a
  maximally-negative judgment still renders the *unchanged* original decision label — the direct
  test of H54's structural guarantee), and `run_query` integration tests confirming citations and
  judge results are actually threaded through end to end. Two live tests: the judge against a real
  Ollama model (self-hosted, hard-fail per H50's convention), and the two knowledge-base functions
  against the real openFDA/RxClass APIs (self-skip on connectivity failure — these are third-party
  services this repo doesn't operate, unlike Ollama).
- **Live end-to-end validated**: the HIGH-risk amoxicillin/penicillin-allergy reference case,
  run against real Claude + real FHIR/triage, correctly produced `DO_NOT_DISPENSE` with real
  openFDA contraindication text and real RxClass drug classes as citations. The judge, in that
  same run, flagged a genuine (if debatable) issue — the model's own rationale repeated the
  patient's name unnecessarily — and it rendered as a clearly-advisory note without touching the
  decision above it, exactly the H54 guarantee this milestone is built around. Separately, two
  runs against the real self-hosted default (`llama3.2:1b`) confirmed the fail-closed paths
  (H5, H18, H21) still resolve correctly end to end with a genuinely weak model driving the whole
  loop, policy text included.

Sources verified for the knowledge-base decision: [openFDA — explore the API](https://open.fda.gov/apis/drug/label/explore-the-api-with-an-interactive-chart/) · [NIH Discontinues their Drug Interaction API](https://blog.drugbank.com/nih-discontinues-their-drug-interaction-api/) · [RxClass API](https://lhncbc.nlm.nih.gov/RxNav/APIs/RxClassAPIs.html)

## M7 — Strong Model in Production (planned, not yet implemented)

**Short story:** Guarantee that a *real* clinical deployment actually runs a strong model,
replacing M5's minimal `DEPLOYMENT_ENV=production` guardrail with the fuller mechanism it was
always meant to be a stopgap for.

**Long story:** (full design: [`design.md` §4.7](./design.md#47-strong-model-in-production--m7--planned-not-yet-implemented))

- **The problem M5 left open:** `DEPLOYMENT_ENV=production` ([`decisions.md` H47](./decisions.md))
  only refuses to start when `LLM_PROVIDER` is *unset* — it does nothing to stop a misconfigured
  deployment from explicitly (if mistakenly) setting `LLM_PROVIDER=ollama` in what's actually a
  production environment, or from `DEPLOYMENT_ENV` itself being absent/wrong on a real deployment.
  A one-off env var is exactly the kind of thing that's easy to get right in a demo and wrong in a
  real rollout.
- **What "the fuller design" needs to answer**, not yet decided:
  1. What actually *declares* an environment as production, in a way a deployment can't
     accidentally misrepresent — a signed/provisioned value from the deploy pipeline itself
     (Terraform output, a GKE workload identity claim, a value only settable by whoever owns the
     deployment), not a plain env var anyone could type wrong.
  2. What the fail-loud behavior is precisely — refuse to start entirely, or start but refuse to
     serve `/sessions`/`/query` until a valid provider is confirmed reachable?
  3. Whether this needs a real allowlist ("production may only run `anthropic`, never `ollama`")
     versus just "production may not silently default" (M5's current, narrower guarantee).
  4. How this interacts with the docker-compose dev/demo stack, which is explicitly *not*
     production and must keep working with zero required configuration.
- **Deliberately not started yet** — this is exactly the kind of change CLAUDE.md flags for
  deeper architectural care (hard to reverse, touches production reliability) and the user
  explicitly asked to defer it rather than bolt it on inside M5's rework.
