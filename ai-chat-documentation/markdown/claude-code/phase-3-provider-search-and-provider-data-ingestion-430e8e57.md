# Phase 3 - provider search and provider data ingestion

## Turn 1

### Prompt

You are my senior staff engineer / architect pair. We are extending an existing healthcare data platform with a new capability. Work in brainstorming mode first, then produce a draft PRD and a design proposal. Ask me clarifying questions before finalizing anything you're unsure about — do not silently assume.

## Context: the existing platform (what's already built)

Existing repo (github.com/bhaskarcmu/fhir-agent): a FHIR-based healthcare data platform. Prior phases established:
- A FHIR interoperability/audit layer (HAPI FHIR JPA), synthetic patient data (Synthea), Postgres/Neon backing store.
- A polyglot services layer: Spring Boot (Java) for domain/façade services, Python/FastAPI for agents and clinical-decision/triage services.
- A Kong API gateway fronting edge routes; internal/legacy services never exposed on the edge.
- Patterns already in use: API Façade, Anti-Corruption Layer (ACL), Strangler-Fig, contract-first APIs, 12-factor services, PHI-safe-by-default, observability/SLOs, ADRs.
- GKE for orchestration.
- Note: the platform has previously used lightweight, in-process "agent tool" wiring. This phase is my FIRST real Model Context Protocol (MCP) server — build it fresh as a genuine MCP server; do not assume an existing MCP server to extend.

## Goal of this phase (Phase 3): Provider Search

Build a Provider Search capability that finds real-world healthcare providers matching a clinical need. Given (a) a patient location (or arbitrary geographic point), (b) a required specialty, and optionally (c) filters like accepting-new-patients and distance radius, return a ranked list of appropriate providers with the data needed to act on a referral.

**Critical constraint:** Build on AUTHENTIC, PUBLICLY AVAILABLE provider data — NOT a paid third-party aggregator API. We own ingestion, normalization, matching, and ranking ourselves. Part of the value is demonstrating that a first-party provider-search service can replace a black-box commercial API.

## Two agents to design (first-class)

Introduce TWO agents plus the deterministic services they orchestrate. Propose the cleanest split; my initial thinking:

1. **Provider Search / Referral agent** — takes a natural-language or structured clinical request ("find an endocrinologist within 15 miles of this ZIP who is accepting new patients"), decomposes it, calls deterministic tools (specialty resolution, location lookup, ranking) over MCP, and returns an explained, ranked result set with rationale. The agent orchestrates; it must NEVER invent provider facts — every returned provider must trace to a real ingested record.

2. **Provider Data Ingestion / Curation agent** — an agent (or agentic pipeline) that ingests, normalizes, deduplicates, and reconciles provider records from multiple authoritative public sources into a canonical registry. AI helps with: fuzzy entity resolution across sources, specialty-taxonomy normalization, flagging stale/conflicting records, summarizing change events. Deterministic where it must be: identity keys, the golden-record merge rules, any coordinate assignment.

For each agent specify: purpose, tools/functions it can call (all human-defined and traceable), inputs/outputs, guardrails (what it must never do), and how it stays grounded in real data.

## Underlying services (deterministic core)

Propose the services. Starting hypotheses (challenge/refine):

- **Provider Registry service** — canonical store + golden records. Explore a diversified/polyglot persistence approach: relational (Postgres) for the authoritative golden record and lineage; a NoSQL/document or search-optimized store for high-cardinality, key-based directory reads (i.e., fetching individual provider records by unique identifier at volume); evaluate whether a graph store (Neo4j) is justified for provider↔organization↔location↔network relationships. Give trade-offs AND a recommendation.

- **Specialty / Taxonomy service** — resolve and normalize specialties using the real NUCC Health Care Provider Taxonomy code set (the standard used with NPI). Map free-text clinical need → taxonomy codes.

