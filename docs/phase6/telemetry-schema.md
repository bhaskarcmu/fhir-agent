# Telemetry Schema — Span Attribute Dictionary

> What every custom span attribute in this platform means, which module populates it, and how
> deep the instrumentation goes. This is the semantic-conventions registry for **this repo's own
> custom telemetry** — the equivalent of what OpenTelemetry itself publishes for its reserved
> namespaces (`http.*`, `db.*`, `gen_ai.*`), scoped to the attributes this platform adds on top.
>
> **Not a requirements-traceability matrix.** In regulated/medical-device software, "traceability"
> names a static, design-time artifact (requirement → design → code → test). This document is the
> opposite: a *runtime* schema for *dynamic* distributed tracing (OpenTelemetry spans). The two
> concepts share a root word and a rough goal (know what produced what, and prove it) but are
> built, maintained, and consumed completely differently — this repo doesn't currently have the
> former, and this document is deliberately not named or structured to be mistaken for one.
>
> Cross-referenced from [`design.md` §4.2](./design.md#42-observability--m2) and
> [`decisions.md` H24–H27](./decisions.md).

## 1. The two namespaces, and why there are two

| Namespace | Standard? | Answers | Populated by |
|---|---|---|---|
| `code.*` | ✅ OpenTelemetry semantic convention (`code.function.name`, `code.file.path`, `code.line.number`) | "What literal function/file produced this span?" | Wherever a span is created, mechanically |
| `fhir_agent.*` | Custom to this repo (namespaced to avoid colliding with any real OTel semconv) | "What *architectural role* did this code play?" | Deliberately, at each layer's boundary |

OTel's `code.*` convention identifies source location; it has no concept of "which architectural
layer" or "which business capability" a span belongs to — that's a business/design concern, and
every mature observability practice that wants it defines its own namespace for it (OTel's own
spec explicitly reserves unprefixed/vendor namespaces for exactly this). `fhir_agent.*` is that
namespace here. Using the real standard where one exists, and inventing the minimum necessary
where it doesn't, is the design principle for this whole document.

## 2. `fhir_agent.*` attributes

| Attribute | Type | Meaning |
|---|---|---|
| `fhir_agent.layer` | string enum (per tier, §3) | The architectural layer that produced this span — e.g. `claims.pipeline`, `agent.orchestration`. Coarse-grained; one of a small fixed set per tier. |
| `fhir_agent.component` | string | The specific class/module within that layer — e.g. `RulesEngine`, `LegacyAdapter`, `assess_refill_risk`. Fine-grained; free text but conventionally the actual class/function name, so it's greppable back to source. |
| `fhir_agent.verbosity` | string enum: `standard` \| `detailed` | Which verbosity level was active when this span was created (§4). Lets a trace be filtered/understood without needing to know the exporting process's config out-of-band. |

Both `fhir_agent.layer` and `fhir_agent.component` are added to spans OpenTelemetry (or its
auto-instrumentation) already creates — they enrich, they don't multiply span count on their own.
New spans are a `verbosity=detailed`-only concern (§4).

### 2.1 M6 additions: `judge.*` and `knowledge.*`

Two more small, purpose-specific namespaces (not folded into `fhir_agent.*`, since they're
result data for one specific feature each, not general architectural metadata):

| Attribute | Type | Meaning |
|---|---|---|
| `judge.available` | bool | Whether `judge_response()` produced a real result this call, or failed closed to inconclusive (decisions.md H53). |
| `judge.groundedness_ok` / `.tone_ok` / `.phi_leak_detected` | bool | The judge's own verdict fields — present only when `judge.available=true`. Never drives any decision logic; observability only (H54). |
| `knowledge.found` | bool | Whether `_fetch_citations()` found any real citation data for the flagged medication(s). |
| `knowledge.source` | string | Which knowledge APIs contributed (currently always `"openFDA + RxClass"` when `knowledge.found=true`). |

## 3. Layer taxonomy, by tier — grounded in the actual package/module structure

Not invented generically — each layer below is a real, already-existing code boundary (Java
package or Python module), found by reading the tree, not guessed.

### 3.1 Agent tier (`mcp-agent`, `agent-platform`)

| `fhir_agent.layer` | Real code boundary | Role |
|---|---|---|
| `agent.orchestration` | `mcp-agent/src/agent/agent.py` | The tool-use loop itself: `run_query`, decision validation, turn management. No clinical logic — orchestrates only (CLAUDE.md's own framing). |
| `agent.tools` | `mcp-agent/src/agent/tools.py` | FHIR/triage integration: `get_patient_summary`, `assess_refill_risk`. |
| `agent.presentation` | `mcp-agent/src/agent/format.py` | Terminal output formatting — not usually spanned (no I/O of interest), listed for completeness. |
| `agent.judge` | `agent_platform/judge.py` | M6's LLM-as-judge (`judge_response`) — advisory-only, structurally incapable of overriding a decision (decisions.md H54). |
| `agent.knowledge` | `agent_platform/knowledge.py`, `mcp-agent/src/agent/agent.py`'s `_fetch_citations` | M6's post-decision citation lookup (openFDA + RxClass, decisions.md H15) — fires only after a decision is already final. |
| `platform.output_gate` | `agent_platform/output_gate.py` | The fail-closed enum contract (M1). |
| `platform.fail_closed` | `agent_platform/fail_closed.py` | The risk-code sentinel guard (M1). |

### 3.2 Deterministic clinical tier (`triage-service`)

| `fhir_agent.layer` | Real code boundary | Role |
|---|---|---|
| `triage.api` | `triage-service/src/triage/main.py` | FastAPI route handlers — request/response shape. |
| `triage.rules` | `triage-service/src/triage/rules.py` | The actual drug-allergy conflict rule engine (`evaluate()`, priority-ordered `Rule` list). The single highest-value place to go deeper than "one span per request" — see §4.2. |

### 3.3 Claims tier (`claims-service`) — Phase 2-owned code, see [`../phase2/plan.md`](../phase2/plan.md)

Six real packages, each already a clean architectural boundary:

| `fhir_agent.layer` | Java package | Role |
|---|---|---|
| `claims.api` | `com.payer.claims.api` | Edge intake: `ClaimController`, `ClaimValidationAdvice` (the malformed-vs-denial distinction, R17.6). |
| `claims.pipeline` | `com.payer.claims.pipeline` | Orchestration: `AdjudicationPipeline` (runs rules → triage → legacy, in order) and `AdjudicationService` (idempotency + persistence wrapper, R18). |
| `claims.rules` | `com.payer.claims.rules` | `RulesEngine` — the modern layered rules engine and the Decision Contract precedence (R17). |
| `claims.acl` | `com.payer.claims.acl` | `LegacyAdapter` — the anti-corruption layer; the one place that knows the legacy fixed-width wire format. |
| `claims.fhir` | `com.payer.claims.fhir` | `HapiFhirClient`, `FhirArtifactBuilder` — persists the decision artefact graph. |
| `claims.kb` | `com.payer.claims.kb` | `FilePayerKb` — the payer knowledge base repository (C3 seam). |

`com.payer.claims.client` (the two outbound HTTP clients) doesn't get its own `fhir_agent.layer` —
it's transport, already identified by the span it wraps (`HttpTriageClient`'s span is already
named for the HTTP call it makes); tagging it again would be redundant.

**At `standard` verbosity, only `claims.api` is actually applied.** There is exactly one span
per request (the auto-instrumented Spring MVC server span) — tagging it from `pipeline`, then
`rules`, then `acl` in sequence would just have each overwrite the last, leaving a misleading
single tag that reflects whichever layer happened to run last, not a meaningful signal. The rest
of this table is the vocabulary reserved for if/when `claims-service` gets its own `detailed`
sub-span tier (real per-layer spans, not repeated tags on one span) — not built in this pass,
same as claims-service's pipeline/rules/acl stages generally (§4.2 names `triage.rules` as the
one boundary judged worth it right now).

