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

*[Claude has not completed this turn yet.]*

<details>
<summary>Execution details — 12 tool events</summary>

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

</details>

---

## Archive metadata

- **Source:** Claude Code
- **Session ID:** `703d1575-6579-4a4a-834d-bfd055f35840`
- **Created:** 2 August 2026, 03:48 UTC
- **Last updated:** 2 August 2026, 04:02 UTC
- **Turns:** 4
- **Status:** Incomplete
