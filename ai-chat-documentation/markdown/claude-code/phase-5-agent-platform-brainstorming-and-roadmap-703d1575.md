# Phase 5 agent-platform brainstorming and roadmap

## Turn 1

### Prompt

I want to start Phase 5. Here is a quick outcome of some brainstorming. Just internalize and wait for my next prompt for details. Not expecting any sustantive response to this prompt

___________________
✅ Agreed / decided 

Build the agent-platform capabilities once as a shared, reusable layer, pilot on mcp-agent (Phase 1 refill-triage agent — it already has the conversational shape), then carry to the Phase 2 claims stack.
Phase 5 is It's its own phase, NOT folded into Phase 2. Reasons settled: the "Phase 2 is cloud-ready" premise contradicts our documented cloud-delivery gap; this work is cloud-agnostic anyway; the conversational surface you described is Phase 1's agent; reopening a completed phase repeats the status-truthfulness problem; these are shared-platform capabilities.
Agent is becoming clinician-facing → the heavy tier (policy + judge, M6) is justified.
PHI-off-third-party = a future business rule → build the provider seam now, keep Anthropic the only live backend for now; target providers are Anthropic + Llama + DeepSeek.
Provider abstraction = two adapters only: Anthropic (native) + OpenAI-compatible (covers Llama, DeepSeek, Ollama, vLLM, and hosted endpoints). Llama-vs-DeepSeek becomes config, not code.
Output safety is a MUST: tool-with-enum-output + code validation + fail-closed to REVIEW.
policy.md into the system prompt — NOT RAG. RAG only for a genuine knowledge base, kept separate.
LLM-as-judge only for "important" responses, checking soft qualities; code enforces hard invariants.
Build order (by dependency, not your 1–5): M1 enum-gate → M2 OTel → M3 memory/context+session store → M4 deploy resilience+cost alerts → M5 provider abstraction → M6 policy+knowledge+judge. Minimal cut = M1 + M2.
Cheap Llama/DeepSeek testing: stub OpenAI-compatible server ($0 CI) / Ollama local ($0, weak — good adversary for the enum gate) / hosted OpenAI-compatible like DeepSeek API/OpenRouter/Groq (pennies, real quality).

🟡 Open issues to be brainstormed