### 3.4 Legacy emulation tier (`rxclaim-emulator`) — Phase 2-owned code

| `fhir_agent.layer` | Java package | Role |
|---|---|---|
| `rxclaim.api` | `com.payer.rxclaim.api` | `AdjudicationController` — the one endpoint claims-service's ACL calls. |
| `rxclaim.core` | `com.payer.rxclaim.core` | `RxClaimCore` — the emulated legacy adjudication logic itself. |
| `rxclaim.legacy` | `com.payer.rxclaim.legacy` | `LegacyClaimRecord`/`LegacyResponseRecord` — fixed-width wire parsing. |

### 3.5 FHIR persistence tier (`fhir-service`)

No custom `fhir_agent.layer` values — `fhir-service` is the stock HAPI FHIR JPA starter with no
custom business-logic packages of its own (confirmed: no `com.healthcare.*` package exists beyond
starter configuration). `service.name=fhir-service` on its spans is sufficient; inventing a layer
taxonomy for a service with no internal architecture to describe would be exactly the kind of
over-instrumentation §4 argues against.

## 4. Verbosity — configurable depth, not maximum depth by default

Two levels, one environment variable: **`TELEMETRY_VERBOSITY`** (`standard` default, or
`detailed`). Deliberately not prefixed `OTEL_*` — that prefix is reserved for the real
OpenTelemetry SDK's own environment variables (`OTEL_EXPORTER_OTLP_ENDPOINT`, etc.); this is a
repo-specific setting, not a spec-defined one.

