# Decision Index (ADR-style)

Every architectural decision for Phase 6, in one auditable list: what was decided, its status,
what superseded it, and where the full rationale lives. Modeled directly on
[`docs/phase3/decisions.md`](../phase3/decisions.md) and
[`docs/phase4/decisions.md`](../phase4/decisions.md) — same status vocabulary, same convention.

**This page is an index, not a rewrite.** Each decision's reasoning lives in
[`prd.md`](./prd.md) or [`design.md`](./design.md); duplicating it here would create two
versions that drift. Follow the link for the *why*. Read this page for *what was decided, and
whether it still holds*.

Status values: **Accepted** (in force) · **Superseded** (replaced — successor named) ·
**Partially delivered** (accepted, but the repo does not yet match — the gap is named) ·
**Open** (a live, unresolved question — none currently, all H-items are closed as of this PRD).

Single letter family (**H** — "Hardening"), unlike Phase 2's split D/C families or Phase 3/4's
single letter reused per-phase (`P`, `E`) — `H` avoids collision with any existing family.

---

## H — Hardening decisions

| # | Decision | Status | Notes / supersession |
|---|---|---|---|
| **H1** | Phase 6 is its **own phase**, not folded into Phase 2 | ✅ Accepted | Phase 2's "more cloud-ready" premise contradicted its own documented cloud-delivery gap; this work is cloud-agnostic anyway; reopening a completed, previously-corrected phase repeats the status-truthfulness problem a reviewer already caught once. Rationale: [`prd.md` §1](./prd.md#1-problem-statement). |
| **H2** | Build the platform **once, as a shared reusable layer** (`agent-platform/`); **pilot on `mcp-agent`**, then carry to `claims-agent`; Phase 3/4 agents explicitly deferred | ✅ Accepted | `agent-platform/` follows the `client/clinical` precedent for a domain-shared library. Rationale: [`design.md` §1](./design.md#1-target-architecture), [`prd.md` §3](./prd.md#3-non-goals). |
| **H3** | The agent is becoming **clinician-facing** → the heavy tier (M6 policy+judge) is justified; **PHI-off-third-party is a future business rule**, not active today → build the provider seam now but **Anthropic stays the only live backend** | ✅ Accepted | Rationale: [`prd.md` §1](./prd.md#1-problem-statement), [`design.md` §4.5](./design.md#45-multi-provider--m5). |
| **H4** | Provider abstraction = **exactly two adapters** — Anthropic (native) + one OpenAI-compatible adapter (covers Llama, DeepSeek, Ollama, vLLM, hosted endpoints) | ✅ Accepted | Model choice becomes config, not code. Rationale: [`design.md` §4.5](./design.md#45-multi-provider--m5), [`milestone-plan.md` M5](./milestone-plan.md#m5--provider-abstraction--cross-model-follow-ups). |
| **H5** | Output safety is a **MUST**: tool-with-enum-output + code validation + fail-closed to `REVIEW` | ✅ Accepted | This repo's existing fail-closed thesis applied to agent *output*, not just deterministic-service *decisions*. Rationale: [`design.md` §4.1](./design.md#41-output-safety--m1). |
| **H6** | `policy.md` rules go into the **system prompt, not RAG**; RAG reserved for a **genuine knowledge base only** | ✅ Accepted | Rules always apply — retrieval is the wrong mechanism for them. Rationale: [`design.md` §4.6](./design.md#46-policy-knowledge-judge--m6). |
| **H7** | LLM-as-judge runs only on responses classified as **"important"** | ⚠️ **Superseded by H11** | Original brainstorm framing, cost-conscious. Retired once the user confirmed uniform judging is acceptable given the new local-LLM testing investment (H11) — see that entry. |
| **H8** | Build order **M1 → M2 → M3 → M4 → M5 → M6**, by dependency, not topic number; minimal viable cut = **M1 + M2** | ✅ Accepted, cut re-examined per H23 | Order: [`milestone-plan.md`](./milestone-plan.md). The "M1+M2 minimal cut" claim is explicitly deferred for reassessment to the end of M2, not decided now — see H23. |
| **H9** | Cheap multi-model testing: **stub OpenAI-compatible server** ($0 CI) / **Ollama local** ($0, weak — the harshest adversary) / **hosted OpenAI-compatible** (pennies, real quality) | ✅ Accepted | Rationale: [`design.md` §5](./design.md#5-testing-strategy). |
| **H10** | Agent output enum is **purpose-built for refill triage**, not `claims-service`'s `Outcome` verbatim — but **reuses `REVIEW`** as the literal term for the fail-closed case | ✅ Accepted | Refill triage isn't claims adjudication (domain mismatch for full reuse), but platform-wide vocabulary consistency matters for the one shared concept (fail-closed escalation). Rationale: [`design.md` §4.1](./design.md#41-output-safety--m1). |
| **H11** | The judge runs on **every response, uniformly** (supersedes H7); **local/weak-LLM adversarial testing is a standing rule from M1 onward**, not deferred to M5 — latency and cost for both are explicitly accepted | ✅ Accepted | User's explicit call: cost/latency of uniform judging is acceptable, and "quite some testing has to happen on local LLMs is the rule moving forward." Rationale: [`design.md` §3](./design.md#3-cross-cutting-principles), [`design.md` §5](./design.md#5-testing-strategy). |
| **H12** | Session store = **Postgres/Neon**; shared layer ships as a **new top-level `agent-platform/` package** from M1, not an in-place refactor extracted later | ✅ Accepted | Reuses existing repo infrastructure over introducing Redis; avoids a later extraction refactor given H2's build-once decision. Rationale: [`design.md` §4.3](./design.md#43-memory--session--m3). |
| **H13** | Memory token budget: the **real number is deferred to M3**, set from M2's telemetry; a **crude placeholder cap lands in M1** as a pure stopgap against `interactive_mode`'s current zero-bound growth | ✅ Accepted | Paired decision — don't guess the real number, but don't ship M1 leaving an unbounded-growth risk live either. Rationale: [`prd.md` R9](./prd.md#4-functional-requirements), [`milestone-plan.md` M1](./milestone-plan.md#m1--output-contract--fail-closed-enforcement). |
| **H14** | Conversational transport: a **thin FastAPI HTTP wrapper** around the existing agent loop (M3) — not REPL-only, not a full web/chat UI | ✅ Accepted | Prerequisite for M3/M4's concurrency and session testing, which a single-process REPL can't exercise. Rationale: [`design.md` §4.3](./design.md#43-memory--session--m3). |
| **H15** | M6 knowledge base: **openFDA Drug Label API** + **RxClass API**, retrieval fires only *after* a `triage-service` decision exists; `data/payer-kb/` explicitly **not** reused (domain mismatch — claims/coverage data, not drug-safety); NLM's Drug-Drug Interaction API explicitly excluded (discontinued January 2024) | ✅ Accepted | Researched and verified live 2026-08-02. Rationale + sources: [`design.md` §4.6](./design.md#46-policy-knowledge-judge--m6), [`milestone-plan.md` M6](./milestone-plan.md#m6--policy-knowledge--judge). |
| **H16** | M2's scope is **"Overall Observability"**, literally — it **closes Phase 2's R15** in `claims-service`/`rxclaim-emulator` (and backfills `fhir-service`'s missing trace propagation), architected once for the whole platform, not agent-tier-only | ✅ Accepted | Justified by the phase's own title, chosen deliberately by the user for exactly this reason. Cross-referenced into Phase 2's docs without duplication or a hardcoded milestone-number citation. Rationale: [`design.md` §4.2](./design.md#42-observability--m2). |
| **H17** | Kong's live PHI-in-logs exposure (`file-log` plugin logging raw request URIs) is **in scope for M2**, fixed opportunistically alongside PHI-redaction work | ✅ Accepted | Justified by H16's broadened scope; still requires its own explicit go-ahead before any gateway-config deploy, per this repo's standing infra-change caution. Rationale: [`design.md` §4.2](./design.md#42-observability--m2). |
| **H18** | `mcp-agent` gets its **own fail-closed data-layer guard** around the `triage-service` call — a Python analog of `HttpTriageClient.java` — landing in M1 | ✅ Accepted | Closes the audited gap: `mcp-agent` currently bypasses the only real fail-closed precedent in this codebase by calling `triage-service` directly. Rationale: [`design.md` §4.1](./design.md#41-output-safety--m1). |
| **H19** | Rate/cost posture: **hybrid** — alert-only for legitimate clinical traffic, **hard backstop only for runaway/bug-driven spend** (M4) | ✅ Accepted | Every existing rate limiter in this repo is fail-closed/block-over-limit; this is a deliberate, documented departure for the clinical-traffic case specifically, while still closing the blind spot pure alert-only would leave against a genuine bug. Rationale: [`design.md` §4.4](./design.md#44-deployment-resilience--cost--m4). |
| **H20** | A **circuit breaker wraps the LLM API call specifically** (M4) — a deliberate, documented divergence from this repo's otherwise-consistent no-breaker convention | ✅ Accepted | `HttpTriageClient.java` explicitly defers breakers as future work for internal calls; the LLM API's external/metered/cost-bearing risk profile is different enough to justify one here. Rationale: [`design.md` §4.4](./design.md#44-deployment-resilience--cost--m4). |
| **H21** | The agent's fail-closed output contract is a **standalone shape** (M1) — does **not** mirror FHIR `OperationOutcome` or `provider-registry-service`'s `{error_type, message}` | ✅ Accepted | It's a successful turn whose content is a conservative decision, not an HTTP error response — neither existing convention is a category match. Rationale: [`design.md` §4.1](./design.md#41-output-safety--m1). |
| **H22** | Observability pipeline: **OTel + OTLP**, `gen_ai.*` conventions for the agent tier, standard spans/Micrometer for the Java tier, **one exporter** repointable from local Jaeger/Grafana to Cloud Trace/Managed Prometheus via config only (M2) | ✅ Accepted | Serves both H16's expanded scope and immediate local dev-loop value without waiting on GKE Managed Prometheus scraping being confirmed active. Rationale: [`design.md` §4.2](./design.md#42-observability--m2). |
| **H23** | The milestone plan gets its **own file** (`milestone-plan.md`), not folded into `design.md` — a deliberate departure from Phase 3/4's consolidation (their own decision to fold milestone plans into `design.md`); and the **"M1+M2 minimal viable cut" claim is explicitly deferred for reassessment to the end of M2**, not decided at kickoff | ✅ Accepted | Phase 6's milestone content is long and cross-service, closer in shape to Phase 2's original `plan.md` split than to Phase 3/4's single-service builds. The minimal-cut deferral is a direct user instruction, given M2's scope grew substantially once H16 was decided. Rationale: [`milestone-plan.md`](./milestone-plan.md). |

## Conventions

- **A decision is never edited to look right in hindsight.** If reality diverges, the status
  changes to *Partially delivered* and the gap is named. If a decision is replaced, it is marked
  *Superseded* and the successor is named — the original stays (see H7).
- **Rationale lives in the normative doc, not here.** This index links; it does not restate.
- **New architectural decisions get a row here** and their rationale in `prd.md` (if normative)
  or `design.md`/`milestone-plan.md` (if design/sequencing). A decision that exists only in a PR
  description or a chat log is not recorded.
