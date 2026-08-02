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

### 4.4 Deployment resilience & cost (→ M4)

- **Rate/cost posture — hybrid** ([`decisions.md` H19](./decisions.md)): alert-only for
  legitimate clinical traffic (this repo's existing rate limiters, Kong's `fhir-rate-limit` and
  `provider-registry-service`'s in-process limiter, are both fail-closed/block-over-limit — a
  deliberate departure here, not an oversight), with a hard backstop reserved specifically for
  runaway/bug-driven spend (an accidental loop, a retry storm) that pure alert-only has no
  protection against at all.
- **Circuit breaker** ([`decisions.md` H20](./decisions.md)) wraps the LLM API call specifically.
  This repo has one explicit precedent *against* circuit breakers generally
  (`HttpTriageClient.java`'s Javadoc: "changes latency, not this policy") — Phase 6 diverges from
  it deliberately, on the stated basis that the LLM API is a materially different risk profile
  (external, metered, cost-bearing SaaS) than the internal service-to-service calls that
  precedent was written for.

### 4.5 Multi-provider (→ M5)

Exactly two adapters ([`decisions.md` H4](./decisions.md)): Anthropic (native tool-use) and one
OpenAI-compatible adapter covering Llama, DeepSeek, Ollama, vLLM, and hosted OpenAI-compatible
endpoints (DeepSeek API, OpenRouter, Groq). Model selection becomes a config value (base URL +
model name); Llama-vs-DeepSeek is never a code branch.

The hard engineering problem here is conversation-history translation — Anthropic's
message/tool-use block shape isn't identical to OpenAI's, and this is where that gets solved for
real. By the time M5 starts, M1's adversarial local-model test corpus (built under the standing
testing rule, H11) already exists and becomes the adapter's acceptance suite — M5 formalizes a
seam that was informally load-bearing since M1, rather than starting from zero.

Anthropic remains the only *live* backend after M5 ships. The seam exists to prove PHI-off-
third-party is achievable when that becomes an active business rule — it is not a default switch.

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