Exact enum set for the pilot surface (dispense / review / don't-dispense is the shape; confirm the set and how REVIEW is the fail-closed sink).
Definition of an "important" response that triggers the judge.
Session-store tech (Redis vs Postgres — tie to existing infra) and where the shared platform layer lives (new agent-platform/ package vs in-place refactor).
Memory token-budget numbers — deliberately deferred until M2 metrics exist so they're set from data, not guessed.
Conversational transport — CLI REPL today; is the clinician surface a web/chat UI or API? (drives streaming + session design).
M6 RAG corpus (formulary? drug info?) or defer RAG entirely.
Phase number/name — a docs/phase5/ readiness-assessment already exists; confirm this is Phase 5 vs Phase 6, and whether the observability slice formally closes Phase 2's unbuilt R15.
_______________________________________

### Claude response

Internalized — Phase 5 decisions and open issues saved. Ready for your next prompt.

## Turn 2

### Prompt

Here is a handoff document. Just internalize without sustantive response. I will feed you some more info before soliticing ananysis and critique:

_________________

# Phase 5 Handoff — Agent Platform Hardening (fhir-agent)

> Paste this whole document as the first message of a fresh Claude Code session to
> bootstrap Phase 5. It captures brainstorming already done; **decisions marked ✅ are
> settled — implement them, don't re-open them.** Items marked 🟡 are for you to resolve
> with me early.

## 0. How to use this doc
You are resuming a multi-session effort on the `fhir-agent` project. Phases 1–4 are built
and merged. This document defines **Phase 5: Agent Platform Hardening**. Start by reading
`CLAUDE.md`, `docs/README.md`, and the memory file `phase5-agent-hardening.md`, then confirm
the 🟡 open questions in §8 with me before writing milestone docs.

## 1. Project orientation (what fhir-agent is)
An agentic healthcare platform. A clinician asks a natural-language question; an LLM/agent
layer fetches FHIR data and returns a structured recommendation. Deterministic services
decide; the agent orchestrates and explains. Two guiding sentences the whole codebase obeys:
- **AI explains and orchestrates; deterministic services decide.**
- **The legacy core is wrapped, not rewritten.**

Relevant components:
- `mcp-agent/` (Python) — **Phase 1** refill-risk-triage agent. Anthropic tool-use CLI. This
  is the **pilot target** for Phase 5 (it already has the conversational shape).
- `claims-agent/` (Python) — **Phase 2** explanation agent; explains adjudication decisions,
  non-authoritative. The **second target**, later.
- `claims-service/`, `rxclaim-emulator/`, `triage-service/`, `fhir-service/`, `epic-emulator/`,
  gateway (Kong) — the deterministic tiers the agents call.
- Docs live in `docs/` (guides) and `docs/phase2../phase4/` (per-phase). Decisions index:
  `docs/phase2/decisions.md`.

Working rules (from `CLAUDE.md`): two git worktrees; **never commit to `main`** — always a
feature branch + PR; never self-merge. Treat claims/clinical data as **PHI**.

## 2. What Phase 5 is
Harden the **agent tier** to the same standard as the decision tier, and turn the pilot agent
into a **clinician-facing conversational surface**. Built as a **shared, reusable platform
layer** (like `client/clinical` is shared) and **applied to one agent first**.

**Scope decision (✅):** Option (c) — build the platform once, **pilot on `mcp-agent`** (Phase 1
refill agent), then carry to the Phase 2 claims stack. **Explicitly defer Phase 3/4 agents.**
This is a **new phase, not an extension of Phase 2.** (Rationale in §7.)

## 3. The five topics this phase covers
1. **Memory** — short-term (the in-context transcript) vs long-term (cross-session store).
   Three distinct axes, do not conflate: per-conversation token budget (cap + compact),
   concurrent-session count (the thing that actually autoscales = compute), cross-session
   persistence store. `MAX_TOKENS=1024` today is the **output** cap, not memory. **Clinical
   rule: re-fetch from FHIR, never act on recalled state** (data changes; stale recall = the
   fail-open bug in disguise).
2. **Deployment + observability tie-in** — bounded queue + per-request deadline (avoid the
   "queue of doom"); the "queue" is really a **client-side token-bucket / concurrency limiter
   in front of the rate-limited, paid LLM API** (that, not local CPU/RAM, is the bottleneck);
   rate/cost **alerts, not auto-shed** (clinical — never silently drop a care request);
   Grafana needs a metrics pipeline **first** (instrument → Prometheus → dashboard).
3. **Observability (full)** — OTel. **A trace = one agent run; spans = reasoning steps** (each
   model call, each tool call). Use OTel `gen_ai.*` semantic conventions. **Propagate the
   traceID *through* tool calls into claims/triage/fhir** so one trace spans cognition →
   deterministic services. **PHI-redact span attributes** (that's where PHI leaks).
4. **Follow-ups + multi-model** — Meta's model = **Llama**; also **DeepSeek** (V3 general, R1
   reasoning). Self-host via vLLM/TGI/Ollama, all OpenAI-compatible. **Driver = PHI residency
   (future rule), NOT cost.** Multi-turn already works in the REPL; the hard part of multi-model
   is normalizing tool-calling + translating conversation history across providers.
5. **Output safety** — `policy.md` of NL rules loaded into the system prompt (**NOT RAG** — the
   rules always apply). RAG only for a real **knowledge base** (separate concern). **Limit the
   final answer to N enum options** via tool-with-enum-output **+** code validation **+**
   **fail-closed to REVIEW** if the model returns anything else. Optional **LLM-as-judge** on
   "important" responses for *soft* qualities only (groundedness, tone, PHI leak) — **code
   enforces hard invariants, never a judge model.** A narrow output surface is also the
   strongest control against "answers the LLM shouldn't give."

## 4. Milestones (✅ order is by dependency, not by topic number)
| M | Milestone | Topic | Why here | Weight |
|---|---|---|---|---|
| **M1** | Output contract & enum gate (tool-with-enum-output; validate in code; fail-closed to REVIEW; narrow the surface) | 5 | Cheap, independent, highest safety value; extends the fail-closed thesis. Do first. | S |
| **M2** | Observability foundation (OTel traces/spans; `gen_ai.*`; traceID propagated into services; PHI redaction) | 3 | The lens. Underpins tuning M3, seeing M4, evaluating M6. | M |
| **M3** | Context & memory mgmt (explicit token budget + documented rationale; compaction at threshold; externalized session store; re-fetch-don't-recall) | 1, 4 | Needs M2's token metrics to set limits honestly. | M |
| **M4** | Deploy resilience & cost control (bounded queue + deadline; token-bucket/concurrency limiter; rate/cost alerts; Grafana dashboards) | 2 | Needs M2 metrics + M3 session model. | M |
| **M5** | Provider abstraction + cross-model follow-ups (2 adapters: Anthropic native + OpenAI-compatible; history translation) | 4 | Backbone for M6; capture follow-up code detail here for the report. | L |
| **M6** | Policy + knowledge + judge (`policy.md` into system prompt; optional RAG knowledge base; LLM-as-judge on important responses) | 5 | Sits on M1 + M5; heaviest; justified because the agent is clinician-facing. | L |

**Minimal viable cut:** M1 + M2 (closes the biggest agent-tier safety gap and gives you eyes).

## 5. Key technical decisions (✅ settled)
- **Provider layer = exactly two adapters:** `Anthropic` (native tool-use) and
  `OpenAI-compatible` (one adapter covering Llama, DeepSeek, Ollama, vLLM, and hosted
  endpoints like DeepSeek API / OpenRouter / Together / Groq). Llama vs DeepSeek = base-URL +
  model-name **config**, not new code. **Anthropic stays the only live backend for now**; the
  others exist to prove the seam.
- **Enum gate:** structured output (tool with enum) constrains *shape*; **still validate in
  code**; **fail closed to REVIEW** on anything off-contract. This is the project's fail-closed
  safety thesis applied to the agent's *output*.
- **Rules vs knowledge:** behavioral rules → `policy.md` into the system prompt (always apply,
  no retrieval). Knowledge base → RAG (retrieve relevant subset). **Do not use RAG for rules.**
- **Judge:** reserve for "important" responses; checks soft qualities; never the enforcer of
  anything code can enforce.
- **Cheap multi-model testing:** stub OpenAI-compatible server ($0 CI, same JDK-HttpServer /
  Python-http stub pattern already used in `HttpTriageClientTest`) · Ollama local ($0, weak —
  a *good adversary* for the enum gate) · hosted OpenAI-compatible (pennies, real quality).

## 6. Current code facts (verify before relying — memory may be stale)
- `mcp-agent/src/agent/agent.py`: hardcoded to Anthropic (`import anthropic`,
  `MODEL="claude-sonnet-4-5"`, `MAX_TOKENS=1024`), a `SYSTEM_PROMPT` constant, an agent loop
  `run_query(client, user_input, messages) -> (final_text, messages)`, and an
  `interactive_mode` REPL that **persists `messages` across turns** (follow-ups work in the
  REPL). The single-shot `--query` path does **not** persist across invocations.
- `mcp-agent/src/agent/tools.py`: tool definitions + `execute_tool`.
- **No observability anywhere** (no OTel/metrics/tracing) — clean slate.
- `claims-agent` has a `--no-llm` deterministic mode — useful as a live oracle for drift
  detection.

## 7. Why its own phase, not folded into Phase 2 (✅ — do not re-open)
- "Phase 2 is more cloud-ready" is **false per our own docs** — Phase 2 has cloud *design* but
  **no root Terraform module / not deployable** (the documented cloud-delivery gap).
- Cloud-readiness is **irrelevant** — all of this is built and tested locally, cloud-agnostic.
- The clinician conversational surface described (patient/med disambiguation, dispense/review/
  hold) is **Phase 1's `mcp-agent`**, not Phase 2's claims *explainer*.
- Reopening a completed, tagged, "done" Phase 2 repeats a status-truthfulness problem.
- These are **shared-platform capabilities** — build once, reuse across agents.
- Honest carve-out: the **observability slice may legitimately close Phase 2's unbuilt R15**,
  but do it *from the shared layer*, not by reopening Phase 2's M0–M7.

## 8. Open questions to resolve with the user first (🟡)
1. Exact **enum set** for the pilot surface and how REVIEW is the fail-closed sink.
2. Definition of an **"important" response** that triggers the judge.
3. **Session-store tech** (Redis vs Postgres) and **where the shared layer lives**
   (`agent-platform/` package vs in-place refactor).
4. **Memory token-budget numbers** — deliberately deferred until M2 metrics exist.
5. **Conversational transport** — CLI REPL today; web/chat UI or API? (drives streaming +
   session design).
6. **M6 RAG corpus** scope, or defer RAG.
7. **Phase number/name** confirmation (a `docs/phase5/` readiness-assessment already exists).

## 9. Cross-cutting principles (apply to every milestone)
- **Fail-closed everywhere, consistently** (enum → REVIEW; queue deadline → fail closed; judge
  disagreement → hold for human; memory → re-fetch not recall).
- **Deterministic code decides; the LLM orchestrates and explains** — the project thesis; the
  enum gate *is* this thesis applied to agent output.
- **PHI-safe is a driver, not just a constraint** (redact spans; don't persist raw PHI;
  self-hosting is a PHI *win*, which is why it's on the roadmap at all).
- **Observability first** — you can't tune memory, see deployment issues, or evaluate
  multi-model quality without M2.
- **The agent is non-authoritative** — it never decides anything clinical/financial.

## 10. Relevant existing memories to check
- `llm-tool-schema-oneof-unreliable` — **directly relevant to M1 and M5**: live Claude
  stringifies `oneOf`-typed nested tool params instead of emitting a native object. Flatten
  tool schemas; validate cross-field rules downstream. Expect worse behavior from small
  self-hosted models — another reason the enum gate validates in code.
- `pytest-test-filename-collision` — same-named `test_*.py` in different packages collide under
  this repo's `import-mode=importlib`. Check before adding any test file.
- `secret-values-never-print` — never echo secret values; redact in output. Extends naturally
  to PHI redaction in traces/logs.

## 11. A comprehensive report is owed (do not forget)
After the milestones (or several) land, the user will ask for a **comprehensive report**. It
must include, at minimum:
- **Follow-ups down to code snippets** — the `run_query(messages)→messages` mechanics, REPL
  persistence, the single-shot gap, and how each enhancement (session store, context
  compaction, tool-result compaction, re-fetch-don't-recall) changes specific lines; plus how
  the provider adapter translates conversation history for Llama/DeepSeek.
- **Memory sizing** — where each limit is set, the rationale for each number, and the autoscale
  path (per-conversation compaction vs session-count scaling vs store).
- **Observability** — the actual Grafana panels and the end-to-end trace/span/attribute schema.
Produce it *after* implementation, grounded in real code and real metrics — not predicted.

## 12. Suggested first move for Phase 5 session
Confirm the §8 open questions with the user, then draft `docs/phase5/plan.md` +
`docs/phase5/README.md` (canonical status, milestone table, decisions) on a `docs/phase5-*`
branch — planning only, no implementation — and open a docs PR. Then start **M1 (enum gate)**
as the first implementation PR, since it's cheap, independent, and the highest safety value.

### Claude response

Internalized — handoff doc noted, no action taken. Ready for the next piece of info.

## Turn 3

### Prompt

Now, internalize this snippet as well, and tell me if you can find what Topic 1, topic 2, 3, 4, and 5 are. If not, I will feed you that as well:

______________

🧠 To be Internalized for the future comprehensive report
I'm carrying these forward (also saved to memory phase5-agent-hardening.md):

Topic 4 down to code snippets — run_query(messages)→messages mechanics, REPL persistence, the single-shot --query gap, and how each "what-could-be-done" (session store, context compaction, tool-result compaction, re-fetch-don't-recall) changes specific lines; plus provider-adapter conversation-history translation for Llama/DeepSeek.
Topic 1 — where each memory limit is set, the rationale for each number, and the autoscale path (per-conversation compaction vs session-count scaling vs persistence store).
Topics 2 & 3 — the actual Grafana panels and the end-to-end trace/span/attribute schema.
Timing: produce it after the milestones (or several) land, not before.

### Claude response

Yes — mapping to the handoff doc's §3 topic list:

- **Topic 1 = Memory** (short-term/long-term, token budget, compaction, session store, re-fetch-don't-recall)
- **Topic 2 = Deployment + observability tie-in** (bounded queue/deadline, token-bucket limiter, rate/cost alerts, Grafana dashboards)
- **Topic 3 = Observability (full)** — OTel traces/spans, `gen_ai.*` attributes, traceID propagation, PHI redaction
- **Topic 4 = Follow-ups + multi-model** (provider abstraction, Llama/DeepSeek, history translation)
- **Topic 5 = Output safety** (policy.md in system prompt, enum gate, fail-closed to REVIEW, judge)

Your snippet is consistent with that: "Topic 4 down to code snippets" → follow-ups/multi-model mechanics; "Topic 1" → memory limits/autoscale; "Topics 2 & 3" → Grafana panels + trace/span schema. No gaps — I don't need you to feed the topic list separately.

I'll fold this report-obligation detail into the `phase5-agent-hardening.md` memory now so it's tied to the right topic numbers.

Confirmed — I can derive the topics directly from the handoff doc's §3 list (no gap, you don't need to feed it separately):

1. **Memory**
2. **Deployment + observability tie-in**
3. **Observability (full — OTel)**
4. **Follow-ups + multi-model**
5. **Output safety**

Your snippet's references line up cleanly: "Topic 4" = follow-ups/multi-model code mechanics, "Topic 1" = memory limits/autoscale, "Topics 2 & 3" = Grafana panels + trace/span schema. I've updated the `phase5-agent-hardening.md` memory to carry this topic numbering plus the report obligations, so it's tied to the right numbers when you ask for the comprehensive report later.

## Turn 4

### Prompt

Now critique everything, analyze what has been implemented and documented in the codebase to confirm what you need to learn about past work, and tell me what is clear and what we need to discuss. Do not jump into planning now.

### Claude response

# Phase 5 Critique — findings from the actual codebase and docs

Four parallel audits (mcp-agent code, claims-agent/Phase 2, Phase 4/Phase 5 docs + observability infra, deterministic-tier conventions). No planning below — just what's confirmed, what's wrong, and what needs a decision from you before any milestone doc gets written.

## What's clear and holds up

**The handoff doc's code claims about mcp-agent are all accurate.** `agent.py`'s hardcoded Anthropic client/model/token cap, `SYSTEM_PROMPT`, `run_query(messages)→messages` mechanics, REPL persistence vs. `--query` non-persistence, `tools.py`'s two tools — all verified line-for-line. Good foundation to build the report on later.

**The cloud-delivery-gap claim is accurate and well-documented**, quotable directly from `docs/phase2/plan.md`'s "⚠️ Cloud-delivery gap" callout and `decisions.md` D8: no root Terraform module, no `deploy-phase2.sh`, only per-service Cloud Run stubs. The "Phase 2 isn't more cloud-ready" reasoning is sound.

**The status-truthfulness incident is real**, commit `0fcc196` ("status truth, safety semantics, gateway runbook, ADR index") — a reviewer did catch Phase 2 asserting things the repo didn't support. That precedent is legitimate grounds for not casually reopening Phase 2.

**A fail-closed convention already exists and is load-bearing** in `claims-service`: `Severity{DENY,PEND,REVIEW,INFO}` / `Outcome{APPROVED,DENIED,PENDED,ROUTED_FOR_REVIEW}`, plus the documented "unknown ≠ safe" lesson (`docs/testing-guide.md`: *"Make 'I don't know' a distinct value"*). `REVIEW` is already a specific, defined status in this codebase, not a blank slate — the plan's "fail-closed to REVIEW" choice happens to align with it.

## Corrections needed

- **Phase 2 was never "tagged."** Only `phase1-v1` exists as a git tag. Phase 2's "done" status lives in prose (`docs/phase2/README.md`'s canonical statement), not a tag. If this word carries into a milestone doc, it repeats an error.
- **`HttpTriageClientTest`'s stub-server pattern lives in `claims-service` (Java), not `triage-service`.** Triage-service has no HTTP-client tests of its own (it's the server, not a client). Reusing that pattern for mcp-agent means porting a Java/JUnit idiom to Python — nothing equivalent exists in Python yet, and no stub-server library (`respx`, etc.) is a dependency anywhere.
- **The R15 ("OTel tracing wired") claim in Phase 2's own milestone table is itself inflated.** No `opentelemetry` or `micrometer` dependency exists in `claims-service`/`rxclaim-emulator`, no `traceId`/correlation-ID code anywhere. This is a second, uncaught instance of the same documentation-vs-code gap the reviewer flagged once already — worth deciding whether to fix in Phase 2's docs opportunistically or just note it and move on.

## The collision that needs your call first

**`docs/phase5/` already has content, and it isn't this.** The only file there — `phase4-testing-and-analysis.md`, on this exact branch — is explicitly labeled *"DRAFT... not a Phase 5 PRD itself,"* and its entire content is a post-merge Phase 4 safety review, headlined by a **live, unfixed clinical-safety bug**: `epic-emulator`'s 20-record pagination cap silently drops allergy records, flipping a HIGH-risk (do-not-dispense) conflict to LOW-risk (safe to dispense) when a patient has >20 allergies. The doc says this should be fixed "**before Phase 5 starts**," and separately proposes Phase 5 scope around decomposing `epic-emulator`, not agent hardening.

`docs/phase4/README.md` and `docs/README.md` both currently reserve "Phase 5" for that epic-emulator decomposition work — "no timeline set," but the slot isn't empty. Nothing in the roadmap reserves "Phase 6" either. So: is agent-platform-hardening now Phase 5 (superseding/absorbing the epic-emulator content) or a different phase number, and — separately from naming — does the open pagination bug need to be dealt with before or alongside this work, given it's a live false-negative on the exact drug-allergy-conflict check `mcp-agent` calls?

## Things the plan should align to rather than invent

- **The triage rule engine (`rules.py`) is not fail-closed** — an unrecognized drug silently falls through to the `LOW`/"safe to dispense" default. Fail-closed only exists one layer up, in `HttpTriageClient.java`'s wrapper (`UNKNOWN` never `LOW` on any failure/timeout/unrecognized response). **mcp-agent talks to triage-service directly, bypassing that Java wrapper entirely** — so today there is no fail-closed protection on that path at all; `tools.py` defaults to the string `"UNKNOWN"` only on parse failure, and nothing stops the LLM from recommending dispense anyway. This is a more concrete version of the "output safety" gap than the handoff doc's framing — worth having in view for M1.
- **PHI redaction has a real precedent to copy**: `provider-registry-service`'s `sanitize_location()` + structural (not scrub-after-the-fact) logging middleware. There's also a documented near-miss (`docs/developer-guide.md`): a design doc claimed a PHI-safety mechanism existed for five milestones before anyone checked — it didn't. Direct caution against writing "PHI-redact span attributes" in a plan without verifying it's wired.
- **A live, currently-open PHI exposure already exists**: Kong's `file-log` plugin logs raw request URIs (containing patient/member IDs) to stdout today, per `docs/gateway-runbook.md`'s own acknowledgment. Worth deciding whether Phase 5's observability/redaction work touches this opportunistically.
- **Timeout convention across the deterministic tier is consistent**: explicit connect-timeout + overall-timeout pairs (5s/20s), and a timeout is folded into the *same* fail-closed branch as any other failure — never a special "assume okay" path. `HttpTriageClient.java` explicitly defers circuit breakers as future work ("changes latency, not policy"). mcp-agent today has one flat 30s timeout, no distinct connect timeout, no retry. If M4 wants a circuit breaker in front of the LLM API, that's a new pattern relative to repo precedent, not an extension of one.
- **Every existing rate limiter in the repo (Kong's `fhir-rate-limit`, provider-registry-service's in-process limiter) is fail-closed/block-over-limit (429).** None "alert without shedding." The plan's M4 proposal to alert-not-shed on the LLM call is a genuine departure from every precedent here — and arguably in tension with its own "never silently drop a care request" framing, since alert-only means the request still goes through uncapped. That needs an explicit rationale, not an implicit one.
- **No single error-shape convention exists to inherit** — FHIR `OperationOutcome` (claims-service, epic-emulator, fhir-service) vs. plain FastAPI `{"detail": ...}` (triage-service) vs. structured `{error_type, message}` (provider-registry-service) are three unreconciled shapes. M1's output contract needs to pick one deliberately and say why, not assume there's a repo standard.

## Other facts worth having before any milestone doc

- **claims-agent already has a `--no-llm` deterministic mode** (template-rendered explanation, no API key needed) that mcp-agent lacks — a real existing fallback pattern, potentially relevant to M1/M6's fail-closed design, that the handoff doc didn't mention.
- **Neither agent has any provider abstraction, memory persistence, or observability today** — both are equivalently minimal Anthropic-only scripts. The "carry to Phase 2's claims stack" premise is architecturally sound (nearly identical skeletons), but there's no existing asymmetry to exploit — it's a clean build for both.
- **Gateway-level observability is not a clean slate**: Kong's Prometheus plugin and a GKE-Managed-Prometheus `ServiceMonitor` are already declared (though not confirmed scraped) — but only on the Phase 1 KIC deployment, not the Phase 2 docker-compose Kong that fronts triage/claims locally, and not at the application/LLM level anywhere. M2 should probably feed that existing pipeline rather than stand up a parallel one.
- **The `oneOf`-schema-fragility memory concern doesn't apply to any tool schema that exists today** — both current tools (`get_patient_summary`, `assess_refill_risk`) are flat single/dual-string-param schemas with zero nesting. It's a forward-looking concern for whatever M1's enum-output tool or M5's cross-provider schemas end up shaped like, not a current bug to fix.

## What needs to be discussed (merging the handoff's §8 with what the audit surfaced)

1. **Phase numbering and the epic-emulator collision** (new, and probably the highest-priority one — it affects the branch/doc structure of everything else).
2. Relationship to the open pagination safety bug — block Phase 5 on it, run in parallel, or explicitly out of scope with a stated reason.
3. Enum set for the pilot surface + REVIEW semantics — now informed by `claims-service`'s existing `Severity`/`Outcome` vocabulary; decide whether to reuse it or diverge deliberately.
4. Whether the "alert not auto-shed" rate/cost control is intentional given it contradicts every existing rate-limiter's fail-closed posture.
5. Error-shape choice for the agent's fail-closed output (FHIR `OperationOutcome` vs. `{error_type, message}` vs. something new).
6. Whether M2 observability plugs into the existing (declared-but-unconfirmed) Kong/Managed-Prometheus pipeline or stands alone.
7. Whether to touch the live Kong PHI-in-logs exposure while doing PHI-redaction work, or leave it out of scope.
8. The rest of the original §8 list (session-store tech, "important" response definition, transport, RAG corpus, memory token-budget numbers) — unchanged, still open.

## Turn 5

### Prompt

Tell me a list of cleanup steps to take, such as document correction to reflect status and Phase numbering, tagging, and clearly documenting remaining bugs un approproate phase's documentation (for futire work in Calude code sessions dedicated to that phase). Don't make any changes yet, just outline the steps and critique them

### Claude response

Here's the cleanup list, ordered by dependency (later steps assume earlier ones are resolved). Nothing executed — outline + critique only.

## 1. Correct the Phase 2 observability status (R15)

Fix `docs/phase2/plan.md`'s milestone table (M3/M4 currently say "OTel tracing wired") and add a `decisions.md` entry acknowledging no `opentelemetry`/`micrometer` dependency or trace/correlation-ID code actually exists in `claims-service`/`rxclaim-emulator`. Model it on the existing "⚠️ Cloud-delivery gap" callout in the same file — same pattern, same doc, different gap.

**Critique:** This is the same status-truthfulness failure mode the reviewer already caught once (commit `0fcc196`), just in a spot that review pass missed. Doing it now is cheap (docs-only PR) and closes the loop honestly. Risk is low, but it does mean re-touching a "closed" phase's docs — which is exactly the thing you decided Phase 5 should *not* do for substantive work. I'd distinguish: **correcting a false status claim is not "reopening Phase 2's work"** — it's fixing a factual error, same class of edit as the original truthfulness commit. Worth stating that distinction explicitly in the PR description so it doesn't read as scope creep.

## 2. Resolve the Phase 5 naming collision

Decide: does agent-platform-hardening become **Phase 5** (superseding the epic-emulator-decomposition content already sitting there) or **Phase 6**? Then update `docs/README.md`'s roadmap table and `docs/phase4/README.md`'s "a future Phase 5 would decompose along whatever the coupling note shows" line to match.

**Critique:** This is a decision, not just a doc edit — I flagged it as open in the last message and it's still open. It blocks steps 3 and 4 below, so it has to happen first. My read: the epic-emulator-decomposition content is thin (one draft doc, no timeline, explicitly not a PRD) versus agent-hardening being a fully-scoped multi-milestone effort — so renumbering epic-emulator work to Phase 6 (or folding it into a Phase 4b/4c alongside the safety-bug fix) and giving agent-hardening the Phase 5 slot is probably the lower-friction path. But that's my recommendation, not a settled fact — flagging it for your call, not deciding it here.

## 3. Relocate the existing `docs/phase5/phase4-testing-and-analysis.md`

Once step 2 is decided, move that file to live under `docs/phase4/` (it's substantively a Phase 4 follow-up analysis, not Phase 5 content) or renumber it to match wherever epic-emulator-decomposition work lands.

**Critique:** Pure `git mv` + internal-link fixes, low risk, but it's meaningless to do before step 2 — moving it and then reversing the decision is wasted churn. Also worth checking whether the current branch name (`docs/phase5-readiness-assessment`) itself should be renamed/reused or abandoned in favor of a fresh branch for the real Phase 5 kickoff docs — the branch name currently promises something that isn't what you're about to build there.

## 4. Give the pagination safety bug a durable, phase-independent home

Right now the bug lives only in that one draft doc. Add it as a numbered entry in `docs/phase4/decisions.md` (or a new `docs/phase4/known-issues.md` if the repo doesn't already have a lighter-weight "open bug" doc type) and keep the warning banner already in `docs/phase4/README.md` pointing at it.

**Critique:** This is the most important step for "future Claude Code sessions" discoverability — a session picking up `epic-emulator` work later has no reason to know a not-yet-a-PRD file on a docs branch exists, but it *would* read `docs/phase4/README.md` and `decisions.md` for that area. The repo already has a `decisions.md` convention (lettered/numbered entries like D8, E10) — reuse that shape rather than inventing a new doc type; that matches existing convention more cleanly than a new `known-issues.md`. Low risk, high value, should happen regardless of how step 2 resolves.

## 5. Document the mcp-agent fail-closed gap we found this session

The finding that mcp-agent calls `triage-service` directly, bypassing `HttpTriageClient`'s fail-closed wrapper, with nothing in code stopping the LLM from recommending dispense on an `UNKNOWN` risk code — currently exists only in this conversation. Write it up as a decision/known-gap entry, most naturally as an input to Phase 5 M1 rather than retroactively into Phase 1 docs (Phase 1 is tagged `phase1-v1` as "done" — same tension as step 1, but here the gap is genuinely new work, not a false status claim, so it belongs in the *next* phase's docs, not a correction to the last one).

**Critique:** I'd deliberately keep this out of Phase 1's docs even though the bug lives in Phase-1-owned code — editing a tagged "done" phase to add a newly-discovered gap is a different (and messier) thing than fixing a factual status error, and it's exactly the kind of scope-widening CLAUDE.md tells me to avoid without being asked. Better home: a "known gaps this milestone must address" section in whatever `docs/phase5/plan.md` M1 ends up being — it's real input, not phase-2-style status cleanup.

## 6. Git tagging

Convention observed: `phase1-v1` marks a snapshot taken *at a phase boundary*, not "phase complete" in the abstract. To match that pattern, `phase2-v1` and `phase3-v1` would need to be tagged retroactively at the actual merge commits where each phase's last milestone landed (found via `git log`, not just tagged at current HEAD) — before Phase 5 starts would be the natural boundary for a `phase4-v1`-or-whatever-it's-called tag, **except Phase 4 is explicitly not fully closed** (open safety bug), so tagging it as a clean boundary right now would recreate the exact status-truthfulness problem in a git tag instead of a doc.

**Critique:** This is the step I'd push back on hardest as "not yet." Retroactively tagging Phase 2/3 has real value (consistent, navigable history) but is pure completeness/hygiene, not blocking anything — I'd rank it lowest priority of the six. Tagging Phase 4 right now is actively inadvisable given the open bug; if you want a Phase-4 boundary tag at all, it should wait until step 4's bug is fixed (or the tag name should honestly encode "milestones merged, safety finding open," which is awkward enough that it argues for just waiting). Also note: tags that get pushed to `origin` are a shared-state action — per your own git rules I'd confirm before pushing any of them, even though creating a local tag alone is cheap/reversible.

## Sequencing summary

Steps 1 and 4 are independent and safe to do now. Step 2 is a decision that gates 3. Step 5 can happen alongside 2/3 since it doesn't depend on the naming outcome. Step 6 is optional hygiene, lowest priority, and should explicitly exclude Phase 4 until the bug's fixed.

## Turn 6

### Prompt

Answer to Step 2: 

Agent-platform-hardening should become Phase 6. Phase 5 documentation should be enhanced to descrinbe clearly what it is reserved for, including potentially uopdating top level README documentation describing the phases. No need to do any coding for Phase 5. Just make super clear everywhat what it is for.

_____________________

Now tell me if you are ready to do all 6 steps you identified above. Over-communicate in documentation, including for bugs remaining in any Phase. I am supposed to have dedicated Claude code sessions for each phase, so I will go to appropriate sessions to fix bugs

### Claude response

Confirmed: PR #54 is already open on this branch (`docs/phase5-readiness-assessment` → `main`), clean working tree, and `phase1-v1` is the only tag — so I have exact current state, not assumptions.

Revised step list per your Phase 6 decision, and yes — **ready to execute**, pending one open question on step 5 below.

## Revised steps

**1. Phase 2 R15 status correction** — unchanged. Docs-only, fix the "OTel tracing wired" overstatement in `docs/phase2/plan.md` + add a decisions.md entry, same pattern as the cloud-delivery-gap callout.

**2. Phase 5 reservation + roadmap update** — now the core deliverable, not a rename:
- Add/expand `docs/phase5/README.md` as the canonical status doc (matching the phase2/3/4 pattern): Phase 5 = reserved for epic-emulator decomposition, blocked/informed by the open pagination bug, not started, no timeline, no code yet.
- Update `docs/phase4/README.md`'s "a future Phase 5 would decompose..." line into a firm cross-reference to that new README.
- Update `docs/README.md`'s top-level roadmap table: firm up Phase 5's entry, and add a Phase 6 row for agent-platform-hardening — **as a name/reservation only** ("Phase 6 (reserved): Agent Platform Hardening — brainstormed, not started, no scope doc yet"), not a scope dump, consistent with your "no coding for Phase 5" instruction extending to "no premature Phase 6 planning doc" either.

**3. Relocate `docs/phase5/phase4-testing-and-analysis.md`** — **now moot.** Given Phase 5 is confirmed reserved for epic-emulator decomposition, that file is already in the right place. No move needed — this step collapses into step 2 (I'll fold its content in as the input document, referenced from the new `docs/phase5/README.md`, rather than treating it as misplaced).

**4. Durable home for the pagination bug** — unchanged, and now has an obvious target: a `decisions.md`/known-issues entry under `docs/phase4/`, cross-linked from both `docs/phase4/README.md`'s existing warning banner and the new `docs/phase5/README.md` (since it's a stated precondition for Phase 5 starting).

**5. mcp-agent fail-closed gap (bypasses `HttpTriageClient`'s wrapper)** — **this is the one open question.** This finding is agent-hardening input, i.e. Phase 6 territory, but per your "no premature Phase 6 doc" instruction there's no `docs/phase6/` to put it in yet, and your dedicated-session-per-phase model suggests Phase 6 planning belongs in its own future session, not this cleanup pass. Options:
   - **(a)** Leave it out of the repo entirely for now — it stays in my memory (`phase5-agent-hardening.md`, which I'll rename to reflect Phase 6) and I resurface it when a Phase 6 session actually starts.
   - **(b)** Add one line to the Phase 6 placeholder row in `docs/README.md` — "known input already identified: mcp-agent calls triage-service directly, bypassing the fail-closed wrapper claims-service uses" — enough of a breadcrumb that it's not repo-invisible, without writing a scope doc.
   
   I'd lean (a) — it's a real gap but it's about mcp-agent's *current* behavior, not a documented commitment, and stuffing it into a roadmap placeholder risks reading as Phase 6 scope-setting, which you didn't ask for here. Your call.

**6. Git tagging** — unchanged, still lowest priority. Confirming: do you want retroactive `phase2-v1`/`phase3-v1` tags done in this pass at all, or fully deferred to a later cleanup? Either way, no Phase 4 tag until the pagination bug is fixed — that part isn't up for debate given the precedent you're trying to avoid repeating.

## Branch/PR structure I'd use

- **Steps 2, 3, 4** (all Phase 4/5-related) → continue on this branch, updates PR #54. Natural fit, no new branch needed.
- **Step 1** (Phase 2 R15 fix) → separate branch + new PR — different area of the repo, unrelated concern, shouldn't ride along in a PR titled about the Phase 4 testing pass.
- **Step 5** → no repo commit if we go with option (a); a small addition to the existing PR #54 if (b).
- **Step 6** → separate action entirely (not a PR), and only after you confirm scope.

Confirm the step 5 choice and step 6 scope and I'll start on step 1 + steps 2-4 (two branches/PRs) right away.

## Turn 7

### Prompt

Proceed with all steps above, with the following modifications. Don;t star if the modifications don't make sense:

* Change Phase 6 naming to "Agent platform hardening plus overall Observability"
* Tag all phases in whatever state then are complete so far, except Phase 5 which deserves no tag IMO

### Claude response

*[Claude has not completed this turn yet.]*

<details>
<summary>Execution details — 21 tool events</summary>

### Turn 1 activity

- **Bash** `cat /home/vscode/.claude/projects/-workspaces-fhir-agent/memory/phase5-agent-hardening.md`
- **Write** `/home/vscode/.claude/projects/-workspaces-fhir-agent/memory/phase5-agent-hardening.md`
- **Edit** `/home/vscode/.claude/projects/-workspaces-fhir-agent/memory/MEMORY.md`

### Turn 3 activity

- **Read** `/home/vscode/.claude/projects/-workspaces-fhir-agent/memory/phase5-agent-hardening.md`
- **Write** `/home/vscode/.claude/projects/-workspaces-fhir-agent/memory/phase5-agent-hardening.md`
- **Edit** `/home/vscode/.claude/projects/-workspaces-fhir-agent/memory/MEMORY.md`

### Turn 4 activity

- **ToolSearch** `select:TodoWrite`
- **TodoWrite** `{"todos": [{"content": "Explore mcp-agent code (agent.py, tools.py, tests) to verify handoff doc's code claims", "status": "in_progress", "activeForm": "Exploring mcp-agent code"}, {"content": "Explor…`
- **Agent** `Audit mcp-agent code reality`
- **Agent** `Audit claims-agent and Phase 2 status`
- **Agent** `Audit phase4/phase5 docs and observability infra`
- **Agent** `Audit deterministic tier and gateway patterns`
- **TodoWrite** `{"todos": [{"content": "Explore mcp-agent code (agent.py, tools.py, tests) to verify handoff doc's code claims", "status": "completed", "activeForm": "Exploring mcp-agent code"}, {"content": "Explore…`

### Turn 6 activity

- **Bash** `git status && echo "---LOG---" && git log --oneline -8 && echo "---TAGS---" && git tag -l -n99 && echo "---REMOTE BRANCH---" && git branch -vv | head -5`
- **Bash** `gh pr list --head docs/phase5-readiness-assessment --state all 2>&1`

### Turn 7 activity

- **Bash** `git log --oneline --all | grep -iE "phase ?2.*(complete|done|m7)|phase ?3.*(complete|done|m7)|phase ?3.*m1|phase ?2.*m0" | head -30`
- **Bash** `git log --oneline --merges main | tail -40`
- **Bash** `git log --oneline --merges main | wc -l && echo --- && git log --oneline --merges main | sed -n '1,80p'`
- **TodoWrite** `{"todos": [{"content": "Confirm both modifications make sense (naming + tagging exceptions)", "status": "completed", "activeForm": "Confirming modifications make sense"}, {"content": "Find exact histo…`
- **Read** `/workspaces/fhir-agent/docs/phase2/plan.md`
- **Bash** `grep -n "^### D\|^## D\|^### E\|D8" /workspaces/fhir-agent/docs/phase2/decisions.md | head -40`

</details>

---

## Archive metadata

- **Source:** Claude Code
- **Session ID:** `703d1575-6579-4a4a-834d-bfd055f35840`
- **Created:** 2 August 2026, 03:48 UTC
- **Last updated:** 2 August 2026, 04:24 UTC
- **Turns:** 7
- **Status:** Incomplete
