# Phase 6 — Agent Platform Hardening + Overall Observability — Design

> Architecture and cross-cutting principles for the requirements in
> [`prd.md`](./prd.md). **Milestone sequencing and status live in
> [`milestone-plan.md`](./milestone-plan.md) and [`README.md`](./README.md)** — this document
> does not restate them.

## 1. Target architecture

```
                         ┌────────────── agent-platform/ (NEW, shared) ──────────────┐
                         │ output-gate (enum + REVIEW)     provider adapters (M5)     │
                         │ fail-closed data-layer guards    session store client       │
                         │ OTel instrumentation helpers     rate/cost limiter (M4)     │
                         │ policy/judge scaffolding (M6)                              │
                         └───────────────────────┬────────────────────────────────────┘
                                                  │ imported by
                    ┌─────────────────────────────┼─────────────────────────────┐
                    ▼                                                            ▼
             mcp-agent (Phase 1)                                          claims-agent (Phase 2)
             PILOT — hardened first                                       CARRY-OVER — after pilot
                    │                                                            │
                    ▼ (HTTP, via new M3 transport)                               ▼
             triage-service / fhir-service                                claims-service (→ rxclaim-emulator, fhir-service)
```

`agent-platform/` is a new top-level package, sibling to `client/clinical` — the precedent for a
domain-abstracted library shared by more than one consumer in this repo
([`decisions.md` H2`](./decisions.md), [`H12`](./decisions.md)). It is built shared from **M1**,
not extracted from `mcp-agent` after the fact; `mcp-agent` is the pilot consumer, `claims-agent`
is the carry-over consumer once the pilot is validated.

## 2. The five topics

Fixed numbering, used throughout Phase 6's documents and referenced by number in
[`decisions.md`](./decisions.md):

1. **Memory** — short-term (in-context transcript) vs. long-term (cross-session store); explicit
   token budget; re-fetch-don't-recall.
2. **Deployment resilience & cost control** — client-side limiter in front of the paid LLM API;
   alert, don't silently shed.
3. **Observability** — OTel trace = one agent run, spans = reasoning steps, `gen_ai.*`
   attributes, PHI-safe by construction; architected to also close Phase 2's R15.
4. **Multi-provider follow-ups** — two-adapter provider seam; cross-provider history
   translation.
5. **Output safety** — narrow, code-validated, fail-closed enum contract; `policy.md` in the
   system prompt; judge for soft qualities only.

Topics 2 and 3 are executed together as one milestone (M2) because the client-side limiter (2)
needs the metrics (3) to have thresholds to alert on — see
[`milestone-plan.md`](./milestone-plan.md) for the dependency-ordered build sequence, which
differs from this topic numbering.

## 3. Cross-cutting principles

Every milestone is designed against these, not just the ones that seem topically relevant:

- **Fail-closed, consistently.** Enum → `REVIEW` (M1). Data-layer guard → `UNKNOWN` never `LOW`
  (M1). Circuit breaker trip → `REVIEW`, not a crash (M4). Judge disagreement → hold for human,
  never silently override (M6). Rate/cost limiter → alert, with a hard backstop only for
  runaway spend, never a silent drop of a real clinical request (M4).
- **Deterministic services decide; the agent orchestrates and explains.** The agent is
  non-authoritative in Phase 6 exactly as it is today — nothing in this phase gives it decision
  authority it didn't already have. The M6 knowledge base is the clearest test of this principle
  in practice: retrieval fires only *after* `triage-service`'s decision exists, never before.
- **PHI-safe is a driver, not just a constraint.** Redaction is structural (span/log attributes
  never carry raw identifiers by construction, mirroring `provider-registry-service`'s
  `sanitize_location()` precedent — not scrub-after-the-fact). The M5 provider seam exists
  *because* self-hosting is a PHI win, not only a cost or availability one.
- **Observability first.** M2 lands second, immediately after M1, specifically because M3
  (memory budget), M4 (deploy/cost dashboards), and M6 (judge evaluation) all need real
  telemetry to be designed from data rather than guessed.
- **Test against a weak model, not only Claude.** A standing rule from M1 onward
  ([`decisions.md` H11](./decisions.md)) — the milestones that most depend on structured-output
  reliability (M1, M6's judge) are exactly the ones a strong model's good behavior can mask a
  real gap in.
- **No hardcoded forward references.** Anything Phase 6 writes into another phase's documents
  (the Phase 2 R15 cross-reference, in particular) names the fact, not a milestone number that
  could still shift — see [`decisions.md` H16](./decisions.md).

## 4. Per-topic deep dive

### 4.1 Output safety (→ M1)

Two paired mechanisms, not one:

- **Output-side enum gate.** A tool-with-enum-output parameter constrains the model's final
  answer to a small, purpose-built set of values (not `claims-service`'s `Outcome` enum
  verbatim — the domains don't match; refill triage isn't claims adjudication). `REVIEW` is
  reused as the literal term for the fail-closed case, matching `claims-service`'s existing use
  of that word ([`decisions.md` H10](./decisions.md)). Code validates the returned value
  independent of schema adherence — informed directly by the `llm-tool-schema-oneof-unreliable`
  finding that live models can stringify structured params instead of emitting them natively,
  and by the standing local-LLM testing rule (H11), which will surface this kind of failure a
  Claude-only test suite would miss.
- **Input-side data-layer guard.** A Python wrapper around the `triage-service` call, structurally
  the same shape as `claims-service`'s `HttpTriageClient.java`: any non-2xx, timeout, transport
  failure, or unrecognized risk code produces an explicit `UNKNOWN` sentinel that the enum gate
  is contractually required to treat as `REVIEW` ([`decisions.md` H18](./decisions.md)). This
  closes the concrete, audited gap where `mcp-agent` today bypasses the one real fail-closed
  precedent in this codebase by calling `triage-service` directly.

The output contract's wire shape is standalone — it does not mirror FHIR `OperationOutcome` or
`provider-registry-service`'s `{error_type, message}` ([`decisions.md` H21](./decisions.md)),
because a fail-closed agent answer is a *successful turn* whose content happens to be a
conservative decision, not an HTTP error response.

### 4.2 Observability (→ M2)

Two coordinated instrumentation tracks under one OTLP pipeline:

- **Agent tier:** `gen_ai.*` semantic-convention spans. One trace per agent run; a span per model
  call and per tool call. TraceID propagates into the `triage`/`fhir` calls the M1 guard already
  wraps.
- **Java tier (closes Phase 2 R15):** standard HTTP/DB spans + Micrometer metrics in
  `claims-service` and `rxclaim-emulator`, where today no `opentelemetry`/`micrometer`
  dependency exists at all. `fhir-service` needs a narrower addition — it already has
  Micrometer/Actuator metrics from Phase 1, but no trace-context propagation (`traceparent`
  handling), so its current coverage is metrics-only against R15's original "tracing across the
  fan-out" language.

One exporter, config-only target: local Jaeger/Grafana via docker-compose today; Cloud
Trace/Managed Prometheus later, by pointing at the pipeline Kong already declares (but hasn't
confirmed is being scraped) — zero code change to switch
([`decisions.md` H22](./decisions.md)).

**PHI redaction is structural, not a filter bolted on after the fact** — span/log attribute
construction never has access to the raw identifier in the first place, the same shape as
`provider-registry-service`'s `sanitize_location()`. This same pass extends to fixing Kong's
`file-log` plugin's live, currently-acknowledged raw-URI PHI leak
([`decisions.md` H17](./decisions.md)) — in scope specifically because M2's charter is now
platform-wide ("Overall Observability"), not agent-tier-only. That specific gateway-config change
still needs its own explicit go-ahead before any deploy, independent of general approval for M2,
per this repo's standing rule on infra/deployment-config changes.

**Closing R15 without duplicating or hardcoding Phase 2's docs:** once this ships,
`docs/phase2/decisions.md`'s `C5` entry (added when this phase's audit first found the gap) gets
its status updated to reflect closure, worded as "closed by a later platform-wide observability
effort" with no citation of a specific Phase 6 milestone number — so it can't go stale if this
phase's own numbering shifts before that update happens.

**Custom span attributes, request-ID surfacing, and configurable depth**
([`decisions.md` H24–H27](./decisions.md)): a full attribute dictionary —
[`telemetry-schema.md`](./telemetry-schema.md) — defines `fhir_agent.layer`/`.component` (custom,
grounded in each service's real package/module structure) alongside OTel's own standard
`code.function.name`, a two-level `TELEMETRY_VERBOSITY` setting (`standard` enriches existing
spans only; `detailed` adds sub-spans at the single highest-value boundary — per-rule spans in
`triage-service/rules.py`, not instrumented everywhere by default), and `X-Trace-Id`
response-header / CLI-output surfacing so a human or test program can identify and look up their
own request without already having Jaeger open.

### 4.3 Memory & session (→ M3) — implemented

Three axes, deliberately not conflated:

1. **Per-conversation token budget** — `agent_platform.context_budget.TOKEN_BUDGET = 40_000`,
   grounded in real, live-measured usage: two complete reference-workflow queries cost 5,404 and
   5,381 tokens end to end, read from actual `gen_ai.usage.*` span attributes via Jaeger's API
   after running them against the live stack — not guessed, not estimated
   ([`decisions.md` H29](./decisions.md)). `MAX_TOKENS=1024` in `agent.py` remains the *output*
   cap on a single model call, a distinct, unrelated concept. Compaction (`context_budget.compact()`)
   drops the single oldest complete turn once the running total exceeds budget, self-correcting
   on the next real measurement rather than computing a precise target in one shot
   ([`decisions.md` H30](./decisions.md)).
2. **Concurrent-session count** — a compute-scaling question, addressed in M4, not here.
3. **Cross-session persistence** — `agent_platform.session_store`, a dedicated Postgres instance
   (`agent-db` in `docker-compose.yml`'s new `phase6` profile), following
   `provider-registry-service`'s own `db.py`/`schema.sql`/`init_db.py` connection-pool convention
   exactly for consistency with the one other Postgres-backed service in this repo. A dedicated
   instance rather than sharing Phase 3's `postgres` container, to keep phase boundaries clean —
   a bug in one schema can't touch the other's data. Messages are stored as JSON text with manual
   (de)serialization, not native `jsonb`, because the Anthropic SDK's assistant-turn content
   blocks are Pydantic models needing `model_dump(mode="json")` first, confirmed against the
   installed SDK, not assumed ([`decisions.md` H28](./decisions.md)).

**Transport** ([`decisions.md` H14](./decisions.md)): `mcp-agent/src/agent/api.py`, a thin FastAPI
wrapper — `POST /sessions`, `POST /sessions/{id}/query`, `GET /health` — matching
`triage-service`'s own convention, including `X-Trace-Id` response headers and
`FastAPIInstrumentor` for a server span per request. `run_query`'s return arity is unchanged (still
a 2-tuple); the new token count and trace ID are handed back through an optional `stats` dict so
every pre-M3 call site stays valid unmodified ([`decisions.md` H31](./decisions.md)). The existing
CLI's `interactive_mode`/`non_interactive_mode` gained an optional `session_id` and gracefully fall
back to in-memory-only sessions when `DATABASE_URL` isn't set — mirroring `claims-agent`'s own
no-API-key deterministic fallback, so the zero-setup CLI experience is unchanged by default
([`decisions.md` H32](./decisions.md)). The HTTP transport has no such fallback: an HTTP "session"
with no persistence isn't a session, so it 503s instead.

**Re-fetch, never recall** is a hard rule, not a preference: every turn re-calls
`get_patient_summary`/`assess_refill_risk` rather than trusting anything cached in prior message
history, because FHIR data can change between turns — treating cached clinical state as current
is the same class of hazard as the fail-open bug this repo's fail-closed conventions exist to
prevent. The session store persists conversation *history* (what was asked, what was decided),
never a cached clinical read.

**Transport:** a thin FastAPI HTTP wrapper around the existing agent loop
([`decisions.md` H14](./decisions.md)), matching `triage-service`'s own convention — not a full
UI, not a streaming design. It exists because M3's session store and M4's concurrency work are
both untestable against a single-process REPL holding a Python list.

### 4.4 Deployment resilience & cost (→ M4) — implemented

- **Rate/cost posture — hybrid** ([`decisions.md` H19](./decisions.md)): alert-only for
  legitimate clinical traffic (this repo's existing rate limiters, Kong's `fhir-rate-limit` and
  `provider-registry-service`'s in-process limiter, are both fail-closed/block-over-limit — a
  deliberate departure here, not an oversight), with a hard backstop reserved specifically for
  runaway/bug-driven spend (an accidental loop, a retry storm) that pure alert-only has no
  protection against at all. `agent_platform.resilience.RateCostLimiter` tracks token usage in a
  sliding one-minute window; `before_call()` returns True (alert, still allowed through) once the
  window crosses `alert_tokens_per_minute`, and raises `CostLimitExceededError` (not attempted at
  all) once it would cross `hard_backstop_tokens_per_minute`. Both are grounded in M3's real
  per-query measurement, not arbitrary round numbers ([`H36`](./decisions.md)).
- **Circuit breaker** ([`decisions.md` H20](./decisions.md)) wraps the LLM API call specifically.
  This repo has one explicit precedent *against* circuit breakers generally
  (`HttpTriageClient.java`'s Javadoc: "changes latency, not this policy") — Phase 6 diverges from
  it deliberately, on the stated basis that the LLM API is a materially different risk profile
  (external, metered, cost-bearing SaaS) than the internal service-to-service calls that
  precedent was written for. `agent_platform.resilience.CircuitBreaker` is a plain
  consecutive-failure breaker (closed → open → half-open → closed), default 5 failures / 30s
  reset ([`H35`](./decisions.md)), tripping on any `anthropic.APIError` — deliberately broad,
  covering 4xx as well as 5xx/timeouts ([`H37`](./decisions.md)).
- **Fail-closed integration**: `call_with_resilience()` wraps the one `client.messages.create()`
  call site in `agent.py`. `CircuitOpenError`/`CostLimitExceededError` are caught there and mapped
  straight onto M1's `AgentDecision.REVIEW` sink via a new `_fail_closed_unavailable()` helper —
  an LLM call that couldn't even be attempted is exactly as safety-relevant as a risk check that
  came back UNKNOWN ([`H34`](./decisions.md)). An *individual* call failure below the breaker's
  threshold still propagates as an exception exactly as it did before M4 (existing test coverage
  unchanged); `api.py` now maps that specific case to a clean `502`, a real gap found live-testing
  with an intentionally invalid API key — without it, FastAPI's default 500 was the only outcome,
  an ungraceful failure mode for a milestone about deploy resilience specifically.
- **Concurrency limiter** ([`decisions.md` H38](./decisions.md)): `mcp-agent-api`'s
  `query_session` route is guarded by a bounded `threading.Semaphore` (default 10 concurrent LLM
  queries) with a deadline (default 5s) — a request that can't get a slot in time gets a `503`
  rather than queueing indefinitely. This is M3's deferred "concurrent-session-count scaling":
  what actually threatens the single Anthropic API key's rate limits and this process's thread
  pool is LLM calls in flight at once, not how many Postgres-backed sessions exist.
- **Metrics** ([`decisions.md` H39](./decisions.md)): four real Prometheus series exposed at
  `mcp-agent-api`'s new `/metrics` route — `fhir_agent_llm_tokens_total{direction}`,
  `fhir_agent_llm_calls_total{outcome}` (success/failure/circuit_open/cost_blocked),
  `fhir_agent_llm_call_duration_seconds`, `fhir_agent_rate_limit_alerts_total`. Scraped by
  Prometheus the same way the Java services' `/actuator/prometheus` already is (one scrape
  convention repo-wide, not a parallel OTLP-metrics pipeline) — closes the gap M2 deliberately
  deferred ([`decisions.md` H27](./decisions.md), `telemetry-schema.md` §7). A provisioned Grafana
  dashboard (`observability/grafana/provisioning/dashboards/llm-cost-rate.json`) visualizes all
  four alongside M2's existing trace/span panels.
- **Live-validated, not just mocked**: with `ANTHROPIC_API_KEY` set to an intentionally invalid
  value and the breaker threshold lowered to 2 for a fast repro, two real calls against the live
  Anthropic API 502'd cleanly, the breaker opened, and the third call returned a real `200` with
  a `REVIEW` decision and a trace ID — not a crash. Restoring a real key and recreating the
  container recovered normal operation (a fresh process resets the breaker's process-local
  state). Grafana's dashboard API confirmed the provisioned dashboard loads with all 4 panels;
  Prometheus's own `/api/v1/targets` confirmed `mcp-agent-api` scraping as `up`.

### 4.5 Multi-provider (→ M5) — implemented, reworked post-review

Three provider *identities*, two adapter *implementations* ([`decisions.md` H45](./decisions.md),
superseding H4's "exactly two adapters, Anthropic is the default"): `"anthropic"` (native),
`"ollama"` (self-hosted, the only identity ever selected automatically), and
`"openai_compatible"` (any other OpenAI-chat-completions-shaped endpoint — DeepSeek API,
OpenRouter, Groq, a self-hosted vLLM box — never a default, always explicit). `"ollama"` and
`"openai_compatible"` share one adapter implementation (`OpenAICompatibleProvider`); the split
exists purely to answer *who hosts the inference*, which is the property that actually matters
for keeping PHI off a third party — not which wire protocol is spoken. Model selection is a
config value (`LLM_PROVIDER`/`LLM_MODEL`/`LLM_BASE_URL`/`LLM_API_KEY`/`DEPLOYMENT_ENV`, resolved
by `agent_platform.providers.build_llm_client()`); Llama-vs-DeepSeek-vs-Claude is never a code
branch.

- **No wrapper needed for Anthropic** ([`decisions.md` H40](./decisions.md)): `anthropic.Anthropic`
  already returns exactly the shape `run_query` expects, so it's used completely unwrapped.
  `OpenAICompatibleProvider` duck-types the same `client.messages.create(**kwargs)` surface, so
  `run_query`, `agent.py`, and every one of M1-M4's existing fake-client test fixtures need zero
  changes to use any of the three identities interchangeably.
- **Conversation-history translation** — the actual hard engineering problem — lives in
  `agent_platform/providers.py`: `_to_openai_messages()`/`_to_openai_tools()` outbound (our
  Anthropic-shaped messages/tool definitions → OpenAI chat-completions shape, including turning
  each of our own `tool_result` entries into its own separate `"tool"`-role message), and
  `_from_openai_response()` inbound (OpenAI's `finish_reason`/`tool_calls`/`usage` → the same
  `NormalizedResponse`/`TextBlock`/`ToolUseBlock`/`Usage` dataclasses `run_query` already knows
  how to read). Malformed tool-call-argument JSON from a weak model falls back to an empty input
  rather than raising ([`H43`](./decisions.md)) — the standing local-LLM testing rule (H11)
  applied to the translation layer itself.
- **Resilience is provider-agnostic** ([`decisions.md` H42](./decisions.md)): M4's circuit breaker
  treats both `anthropic.APIError` and `httpx.HTTPError` as tripping failures, since
  `OpenAICompatibleProvider` raises the latter, not the former. `anthropic` and `httpx` became
  real (non-optional) `agent-platform` dependencies as a direct result.
- **`gen_ai_system` is explicit, not inferred** ([`decisions.md` H41](./decisions.md)): a
  type-based `isinstance(client, anthropic.Anthropic)` check mislabeled every existing
  fake-client test as `"openai_compatible"`, caught while implementing M5 the first time — every
  identity is threaded through explicitly instead.
- **The default flipped to `"ollama"`** ([`decisions.md` H45](./decisions.md)) — self-hosted,
  free, and (the actual, primary rationale, not a side effect) PHI never leaves this host when
  nothing is explicitly configured. A present `ANTHROPIC_API_KEY` does **not**, on its own, select
  Anthropic ([`H46`](./decisions.md)) — only an explicit `LLM_PROVIDER` does, since a key's mere
  presence is too easily accidental (a leftover `.env`, a shared devcontainer image) to trust with
  that decision. This is a real, acknowledged breaking behavior change for every pre-rework
  docker-compose/dev setup that only ever set `ANTHROPIC_API_KEY`.
- **Disclosed, never silently substituted** ([`H46`](./decisions.md)): the CLI prints a one-time
  message when the self-hosted default was actually used, gated on `sys.stdin.isatty()` — that
  signal decides *whether to show the message*, never which model runs; an automated caller (not
  a TTY) sees nothing extra. `ResolvedProvider.is_default` carries this from
  `build_llm_client()` through to `agent.py`'s `_maybe_print_disclosure()`. The HTTP transport has
  no TTY concept and shows nothing — a documented, accepted limitation, since the underlying
  default-selection rule doesn't depend on that signal at all.
- **`DEPLOYMENT_ENV=production` is a minimal guardrail, not the full design**
  ([`H47`](./decisions.md)): an unset `LLM_PROVIDER` becomes a loud `RuntimeError` instead of a
  silent `ollama` fallback when set — production must never be "the vacuum." The fuller,
  auditable, fail-loud environment-tier design is deferred to **M7** (§4.7 below); this closes
  only the most dangerous immediate gap (a misconfigured deployment silently downgrading to a 1B
  local model while still producing plausible-looking output).
- **Discovery is opt-in and all-or-nothing** ([`H48`](./decisions.md)): `list_anthropic_models()`/
  `list_ollama_models()`/`list_openai_compatible_models()`, the CLI's `--list-models`/`--provider`/
  `--model` flags, and the API's `GET /models?provider=...` — none of these are called unless
  something explicitly asks; once asked, discovery either returns a real list or raises, with no
  partial results and no fallback logic to maintain.
- **Model choice is per-session (API) / per-process (CLI)** ([`H49`](./decisions.md)): pinned at
  creation, immutable for that conversation's lifetime. `agent_sessions` gained persisted
  `provider`/`model` columns (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, confirmed live against a
  real pre-existing table, not just a fresh one). `build_client_for(provider, model)` rebuilds the
  exact client for a resumed CLI session or any API query, reading only infrastructure-level
  config (base URL, API key) from the *current* environment — no session-scoped secret is ever
  persisted. Live-confirmed on the real API: a session explicitly pinned to `anthropic` correctly
  used real Claude for every query even while the process's own default resolved to `ollama`.
- **M1's adversarial local-model test corpus becomes the real acceptance suite, not a stand-in**:
  M1's own live Ollama test talked to Ollama directly, bypassing the agent loop entirely, because
  this translation layer didn't exist yet. `mcp-agent/tests/test_provider_integration.py` now
  exercises the exact same weak model (`llama3.2:1b`) through the *real* `run_query` loop and the
  *real* translation layer. Ollama is now a **required** test dependency for these specific tests
  ([`H50`](./decisions.md)) — hard-fail, not self-skip — while the large body of fake-client
  agent-loop tests deliberately stays fake-client-only, unaffected by Ollama's availability.
- **A real bug found only by this live weak-model run, not any prior mocked test**
  ([`decisions.md` H44](./decisions.md)): `tools.py`'s `execute_tool` raised an uncaught `KeyError`
  when `llama3.2:1b` omitted a required tool argument — aborting the whole query instead of the
  intended `RISK_UNKNOWN`/`REVIEW` fail-closed path. This gap predates M5 (it existed since M1)
  but only a genuinely weak model ever exercised it. Fixed with the same structured-error
  convention `assess_refill_risk` already uses elsewhere in that file.
- **Live-validated end to end, not just unit-tested**: the CLI with no `LLM_PROVIDER` set at all
  ran a real query against real FHIR/triage services and the real self-hosted model, with zero
  API key required; `--list-models ollama` printed the real locally-pulled models;
  `DEPLOYMENT_ENV=production` with no `LLM_PROVIDER` refused to start with the documented error;
  `--provider anthropic --model claude-sonnet-4-5` correctly used real Claude; and the live API's
  `GET /models?provider=anthropic` returned real Anthropic model names while
  `GET /models?provider=ollama` (unreachable from inside that container) cleanly 502'd rather than
  crashing.

### 4.6 Policy, knowledge, judge (→ M6)

- **Policy:** `policy.md`'s rules load directly into the system prompt — they always apply, so
  retrieval is structurally the wrong mechanism for them
  ([`decisions.md` H6](./decisions.md)).
- **Judge:** runs on every response, not a filtered "important" subset
  ([`decisions.md` H11](./decisions.md), superseding [`H7`](./decisions.md)) — checks soft
  qualities only (groundedness, tone, PHI leak) and never overrides a hard invariant M1's gate
  already enforced. Evaluated, per the standing testing rule, against outputs a local/weak model
  actually produced via M5's adapters — not only against Claude's own clean output.
- **Knowledge base** ([`decisions.md` H15](./decisions.md)): **openFDA Drug Label API**
  (`boxed_warning`/`contraindications` fields, free, no auth, actively maintained) and **RxClass
  API** (NLM/RxNav, drug-class relationships, confirmed active). Both are new to this repo and
  distinct in domain from `data/payer-kb/` (Phase 2's claims/coverage data — a different
  knowledge domain than `mcp-agent`'s drug-safety pilot). NLM's separate Drug-Drug *Interaction*
  API is explicitly excluded — discontinued January 2024.

  **The non-clinical-judgment constraint is structural, not a prompt instruction:** retrieval
  only fires *after* `triage-service` has already returned a determination, to fetch citation
  text for a decision that already exists — never *before*, as an input the agent reasons over.
  This is the concrete implementation of §3's "deterministic services decide" principle, applied
  to the one place in Phase 6 an LLM might otherwise be tempted to reason clinically on its own.

  This corpus choice remains provisional — M6 is last in the build order, and which agent
  (`mcp-agent` or a carried-over `claims-agent`) ends up consuming it may become clearer once
  M1–M5 land.

### 4.7 Strong model in production (→ M7) — planned, not yet implemented

Deferred scope, not yet built: an explicit, auditable, fail-loud environment-tier declaration
that a real production deployment cannot accidentally misrepresent (unlike an easily-forgotten
env var) — the actual mechanism that guarantees a *real* clinical deployment runs a strong model,
building on the minimal `DEPLOYMENT_ENV=production` guardrail ([`decisions.md` H47](./decisions.md))
already shipped in M5's rework. See
[`milestone-plan.md` M7](./milestone-plan.md#m7--strong-model-in-production-planned-not-yet-implemented)
for the full scope and open design questions.

## 5. Testing strategy

Per [`prd.md` R19](./prd.md#4-functional-requirements) and
[`decisions.md` H11](./decisions.md): every milestone from M1 onward includes adversarial
testing against a local/weak model, not only Claude. Three cost/realism tiers, reused across
milestones rather than invented per-milestone:

| Tier | Cost | Use |
|---|---|---|
| Stub OpenAI-compatible server | $0, CI-safe | Baseline structural test — malformed/partial tool-call shapes, timeouts, non-200s. |
| Ollama, local | $0, deliberately weak | The harshest realistic adversary for M1's enum gate and M6's judge — a model genuinely worse than Claude at following structured-output instructions. |
| Hosted OpenAI-compatible (DeepSeek API / OpenRouter / Groq) | Pennies | Real-quality spot-check once the stub/Ollama tiers pass. |

M1 builds this harness before the formal provider seam (M5) exists — a throwaway
OpenAI-compatible-shaped call is sufficient for M1's own testing; M5 formalizes the adapter the
harness already assumed.

## 6. Open items resolved during milestone execution, not blocking kickoff

A few concrete numbers are deliberately left to the milestone that has the data to set them
honestly, rather than guessed here:

- M1's placeholder message-list cap (a stopgap number, not the real budget — see
  [`prd.md` R9](./prd.md#4-functional-requirements) and
  [`milestone-plan.md` M1](./milestone-plan.md#m1--output-contract--fail-closed-enforcement)).
- M3's real per-conversation token budget (set from M2 telemetry).
- M6's specific judge-model choice and prompt.

None of these block starting M1.
