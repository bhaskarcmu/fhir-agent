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
- **End-of-milestone checkpoint:** the minimal-viable-cut question (§Order above) gets decided
  here, once M2's actual delivered size is known.

## M3 — Context, Memory & Session Transport

**Short story:** Give the agent a real session concept — Postgres-backed, behind a thin HTTP API
— plus a token-budget policy actually set from M2's real telemetry instead of guessed.

**Long story:** (full design: [`design.md` §4.3](./design.md#43-memory--session--m3))

- **Transport:** a thin FastAPI wrapper around the existing agent loop, matching
  `triage-service`'s convention ([`decisions.md` H14](./decisions.md)) — turns `mcp-agent` from
  a CLI process holding a Python list into an addressable service with sessions. Prerequisite for
  testing concurrency at all (M4).
- **Store:** Postgres/Neon ([`H12`](./decisions.md)) — reusing existing repo infrastructure
  rather than introducing Redis. Schema: `session_id`, `messages`, timestamps, running token
  count. Swappable later via the same documented-scale-swap pattern Phase 2's `C3` set.
- **Memory policy, three axes kept separate:** (1) per-conversation token budget — the real
  number, replacing M1's placeholder cap, set from M2's actual telemetry; (2) concurrent-session
  count — deferred to M4; (3) cross-session persistence — the Postgres store itself.
  Re-fetch-don't-recall enforced throughout.
- **Package landing:** `agent-platform/` gains the session-store client and transport scaffolding,
  reusable by `claims-agent` without a rebuild.
- **Testing:** multi-session concurrency tests, possible for the first time now that transport
  exists; a local-LLM run confirming compaction doesn't break a weaker model's grip on multi-turn
  context.

## M4 — Deploy Resilience & Cost Control

**Short story:** Protect the paid LLM API call with a hybrid rate/cost limiter — alert-only for
real clinical traffic, hard-block only on runaway/bug-driven spend — plus a circuit breaker sized
specifically for that one external dependency, documented as a deliberate divergence from this
repo's usual "no breaker" convention.

**Long story:** (full design: [`design.md` §4.4](./design.md#44-deployment-resilience--cost--m4))

- **Rate/cost posture:** hybrid ([`decisions.md` H19](./decisions.md)) — alert-only for
  legitimate traffic, hard backstop specifically for runaway spend, which pure alert-only has no
  protection against.
- **Circuit breaker:** wraps the LLM API call specifically, diverging explicitly and on the
  record from `HttpTriageClient.java`'s "no breaker" precedent ([`H20`](./decisions.md)) — the
  LLM API's external, metered, cost-bearing risk profile is materially different from the
  internal service-to-service calls that precedent was written for.
- **Grafana dashboards** become buildable now that M2 exists — cost/rate panels alongside
  trace/span panels.
- **Concurrent-session-count scaling** (deferred from M3) gets addressed here, tied to the
  concurrency-limiter design.
- **Testing:** chaos-style tests — simulated LLM API timeouts/5xx/rate-limit responses, confirming
  the breaker trips and M1's `REVIEW` fail-closed path is hit, not a raw crash.

## M5 — Provider Abstraction & Cross-Model Follow-ups

**Short story:** Formalize the two-adapter seam (Anthropic native + OpenAI-compatible) so
Llama/DeepSeek/local models become config, not code — making official what M1's local-LLM testing
already forced into informal existence.

**Long story:** (full design: [`design.md` §4.5](./design.md#45-multi-provider--m5))

- **Two adapters only** ([`decisions.md` H4](./decisions.md)): Anthropic native + one
  OpenAI-compatible adapter covering Llama, DeepSeek, Ollama, vLLM, hosted OpenAI-compatible
  endpoints. Model choice becomes config (base URL + model name), never a code branch.
- **Conversation-history translation** across providers is the real engineering work here —
  written and tested for the first time, not assumed.
- M1's local-LLM adversarial test corpus becomes this milestone's acceptance suite — M5
  formalizes a seam that was informally load-bearing since M1.
- **Anthropic stays the only live backend in production** even after this ships.
- **Testing:** the full three-tier harness from [`design.md` §5](./design.md#5-testing-strategy)
  — stub server, Ollama local, hosted OpenAI-compatible spot-check.

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
