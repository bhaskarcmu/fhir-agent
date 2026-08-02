# Phase 6 — Agent Platform Hardening + Overall Observability — PRD

> Problem statement, goals/non-goals, functional requirements, success metrics. Normative for
> *what* Phase 6 must be true of when done. **Status, milestones, and how** live in
> [`README.md`](./README.md), [`design.md`](./design.md), and
> [`milestone-plan.md`](./milestone-plan.md) — not restated here.

## 1. Problem statement

The agent tier (`mcp-agent`, Phase 1's refill-risk-triage CLI; later `claims-agent`, Phase 2's
claims-explanation agent) has never been hardened to the standard the deterministic tiers
already are. Concretely, as of this PRD:

- **No output-safety enforcement.** `mcp-agent` can produce a dispense recommendation with
  nothing in code checking it against what the triage service actually returned. The one real
  fail-closed precedent in this codebase (`claims-service`'s `HttpTriageClient.java`, which maps
  every unrecognized/failed safety check to `UNKNOWN → PEND`, never `LOW`) is bypassed entirely —
  `mcp-agent` calls `triage-service` directly.
- **No observability.** No OTel, no metrics, no structured logging in any agent — a clean slate,
  confirmed by direct code audit, not assumed from docs.
- **No memory or session management.** `interactive_mode`'s message list grows unbounded for the
  life of the process; a single-shot `--query` invocation has no session concept at all.
- **No deployment resilience.** One flat 30-second timeout on the triage call, no retry, no
  circuit breaker, no rate or cost control on the paid, rate-limited Anthropic API.
- **Hardcoded to one provider.** `import anthropic` directly in both agents; no seam for any
  other model.

At the same time, the agent is becoming a genuinely **clinician-facing** conversational surface
(patient/medication disambiguation, dispense/review/hold recommendations) rather than a demo
script — which is what justifies hardening it to platform-grade rigor now, not later.

Separately, and unrelated in subject matter but bundled into this same phase's title
(**"+ Overall Observability"**) by deliberate scope decision (see
[`decisions.md` H16](./decisions.md)): Phase 2's requirement **R15 (Observability)** was
documented as delivered ("OTel tracing wired") but is not — no `opentelemetry`/`micrometer`
dependency exists in `claims-service` or `rxclaim-emulator`. Phase 6 closes that gap as part of
building the same tracing/metrics architecture for the agent tier, rather than as separate,
disconnected work.

## 2. Goals