- **Location / Geospatial Search service — KEEP THIS DELIBERATELY SIMPLE FOR NOW.** Do NOT design PostGIS, Elasticsearch geo, or geohashing infrastructure yet. Instead:
  - Pre-load a largish lookup dataset: real provider records (from NPPES) whose practice addresses have pre-computed lat/long stored as plain columns, plus a ZIP-centroid reference table (public ZIP→lat/long) so we can resolve an input ZIP to a coordinate.
  - Implement proximity as a straightforward stub: compute great-circle (haversine) distance in application code (or a simple SQL expression) between the input coordinate and candidate providers, filter by radius, sort ascending, return nearest-N. A naive full-or-filtered scan over the pre-loaded table is FINE at this stage — correctness and a clean interface matter more than performance.
  - Design it behind a clean, swappable interface (a LocationSearch port with a well-defined contract) so a production-grade geospatial engine can replace the stub later WITHOUT changing callers. Call out explicitly that this is a stub and note what the future real implementation would be.

- **Ingestion / ETL pipeline** — how we load and refresh the registry (and the pre-computed coordinates). Batch/scheduled is fine now; note where incremental/CDC would fit later.

## Non-functional / learning requirement: a REAL MCP server (must-have, zero-cost)

For learning purposes, this phase MUST use an actual, hand-built Model Context Protocol (MCP) server — not a simulated or in-process stand-in. This is my first MCP server. Constraints and intent:

- **Real protocol, hand-built, free.** Implement a genuine MCP server using the open-source MCP SDK (Python or TypeScript). It must implement the real MCP handshake and lifecycle (initialize, tools/list, tools/call) so it could be registered with any compliant MCP client (Claude Desktop, an IDE, or our own client). No paid services, no hosted/managed MCP product — a simple locally-runnable server (stdio transport is fine; HTTP/SSE optional) is exactly what I want.

- **What the MCP server exposes:** the deterministic Phase 3 tools as MCP tools, each with a clear input/output schema and description — at minimum:
  - `resolve_specialty` (free-text clinical need → NUCC taxonomy code[s])
  - `search_providers_near` (coordinate/ZIP + specialty + filters → ranked nearest-N provider records from the registry, using the simple haversine stub)
  - `get_provider` (fetch a full provider record by NPI, with lineage)
  Optionally expose provider reference data as MCP *resources*.

- **How the agent uses it:** the Provider Search / Referral agent must act as a real MCP *client/host* — connect to the MCP server, discover tools via tools/list, and invoke them via tools/call. It must NOT call the underlying services through in-process function calls that bypass the protocol; the MCP boundary is the point of the exercise. Show the transport and the tool-discovery/invocation flow in the design.

- **Boundaries & guardrails:** the MCP server is internal-only (never on the Kong edge), returns only traceable, real ingested records, and enforces PHI-safe-by-default. Keep it simple enough to run locally and hand-build; call out clearly which piece is the MCP server, which is the MCP client/host, and where the protocol boundary sits.

Reflect this in both the PRD (as an explicit NFR) and the design proposal (show the MCP server component, its tool contracts, the transport, and the client/host wiring in the architecture diagram).

## Authoritative public data sources — research and propose the best set

Identify and evaluate REAL, publicly available, authoritative U.S. provider data sources; recommend which to use and how to combine. At minimum consider:
- **NPPES / NPI Registry** (CMS) — foundational public provider dataset (NPI, name, taxonomy, practice address); has a bulk downloadable file and an API.
- **NUCC Health Care Provider Taxonomy** — specialty normalization.
- **A public ZIP-code → lat/long dataset** and/or the **US Census Geocoder** — to get coordinates for input locations and to pre-compute provider coordinates for the stub.
- Any other authoritative public sources you know of (CMS provider files, state licensing boards).
For each: what it provides, format/access (bulk vs API), update cadence, key fields, gotchas, and fit to the golden-record model. Be accurate about what these actually contain; if unsure about current availability/schema, say so and mark it "to verify."

## What to produce

In this order:

1. **Clarifying questions** — ask anything material before designing (scale targets, latency expectations, freshness/batch cadence, whether commercial/plan-specific network data is in scope or just public data, dataset size for the stub, MCP SDK language preference, etc.).

2. **Draft PRD** — problem statement, goals & non-goals, users & use cases, functional requirements, non-functional requirements (scale, latency, freshness, availability, PHI/PII handling, compliance posture, AND the real-MCP-server learning requirement), success metrics/KPIs, explicit out-of-scope (note that eligibility determination is a FUTURE phase, not this one).