### 4.1 `standard` (default)

Every span M2 already creates, now additionally carrying `fhir_agent.layer` / `.component` /
`.verbosity`. **No new spans.** This is the right default: SRE guidance (Google's SRE book, most
OTel adoption guides) is consistently to instrument at architecturally meaningful boundaries, not
every function — over-instrumenting adds real overhead and makes traces harder to read, not
easier. Enriching existing spans costs nothing extra in span volume.

### 4.2 `detailed` (opt-in)

Adds sub-spans at the **single highest-value boundary this platform has**: one span per rule
evaluated in `triage-service/rules.py`'s `evaluate()` loop (`penicillin-conflict`,
`duplicate-therapeutic-class`, `high-criticality-allergy`, in priority order) — this is the actual
clinical decision logic, the one place where "which specific rule fired, and what did the ones
before it decide" is worth the extra span volume. Deliberately **not** instrumented to this depth
everywhere: claims-service's pipeline stages, the ACL translation, and the rest stay at `standard`
level unless a specific debugging need justifies extending `detailed` there too — that's an
explicit future decision, not a default assumption (see `decisions.md` H27).

## 5. Request/trace-ID surfacing

The TraceID OTel already generates is exposed to whoever's on the other end of a request,
consistent with the long-standing `X-Request-Id`/`X-Correlation-Id` pattern (which predates OTel
and is kept here specifically because a trace ID buried in span context is useless to a human or
test program that isn't already looking at Jaeger):

- **`mcp-agent`**: the trace ID appears in both `decision_block()`'s output and `error_block()`'s
  output — visible in every CLI response, success or failure.
- **`triage-service`**: every HTTP response (success or error) carries an `X-Trace-Id` header.
- **`claims-service`**: same — every HTTP response carries an `X-Trace-Id` header.

## 6. Exceptions — already correlated, verified not assumed

OpenTelemetry's Python SDK defaults `record_exception=True, set_status_on_exception=True` on
`start_as_current_span()` — confirmed directly against the installed package
(`inspect.signature(Tracer.start_as_current_span)`), not assumed from documentation. Any exception
raised inside a span this platform creates is automatically attached to that span, carrying
whatever `fhir_agent.layer`/`.component` attributes are already on it — no extra code needed on
the Python side. The Java side's equivalent (Micrometer's OTel bridge) is expected to behave the
same way (Micrometer Observation API also records exceptions by default) but has not been
independently verified against the installed version the way the Python claim was — flagged as an
open verification item, not asserted as fact.

## 7. Resource usage — RED and USE, and what M4 built

Two established SRE vocabularies, used here so nothing bespoke gets invented:

- **RED** (Rate, Errors, Duration) — request-level; already substantially covered by the trace/span
  data this document describes, plus each service's HTTP-layer metrics.
- **USE** (Utilization, Saturation, Errors) — resource-level (CPU, memory, connection pools).
  Largely **already available for free**: Spring Boot Actuator + Micrometer auto-registers JVM
  memory/GC/thread/CPU metrics the moment `micrometer-registry-prometheus` is on the classpath
  (true for all three Java services since M2) — worth confirming what's already on
  `/actuator/prometheus` before building anything new here.

**LLM token/cost usage was the one resource genuinely worth new work, and M4 built it**
(docs/phase6/decisions.md H39). M2 already puts `gen_ai.usage.input_tokens`/`output_tokens` on
each chat span (per-request visibility), but a span attribute can't answer "how many tokens
today" or feed a cost alert — that needed an actual Prometheus counter/histogram, deliberately
deferred until M4's rate/cost limiter existed as its consumer (building the metric before it had
one would have been premature). `agent_platform.resilience` now exposes four series at
`mcp-agent-api`'s `/metrics`, scraped by Prometheus the same way the Java services'
`/actuator/prometheus` already is:

- `fhir_agent_llm_tokens_total{direction="input"|"output"}` — cumulative token counter.
- `fhir_agent_llm_calls_total{outcome="success"|"failure"|"circuit_open"|"cost_blocked"}` — a
  nonzero `circuit_open`/`cost_blocked` rate means M4's fail-closed protections are actively
  shedding load, not that the agent is silently broken.
- `fhir_agent_llm_call_duration_seconds` — histogram, successful calls only.
- `fhir_agent_rate_limit_alerts_total` — the hybrid posture's alert-only signal (H19): rising
  without a corresponding `cost_blocked` rise means unusual-but-not-runaway volume.

A provisioned Grafana dashboard (`observability/grafana/provisioning/dashboards/llm-cost-rate.json`)
visualizes all four. See `milestone-plan.md` M4 for the live validation that confirmed this against
a real (intentionally broken, then restored) Anthropic API key.