Five topics, referenced by number throughout Phase 6's documents (see
[`design.md` §2](./design.md#2-the-five-topics)):

1. **Memory** — short-term (in-context transcript) vs. long-term (cross-session store), with an
   explicit, data-driven token budget and a hard "re-fetch, never recall" rule for clinical data.
2. **Deployment resilience & cost control** — a client-side limiter in front of the paid,
   rate-limited LLM API; alerts, not silent request-shedding, for a clinical-tier system.
3. **Observability** — OTel tracing + metrics for the agent tier, architected to also close
   Phase 2's R15 gap platform-wide (topics 2 and 3 are deliberately treated together in the
   milestone plan — see [`milestone-plan.md` M2](./milestone-plan.md#m2--observability-platform-wide)).
4. **Multi-provider follow-ups** — a real provider seam (Anthropic native + one
   OpenAI-compatible adapter) proving PHI-off-third-party is achievable, without switching the
   live default away from Anthropic.
5. **Output safety** — a narrow, code-validated, fail-closed output contract; this is the
   platform's existing fail-closed thesis applied to what the agent is allowed to *say*, not just
   what deterministic services are allowed to *decide*.

## 3. Non-goals

- **No clinical logic in the agent.** Every Phase 6 milestone reinforces, never weakens, "AI
  explains and orchestrates; deterministic services decide." The M6 knowledge base
  (§`milestone-plan.md` M6) is explicitly designed so retrieval only ever grounds an
  *explanation* of a decision `triage-service` already made — never a premise the agent reasons
  over to reach its own conclusion.
- **No live switch away from Anthropic.** The provider seam (M5) exists to prove the seam works,
  not to change the production default. Anthropic remains the only live backend Phase 6 ships
  with.
- **No Phase 3 or Phase 4 agent work.** `provider-search-agent`, `provider-curation-agent`, and
  any future Epic-emulator-adjacent agent work are explicitly out of scope — Phase 6 pilots on
  `mcp-agent` (Phase 1) and carries to `claims-agent` (Phase 2) only.
- **No full web/chat product.** M3's transport work (§`milestone-plan.md` M3) is a thin HTTP API
  sufficient to test sessions and concurrency — not a UI, not a streaming design, not a customer
  product surface.
- **No RAG for behavioral rules.** `policy.md` goes into the system prompt; RAG (M6) is reserved
  for a genuine knowledge base only ([`decisions.md` H6](./decisions.md)).
- **No epic-emulator work.** Phase 6 is unrelated in subject matter to Phase 5 (`epic-emulator`
  decomposition) — see [`../phase5/README.md`](../phase5/README.md) for that phase's own,
  separate, and still-unstarted scope.

## 4. Functional requirements

Grouped by topic; each maps to the milestone(s) that deliver it in
[`milestone-plan.md`](./milestone-plan.md).

**Output safety (topic 5, → M1)**
- **R1.** Every agent turn resolves to one of a small, explicit set of enum outcomes, including a
  `REVIEW` value that is the fail-closed sink for anything off-contract.
- **R2.** The enum is validated in code, not trusted from the model's tool-schema adherence alone.
- **R3.** A data-layer guard on the `triage-service` call ensures any unrecognized/failed safety
  check maps to an explicit `UNKNOWN` state that R1's contract is required to treat as `REVIEW`,
  never as safe — independent of whether the model itself reads the tool result correctly.

**Observability (topics 2 & 3, → M2)**
- **R4.** Every agent run produces one trace; every model call and every tool call is a span,
  using `gen_ai.*` semantic conventions.
- **R5.** TraceID propagates from the agent into `triage-service`/`fhir-service` calls.
- **R6.** Span/log attributes are PHI-safe by construction (structural redaction, not
  scrub-after-the-fact).
- **R7.** `claims-service` and `rxclaim-emulator` receive equivalent tracing/metrics
  instrumentation, closing Phase 2's R15; `fhir-service`'s existing metrics-only coverage is
  extended to include trace propagation.
- **R8.** The exporter target is config-only — the same instrumentation serves a local
  Jaeger/Grafana stack today and Cloud Trace/Managed Prometheus later.

**Memory & session (topic 1, → M3)**
- **R9.** Per-conversation token budget is a real number set from R4's telemetry, with a
  documented compaction policy at threshold — not a guess.
- **R10.** Every clinical data read re-fetches from FHIR/triage on each turn; nothing clinical is
  ever answered from cached conversation history.
- **R11.** Conversation state persists in an externalized store (Postgres/Neon), addressable by
  session ID via an HTTP API — not only an in-process Python list scoped to one REPL.

**Deployment resilience & cost (topic 2, → M4)**
- **R12.** A client-side limiter in front of the LLM API alerts on threshold breach for normal
  traffic and only hard-blocks on runaway/bug-driven spend — never on a legitimate clinical
  query.
- **R13.** A circuit breaker specifically wraps the LLM API call, documented as a deliberate
  divergence from this repo's otherwise-consistent "no breaker" convention.

**Multi-provider (topic 4, → M5)**
- **R14.** Exactly two provider adapters — Anthropic native and one OpenAI-compatible adapter
  covering Llama/DeepSeek/Ollama/vLLM/hosted endpoints. Model selection is configuration, not
  code.
- **R15-agent.** *(named to avoid collision with Phase 2's R15)* Conversation history correctly
  round-trips through both adapters and through R11's session store regardless of provider.

**Policy, knowledge, judge (topic 5, → M6)**
- **R16.** `policy.md`'s rules are always present in the system prompt.
- **R17.** An LLM-as-judge evaluates every response for soft qualities (groundedness, tone, PHI
  leak); it never overrides a hard invariant R1–R3 already enforced.
- **R18.** Any knowledge-base retrieval fires only after a deterministic decision already exists,
  to ground an explanation — never before, as an input the agent reasons over.

**Cross-cutting**
- **R19.** All agent-tier code introduced by Phase 6 is adversarially tested against a local/weak
  LLM (Ollama or a stub OpenAI-compatible server), not only against Claude — a standing testing
  rule from M1 onward, not deferred to M5.

## 5. Success metrics

| Milestone | Metric |
|---|---|
| M1 | Zero off-contract final answers escape the enum gate across the full adversarial test corpus (Claude + local/weak model). Zero cases where an `UNKNOWN`/failed triage check is narrated as safe. |
| M2 | 100% of agent runs (across both providers, once M5 lands) produce a complete, PHI-clean trace. R15 formally closed: `claims-service`/`rxclaim-emulator` export equivalent traces/metrics. |
| M3 | Zero conversation state lost across an HTTP-API session restart. Token-budget number is cited back to real M2 telemetry, not asserted without a source. |
| M4 | A simulated LLM-API outage never silently blocks a real clinical query (alert fires, request still completes or fails closed to `REVIEW` — never a raw crash or silent drop). |
| M5 | The full M1 adversarial test corpus passes unmodified against the OpenAI-compatible adapter pointed at a local Ollama model. |
| M6 | Judge flags are reviewed and none override a hard R1–R3 invariant during acceptance testing; every knowledge-base citation traces to a `triage-service` decision that already existed before retrieval fired. |

## 6. Provenance

This PRD synthesizes a structured, multi-round design process, not a single external DRAFT PRD
(contrast [`../phase2/source-prd.md`](../phase2/source-prd.md), which archives an actual source
document) — a handoff brainstorm proposing the five topics and initial milestone shape, followed
by a full codebase audit that verified or corrected every load-bearing claim in it (found: the
Phase 5/Phase 6 naming collision, the mcp-agent fail-closed gap, the Phase 2 R15 documentation
drift, and several existing conventions this phase now aligns to rather than reinvents), followed
by a decision pass resolving every open question the audit and brainstorm surfaced. The full
decision trail is [`decisions.md`](./decisions.md).