3. **Design proposal** — target architecture with a text/ASCII component diagram; the two agents and their tool contracts; the deterministic services; the data model and persistence choices (polyglot trade-off analysis + clear recommendation); the ingestion pipeline; the specialty-matching + simple-proximity + ranking approach; the swappable LocationSearch stub interface (with a note on the future real engine); the hand-built MCP server (component, tool contracts, transport, client/host wiring); how it plugs into the existing Kong/FHIR/GKE platform; how existing patterns (Façade, ACL, Strangler-Fig, contract-first) apply; key API contracts (sketch main endpoints/schemas); agent guardrails/grounding; observability/SLOs; security/compliance; and a phased build/rollout sequence with risks and open questions.

## Ground rules
- Contract-first and PHI-safe-by-default, consistent with the existing platform.
- Agents orchestrate deterministic, human-authored tools over a real MCP boundary; agents must NEVER fabricate provider facts — every provider in a result must trace to a real ingested record with lineage.
- Prefer authentic public data for the provider registry (synthetic patients are fine on the "requesting" side).
- Geospatial: simple haversine-over-preloaded-data stub now, clean swappable interface for later. Don't over-engineer it.
- MCP: real, hand-built, free, locally-runnable; the agent connects as a genuine MCP client. Don't bypass the protocol.
- Be opinionated: where there's a choice, recommend and justify. Flag uncertainties rather than guessing.

Start by asking me your clarifying questions.

### Claude response

I'll ground my clarifying questions in the actual repo state first — checking prior phase context and the existing MCP-agent/gateway structure — then ask you before drafting anything.

I've grounded myself in the current repo state before drafting questions. Key facts that shape the questions below:

- **mcp-agent/ is confirmed NOT a real MCP server today** — it's an in-process Anthropic tool-use loop (`agent.py`/`tools.py`), matching your premise. Interestingly, `fhir-service` (Java) already has a *dormant* real MCP server (Spring AI MCP, `enabled-by-default: false`) — unrelated to mcp-agent and not something Phase 2 touched. I'll treat it as irrelevant to Phase 3 unless you say otherwise.
- **triage-service is called over HTTP** from mcp-agent, not in-process — so "the MCP boundary must not be bypassed" has a clean precedent to follow.
- **client/clinical/ has no Organization/Location/Practitioner models yet** — Provider Search will add the first ones, following its existing `get_<resource>()` + dataclass + `_parse_<resource>()` pattern.
- **Phase 2 set real precedents** worth either following or deliberately deviating from: a *separate* `claims-agent` package (not an extension of `mcp-agent`), curated data slices instead of full bulk files (2.4GB CMS PUF → curated only), Postgres-behind-a-repository-interface with NoSQL/Bigtable as a documented future scale-swap (not built now), Cloud Run for new Phase 2 services vs. GKE for untouched Phase 1, and `docs/phase2/{README,requirements,plan,decisions,source-prd}.md` as the doc-set template with a `D#/C#` decisions log (no formal `ADR-NNNN` folder exists).
- **gateway/ already has a clean "internal-only, never on the edge" precedent** (`rxclaim-emulator`) that the MCP server can follow directly.

Now, my clarifying questions — the four below are the ones that most change the shape of the design, so I'd like your call on each before drafting.

A few more that shape scope boundaries and the ingestion/infra design:

Both drafts are up:

