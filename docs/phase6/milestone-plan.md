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

**Short story:** Formalize the two-adapter seam (Anthropic native + OpenAI-compatible) so
Llama/DeepSeek/local models become config, not code — making official what M1's local-LLM testing
already forced into informal existence.

**Long story:** (full design: [`design.md` §4.5](./design.md#45-multi-provider--m5--implemented))

- **Two adapters only** ([`decisions.md` H4](./decisions.md)): Anthropic native (used completely
  unwrapped — its response shape already matches what `run_query` expects, [`H40`](./decisions.md))
  + one OpenAI-compatible adapter (`agent_platform.providers.OpenAICompatibleProvider`) covering
  Llama, DeepSeek, Ollama, vLLM, hosted OpenAI-compatible endpoints. Model choice is config
  (`LLM_PROVIDER`/`LLM_MODEL`/`LLM_BASE_URL`/`LLM_API_KEY`), never a code branch.
- **Conversation-history translation** — written and tested for real, not assumed:
  `_to_openai_messages()`/`_to_openai_tools()` outbound, `_from_openai_response()` inbound,
  including turning our own `tool_result` entries into separate OpenAI `"tool"`-role messages
  and falling back to an empty tool-call input on malformed JSON from a weak model
  ([`H43`](./decisions.md)) rather than raising.
- **Resilience made provider-agnostic** ([`H42`](./decisions.md)): M4's circuit breaker now trips
  on `httpx.HTTPError` too, not just `anthropic.APIError` — otherwise M4's protections would
  silently not cover this new provider path at all.
- **`gen_ai_system` is explicit** ([`H41`](./decisions.md)), not inferred by `isinstance` — caught
  during implementation when a type-based check mislabeled every existing fake-client test.
- **Anthropic stays the only live backend in production** even after this ships — `LLM_PROVIDER`
  defaults to `"anthropic"`.
- **Testing:** `agent-platform` — 17 unit tests for the translation layer and the
  `build_llm_client()` env var contract, no network. `mcp-agent` — 2 **live** integration tests
  against a real local Ollama (`llama3.2:1b`), self-skipping when unreachable, running the actual
  `run_query` loop through the real translation layer (not simulated) — this is M1's own
  adversarial local-model corpus finally exercised through the real agent loop instead of talking
  to Ollama directly, which is all it could do before this milestone built the seam. Plus 3
  regression tests for a real bug (below).
- **A real bug found live, not by any mocked test**: running the full CLI end to end against
  real FHIR/triage services and the real Ollama model, `llama3.2:1b` omitted a required tool
  argument entirely; `tools.py`'s `execute_tool` raised an uncaught `KeyError`, aborting the query
  instead of reaching the intended `RISK_UNKNOWN`/`REVIEW` fail-closed path. This gap predates M5
  (present since M1) but no test — mocked or live — had exercised a model weak enough to trigger
  it until now. Fixed with the same structured-error convention `assess_refill_risk` already uses
  elsewhere in that file ([`H44`](./decisions.md)); re-ran the same live CLI query afterward and
  confirmed a clean `REVIEW` decision instead of a crash.

## M6 — Policy, Knowledge & Judge

**Short story:** `policy.md` goes straight into the system prompt (not RAG); a narrowly-scoped
knowledge base lets the agent cite real regulatory drug-safety text instead of reasoning about it
itself; every response now goes through an LLM-as-judge for soft-quality checks, with code still
enforcing every hard invariant.

**Long story:** (full design: [`design.md` §4.6](./design.md#46-policy-knowledge-judge--m6))

- **Policy:** `policy.md`'s rules load into the system prompt — unchanged, always-apply, no
  retrieval ([`decisions.md` H6](./decisions.md)).
- **Judge:** runs on every response, not a filtered "important" subset
  ([`H11`](./decisions.md), superseding [`H7`](./decisions.md)). Checks soft qualities only;
  never overrides a hard M1 invariant. Evaluated against local/weak-model output from M5, not
  only Claude's.
- **Knowledge base** ([`H15`](./decisions.md)): **openFDA Drug Label API**
  (`boxed_warning`/`contraindications`, verified live and actively maintained) and **RxClass
  API** (NLM/RxNav drug-class relationships, verified active) — both new to this repo, distinct
  in domain from `data/payer-kb/`. NLM's Drug-Drug Interaction API is explicitly excluded
  (discontinued January 2024). Retrieval fires only after `triage-service`'s decision exists —
  never before, as an input the agent reasons over. Provisional corpus choice; revisit once
  M1–M5 clarify which agent actually consumes it.
- **Testing:** acceptance criteria include verifying every citation traces back to a
  pre-existing deterministic decision, not a retrieval-then-reason sequence.

Sources verified for the knowledge-base decision: [openFDA — explore the API](https://open.fda.gov/apis/drug/label/explore-the-api-with-an-interactive-chart/) · [NIH Discontinues their Drug Interaction API](https://blog.drugbank.com/nih-discontinues-their-drug-interaction-api/) · [RxClass API](https://lhncbc.nlm.nih.gov/RxNav/APIs/RxClassAPIs.html)