- **[PRD](https://claude.ai/code/artifact/aaa566f9-7741-4488-96ba-869dad82bdb0)** — problem, goals/non-goals, functional + non-functional requirements, success metrics, explicit out-of-scope.
- **[Design proposal](https://claude.ai/code/artifact/8f08156a-6dad-4d09-aec0-391d32483d2b)** — architecture diagram, both agents' full tool contracts and guardrails, the Provider Registry Service + `LocationSearchPort` stub, the hand-built MCP server (real code sketch for both server and client/host sides), data sources with honest gotchas, and a phased rollout.

Grounded the design in what's actually in the repo rather than assuming: two new standalone agent packages (matches Phase 2's `claims-agent` precedent), Postgres-only with a swappable port (matches Phase 2's C3 decision), internal-only on Cloud Run with no Kong route (matches `rxclaim-emulator`), and MCP scoped only to the three query-side tools — ingestion deliberately stays outside the MCP boundary since it has no client that needs tool discovery.

Two things came up during research that are worth flagging directly:

1. **NPPES has no `accepting_new_patients` field.** I did not find a verified source for it and marked this "to verify" rather than guessing — the schema keeps it nullable/`unknown` until we confirm a real source (e.g. CMS Care Compare) actually covers it.
2. **`fhir-service` already has a dormant, unrelated Java MCP server** (Spring AI, `enabled-by-default: false`). I treated it as irrelevant to this Python-based Phase 3 build — flag if you want it reused or removed instead.

Both docs end with a short **open-questions list** (§9 in the PRD, §15 in the design doc) — things like which 2–3 states to curate, whether the search agent needs an HTTP entrypoint, and Phase 2's actual east-west auth pattern to match. Nothing is committed to the repo yet — these are drafts for your review; once you're good with the direction I'll branch, write them to `docs/phase3/`, and open a PR, matching the Phase 2 pattern.

## Turn 2

### Prompt

Answer the open questions yourself using best judgement. Then commit these documents locally without creating a PR yet. I want to review them here in this environment. Also for terminology do not use the word "Phase" for any parts of Phase 3. There can be milestones within Phase 3 9create a plan containing these). Phase 3b will be GCP cloud deployment, just as we did with phase 2, each milestone will prepare suitably with stubs for Phase 3b. MAke all this ready locally commmitted for my review please

### Claude response

Let me verify one factual item (Phase 2's actual internal service-to-service auth pattern) before finalizing, rather than guess.

Verified: Phase 2 has **no application-layer auth on internal service-to-service calls** — trust is network-isolation only (`ingress=internal` + IAM invoker + VPC connector), confirmed in `HttpTriageClient.java:50-55`, `HttpLegacyClient.java:23-29`, `HapiFhirClient.java:24-31`, and `docs/phase2/plan.md:36-40,167-170`. I'll apply that same pattern rather than inventing new auth.

Now updating both docs: resolving the open questions with rationale, and reworking the milestone plan to drop "Phase" labels internally while introducing **Milestone 3b** terminology... 

Correction — updating the milestone plan so the GCP deployment step is called **Milestone 3b** per your naming.

Now updating the non-goals, KPIs, and resolving the open questions section:

Now the "Out of scope" and open-questions sections:

Now replacing the open-questions section with resolved decisions:

PRD is updated. Now the design doc — reworking the milestone plan and resolving its open questions.

<details>
<summary>Execution details — 30 tool events</summary>

### Turn 1 activity

- **Read** `/home/vscode/.claude/projects/-workspaces-fhir-agent/memory/phase2-planning-state.md`
- **Agent** `Survey repo structure for Phase 3 design`
- **AskUserQuestion** `{"questions": [{"question": "Which language should the hand-built MCP server (and the agent's MCP client/host side) use?", "header": "MCP language", "multiSelect": false, "options": [{"label": "Python…`
- **AskUserQuestion** `{"questions": [{"question": "Where should the new Phase 3 services (registry, taxonomy, location-search, MCP server, both agents) deploy?", "header": "Deploy target", "multiSelect": false, "options":…`
- **Skill** `{"skill": "artifact-design"}`
- **Bash** `mkdir -p /tmp/claude-1000/-workspaces-fhir-agent/430e8e57-d6b5-46cb-89d1-1b01e1ad7fcb/scratchpad/phase3`
- **Write** `/tmp/claude-1000/-workspaces-fhir-agent/430e8e57-d6b5-46cb-89d1-1b01e1ad7fcb/scratchpad/phase3/prd.md`
- **ToolSearch** `TodoWrite`
- **TodoWrite** `{"todos": [{"content": "Draft PRD (prd.md)", "status": "completed", "activeForm": "Drafting PRD"}, {"content": "Draft design proposal (design.md)", "status": "in_progress", "activeForm": "Drafting des…`
- **Write** `/tmp/claude-1000/-workspaces-fhir-agent/430e8e57-d6b5-46cb-89d1-1b01e1ad7fcb/scratchpad/phase3/design.md`
- **TodoWrite** `{"todos": [{"content": "Draft PRD (prd.md)", "status": "completed", "activeForm": "Drafting PRD"}, {"content": "Draft design proposal (design.md)", "status": "completed", "activeForm": "Drafting desig…`
- **Artifact** `/tmp/claude-1000/-workspaces-fhir-agent/430e8e57-d6b5-46cb-89d1-1b01e1ad7fcb/scratchpad/phase3/prd.md`
- **Artifact** `/tmp/claude-1000/-workspaces-fhir-agent/430e8e57-d6b5-46cb-89d1-1b01e1ad7fcb/scratchpad/phase3/design.md`
- **TodoWrite** `{"todos": [{"content": "Draft PRD (prd.md)", "status": "completed", "activeForm": "Drafting PRD"}, {"content": "Draft design proposal (design.md)", "status": "completed", "activeForm": "Drafting desig…`

### Turn 2 activity

- **Bash** `grep -rniE "internal.*auth|service.*token|x-internal|shared.*secret|api.?key" claims-service/ rxclaim-emulator/ docs/phase2/ 2>/dev/null | grep -viE "kong|key-auth.yaml|apikey header" | head -50`
- **Bash** `grep -rniE "httpx|RestTemplate|WebClient|okhttp" claims-service/src/main/java --include=*.java -l 2>/dev/null | xargs -I{} sh -c 'echo ==={}===; grep -niE "header|auth|token" {}' 2>/dev/null | head -6…`
- **Agent** `Verify Phase 2 internal service auth`
- **Read** `/tmp/claude-1000/-workspaces-fhir-agent/430e8e57-d6b5-46cb-89d1-1b01e1ad7fcb/scratchpad/phase3/prd.md`
- **Edit** `/tmp/claude-1000/-workspaces-fhir-agent/430e8e57-d6b5-46cb-89d1-1b01e1ad7fcb/scratchpad/phase3/prd.md`
- **Edit** `/tmp/claude-1000/-workspaces-fhir-agent/430e8e57-d6b5-46cb-89d1-1b01e1ad7fcb/scratchpad/phase3/prd.md`
- **Edit** `/tmp/claude-1000/-workspaces-fhir-agent/430e8e57-d6b5-46cb-89d1-1b01e1ad7fcb/scratchpad/phase3/prd.md`
- **TodoWrite** `{"todos": [{"content": "Resolve open questions with best judgment in prd.md", "status": "in_progress", "activeForm": "Resolving open questions in prd.md"}, {"content": "Resolve open questions + rework…`
- **Edit** `/tmp/claude-1000/-workspaces-fhir-agent/430e8e57-d6b5-46cb-89d1-1b01e1ad7fcb/scratchpad/phase3/prd.md`
- **Edit** `/tmp/claude-1000/-workspaces-fhir-agent/430e8e57-d6b5-46cb-89d1-1b01e1ad7fcb/scratchpad/phase3/prd.md`
- **Edit** `/tmp/claude-1000/-workspaces-fhir-agent/430e8e57-d6b5-46cb-89d1-1b01e1ad7fcb/scratchpad/phase3/prd.md`
- **Edit** `/tmp/claude-1000/-workspaces-fhir-agent/430e8e57-d6b5-46cb-89d1-1b01e1ad7fcb/scratchpad/phase3/prd.md`
- **Edit** `/tmp/claude-1000/-workspaces-fhir-agent/430e8e57-d6b5-46cb-89d1-1b01e1ad7fcb/scratchpad/phase3/prd.md`
- **Edit** `/tmp/claude-1000/-workspaces-fhir-agent/430e8e57-d6b5-46cb-89d1-1b01e1ad7fcb/scratchpad/phase3/design.md`
- **Edit** `/tmp/claude-1000/-workspaces-fhir-agent/430e8e57-d6b5-46cb-89d1-1b01e1ad7fcb/scratchpad/phase3/design.md`
- **TodoWrite** `{"todos": [{"content": "Resolve open questions with best judgment in prd.md", "status": "completed", "activeForm": "Resolving open questions in prd.md"}, {"content": "Resolve open questions + rework m…`

</details>

---

## Archive metadata

- **Source:** Claude Code
- **Session ID:** `430e8e57-d6b5-46cb-89d1-1b01e1ad7fcb`
- **Created:** 17 July 2026, 13:05 UTC
- **Last updated:** 17 July 2026, 13:41 UTC
- **Turns:** 2
- **Status:** Complete
