# Phase 2 - prescription claim adjudication prototype

## Turn 1

### Prompt

This whole system has to be capable of running locally for development, and be very easily switchable to being deployed in the cloud. The Kong gateway has to be carefully placed in the architecture. Note where it already is, and where it needs to be. There can me multiple APIs as part of the architecture in different places, but there has to be a clear diagram and thought process where they are. Elaborate on your thoughts regarding these matters

### Claude response

Let me look at how Kong is actually wired today before reasoning about where it should go — the gateway config, compose, deploy script, and k8s manifests.

Critical finding: **Kong is not in docker-compose at all** — locally everything talks directly to the FHIR container; Kong exists only as k8s/Helm config for cloud. Let me read the gateway config and k8s manifests to see exactly what it fronts.

Now I have the full picture. Let me confirm the cloud deploy pattern and k8s layout quickly.

I now have the complete picture. Here's my elaboration on local/cloud parity, Kong placement, and the multi-API topology.

## 1. Where Kong actually is today

Two facts that dominate the design:

- **Kong is cloud-only.** It's not in [docker-compose.yml](docker-compose.yml) at all. It exists only as Helm values + Kubernetes CRDs ([gateway/kong/](gateway/kong/)) deployed to GKE by [deploy.sh](deploy.sh). Locally, nothing goes through a gateway.
- **Kong fronts exactly one thing: `fhir-service`.** [kong-ingress.yaml](gateway/kong/kong-ingress.yaml) routes `/fhir` → `fhir-service:8080` (a **ClusterIP** — [service.yaml](fhir-service/k8s/service.yaml) — so it is *unreachable* except through Kong). Plugins: `key-auth` + `rate-limit` per-Ingress; `file-log` + `prometheus` as **global** `KongClusterPlugin`s.

The parity mechanism today is a single env var: **`FHIR_GATEWAY_URL`**, defaulting to `http://fhir:8080/fhir` (direct, local) and overridable to the Kong proxy for the "gated setup." `triage` and `mcp-agent` are the only consumers, and they call FHIR directly locally.

Two things the current design got right and that Phase 2 should exploit:
- The global cluster plugins mean **any new service placed behind Kong is auto-logged and auto-metered** — the gateway README explicitly anticipates this.
- fhir-service being ClusterIP-only is the real enforcement: the gateway isn't bypassable in cloud because the backend has no public address.

## 2. The core mental model: two API planes

The single most important placement decision is recognizing that Phase 2 has **two distinct API planes**, and Kong belongs on exactly one of them.

- **North–south (edge plane):** external clients → the platform. This is where auth, rate-limit, quota, and request logging must live. **Kong owns this plane.**
- **East–west (internal plane):** service → service, inside the trust boundary. This is where the **API façade + anti-corruption** story lives. The legacy emulator sits *here*, and must **never** appear on the edge plane.

The whole "wrap the legacy core, consumers never call it directly" narrative from the PRD is, concretely, *"the legacy emulator has no Kong route and no public Service."* That's what makes the façade real rather than rhetorical.

## 3. Where Kong needs to go in Phase 2

**Kong stays a single gateway; it gains routes — it does not multiply.**

| API | Plane | Kong route? | Reachability |
|---|---|---|---|
| `claims-service` (new, Spring Boot) | Edge — the new front door | **Yes** — new `/claims` route | Public via Kong only |
| `fhir-service` (existing) | Edge (data) | Yes — existing `/fhir` route | ClusterIP, Kong only |
| `triage-service` (existing) | Internal (called by claims + agent) | **Recommend yes** (uniform policy) | ClusterIP |
| `legacy-rxclaim-emulator` (new) | **Internal, private** | **Never** | ClusterIP + NetworkPolicy: only `claims-service` may call it |
| `mcp-agent` | Client (CLI, not a server) | n/a (it's a consumer) | — |

The decision I'd flag for you: **should internal FHIR calls (`claims-service → fhir-service`) traverse Kong, or go direct?** My recommendation: **through Kong in the cloud**, so *every* read/write of clinical data is authenticated, rate-limited, and logged at one chokepoint — that's a strong "audit trail for every decision" compliance story for the target role, and it costs only a `claims-service` Kong consumer/key. Locally it toggles to direct via the same env var. The **one exception is the legacy emulator** — those calls are always direct claims→legacy, because gating your own private legacy core at the edge gateway is nonsensical.

Anti-patterns this explicitly rules out:
- ❌ mcp-agent calling triage or the legacy emulator directly (it must go through the claims-service façade — and CLAUDE.md already forbids clinical logic in the agent).
- ❌ A Kong route to the legacy emulator.
- ❌ Multiple Kong instances / a second internal gateway. For a prototype that's over-engineering; one gateway with clear route boundaries + NetworkPolicies is the right weight. (A service mesh is the "if this were real at scale" answer — worth *saying* in an interview, not building.)

## 4. Local ↔ cloud parity — the switchability mechanism

This is your #1 concern, and today there's a real gap: **local never exercises Kong**, so path-stripping, auth-header handling, and plugin ordering are untested until you're in GKE. I'd close that.

**Recommendation: add an optional Kong to docker-compose via a Compose profile, running DB-less (declarative) mode.** Then the topology is identical in both environments and you flip between them with one flag:

```bash
docker compose up -d                      # fast inner loop: NO gateway, services direct
docker compose --profile gateway up -d    # parity mode: Kong fronts /claims and /fhir, keys required
```

The existing `FHIR_GATEWAY_URL` + `FHIR_API_KEY` pattern already supports this; Phase 2 adds a parallel `CLAIMS_GATEWAY_URL` for the agent. Same images, same env-var contract, only the target URL and presence of a key change — that *is* "very easily switchable."

**The one honest friction point — config dialect drift.** Kong is configured two different ways:
- **Cloud:** Kubernetes CRDs (`KongPlugin`, `Ingress`, `KongClusterPlugin`) read by the Ingress Controller.
- **Local DB-less:** a single declarative `kong.yml`.

These express the *same* routes + plugins in different syntaxes. Options, in order of my preference for a prototype:
1. Maintain both (they're small — 2 routes, 4 plugins) and add a tiny test asserting they define the same routes/plugins. Pragmatic, low-magic.
2. Use `deck` to generate one from the other. Less duplication, more tooling.

I'd flag this in the plan as a known maintenance cost rather than pretend a single source of truth exists for free.

Minor concrete gotcha: **local Kong admin defaults to :8001, which `triage` already owns.** Map Kong's admin to :8081 locally (proxy stays :8000 to match the cloud port-forward convention).

## 5. The diagram

**Local (default — fast inner loop, no gateway):**
```
mcp-agent (CLI) ──▶ claims-service:8090 ──┬──▶ legacy-rxclaim:8091   (private, direct)
                                          ├──▶ triage:8001           (direct)
                                          └──▶ fhir:8080/fhir        (direct)
   FHIR_GATEWAY_URL=http://fhir:8080/fhir   ·   no API keys
```

**Local `--profile gateway` AND Cloud (GKE) — identical topology:**
```
                         ┌─────────── EDGE PLANE (Kong) ───────────┐
client / mcp-agent ─apikey─▶ Kong proxy ─ key-auth ─ rate-limit ─ log/metrics
                              │   /claims ──▶ claims-service  (façade)
                              │   /fhir   ──▶ fhir-service    (data)
                              └──────────────────┬───────────────────┘
                                                 │  claims-service orchestrates:
                    ┌────────────────────────────┼───────────────────────────┐
                    ▼ (via Kong /fhir, keyed)     ▼ (via Kong, keyed)          ▼ (DIRECT, private)
              fhir-service:8080            triage-service:8001         legacy-rxclaim:8091
              (ClusterIP)                  (ClusterIP)                 (ClusterIP + NetworkPolicy:
                    │                                                   only claims-service allowed)
                    ▼
              Neon fhirdb                  Kong config → Neon kongdb   Neon (legacy DB2-style tables)
```

Cloud namespaces: keep `kong` and `fhir`; add a `claims` namespace holding **both** `claims-service` and `legacy-rxclaim-emulator`, with the emulator locked inside it by NetworkPolicy. Kong routes reference services across namespaces (as it already does for `fhir`).

## 6. What this implies for the plan (deltas to M0–M7)

- **M0 (recon)** also reconciles the compose/README **HAPI version drift** (compose pins `hapiproject/hapi:v7.2.0`; README says built starter 8.8.0) — we need one target before adding services around it.
- **New workstream: gateway parity** — add DB-less Kong to a compose `gateway` profile; author `/claims` route + `claims-service` consumer in both config dialects; NetworkPolicy for the emulator.
- Every new service ships **both** a compose entry and a k8s (deployment + ClusterIP service + configmap) set, mirroring the existing fhir-service layout, so "local ↔ cloud" is structural, not aspirational.

Two calls I need from you before I sequence this into the plan:

1. **Front `triage` with Kong too** (uniform auth/logging on all internal APIs, slightly more config), or **keep triage internal/direct** (simpler, but the FHIR-only gateway boundary stays asymmetric)?
2. **Add the DB-less Kong compose profile** (my recommendation — closes the parity gap), or **keep local strictly Kong-less** and rely on the env-var toggle as today?

## Turn 2

### Prompt

Answers (caveated by questions):

1. Front triage with Kong too (will this need me to setup Kong for dev testing too, I want to avoid that!)
2. Add the DB-less Kong compose profile  (again, will this need me to setup Kong for dev testing too, I want to avoid that!)

### Claude response

Short answer to your worry: **no — your daily dev loop never touches Kong.** Both decisions are designed specifically so you never have to *set up* anything.

## Your normal inner loop is unchanged

```bash
docker compose up -d          # exactly like today: no Kong, direct calls, no API keys
```

This stays the default. No gateway container, no keys, no config. Same speed, same muscle memory. Fronting triage "with Kong" only means *there exists a routed path* through Kong in the gated topology — it does **not** make Kong mandatory locally. When you run the plain command, claims→triage and agent→triage go direct, same as claims→fhir.

## The gateway profile is opt-in and zero-setup

```bash
docker compose --profile gateway up -d    # only when you WANT to test the gated path
```

The key point that removes the burden: this Kong runs **DB-less (declarative)**, which means none of the ceremony from the cloud setup applies —

| Cloud Kong (what you're picturing) | Local DB-less Kong (what this is) |
|---|---|
| Helm install, migrations | ❌ none — just a container image |
| Neon `kongdb` database | ❌ none — config is a file, in memory |
| `create-key.sh` to provision consumers | ❌ none — a fixed dev key is pre-baked in `kong.yml` |
| Admin API port-forward, key storage | ❌ none |

So even "parity mode" is a single `docker compose` command with **zero manual steps**. The one committed dev key (local-only, non-secret) lives in the declarative config, so requests just work.

## When you'd actually use it (rarely)

- A quick sanity check that routes/auth/path-handling behave before pushing to GKE.
- Running the demo's "gated" story.
- CI can run it automatically so gateway regressions get caught without you thinking about it.

That's it. If you never type `--profile gateway`, you'll never notice Kong exists locally.

## Locked decisions

1. ✅ Triage fronted by Kong **in the gated/cloud topology**; direct locally by default.
2. ✅ DB-less Kong compose profile added, **opt-in**, no setup — default stays Kong-less.

Both fold cleanly into the plan (the "gateway parity" workstream in §6 of my last message) with **no new burden on your dev loop**.

I now have everything I need: hybrid stack · fully-runnable e2e demo · convincing legacy shape · Da Vinci-aware · one Kong gateway fronting claims+fhir+triage on the edge, legacy emulator strictly private · opt-in local parity.

Want me to now write this up as a consolidated Phase 2 plan document (e.g. `docs/phase2-plan.md`) — still no application code, just the plan/architecture committed on a feature branch — or keep iterating here first? I can also save the locked decisions to project memory so they survive across sessions.

## Turn 3

### Prompt

I want Phase 1 (all the pre-existing work at the moment) to be seperately runnable and testable, independent of any Phase 2 components. If you want any changes to Phase 1, make them so that it is still independently capable of being brought up and deployed. Note that Phase 1 is alreay tested for Cloud deployment, whereas that part for Phase 2 will take more time coming later. Thoughts?

### Claude response

Strong instinct, and it's very achievable — mostly because Phase 2 should be **additive**, and the fact that Phase 2's cloud story comes later actually *helps* isolation rather than hurting it. Here's how I'd guarantee Phase 1 stays independently runnable, testable, and deployable.

## The governing rule: the dependency arrow points one way

**Phase 2 → Phase 1, never the reverse.** Phase 2 services may depend on the Phase 1 FHIR server and triage; nothing in Phase 1 may know Phase 2 exists. If I hold that line, Phase 1 comes up and passes tests with Phase 2 entirely absent.

## How each shared surface stays isolated

**1. Docker Compose — profiles, default unchanged.**
New services (`claims-service`, `legacy-rxclaim-emulator`) get `profiles: [phase2]`. The Phase 1 three (`fhir`, `triage`, `mcp-agent`) get **no profile**, so:
```bash
docker compose up -d                 # ← identical to today: only Phase 1
docker compose --profile phase2 up   # ← adds Phase 2 (which pulls Phase 1 up as its substrate)
```
Profiled services never start unless named. `depends_on` flows Phase2→Phase1 only, so Phase 1 never drags Phase 2 in. I'll verify with `docker compose config` that the default service set is byte-for-byte today's. Editing the shared compose file is unavoidable, but the edits are purely additive and gated.

**2. Cloud deploy — don't touch it yet.** [deploy.sh](deploy.sh) and the live [gateway/kong/](gateway/kong/) config stay **Phase-1-only**. Since Phase 2 cloud comes later, Phase 2 gateway routes (`/claims`, fronting triage) go in *separate* files (e.g. `gateway/kong/phase2/`) applied by a future `deploy-phase2.sh`. Your proven, cloud-tested Phase 1 deploy path is literally unmodified. This is the cleanest part: the "front triage with Kong" decision is a Phase 2 **cloud** change, deferred — so Phase 1's cloud posture (FHIR-only gateway) stays exactly as tested. Locally it's just the opt-in profile.

**3. Tests — separately invocable.** Phase 1 suites (triage, mcp-agent, client, fhir-service `mvn verify`) must pass with zero Phase 2 present. Phase 2 tests live in the new service dirs with their own markers, runnable in isolation. CI keeps a "Phase 1 only" job so a Phase 2 regression can never be reported as a Phase 1 failure.

**4. Data seeding — separate scripts.** [seed_demo.py](data/scripts/seed_demo.py) (Kristle Mraz / John Doe) is untouched. Phase 2 gets its own `seed_claims_demo.py` + a `data/payer-kb/` folder. The Phase 1 refill demo needs no Phase 2 data.

**5. Shared substrate is fine — additively.** Both phases use the same HAPI server and [client/clinical](client/clinical/). That's desirable (one source of truth). The constraint: Phase 2 only *adds* FHIR resource types (Claim, Coverage, ClaimResponse…) and only *adds* methods to `client/clinical` — never changes an existing signature or the Phase 1 contract.

## The one real coupling risk: the MCP agent

This is where isolation can quietly leak. The PRD wants the agent to *explain adjudication outcomes* — but [mcp-agent](mcp-agent/src/agent/) currently runs the Phase 1 refill demo, and adding claims logic to `tools.py`/`agent.py` couples it to Phase 2.

My recommendation: **keep the existing agent Phase-1-pure and add claims explanation as a separate, feature-flagged capability** — new claims tools registered only when `CLAIMS_GATEWAY_URL`/claims env is present; absent that, the agent behaves exactly as today and the refill demo runs untouched. (Alternative: a distinct agent entrypoint/command for claims. Same isolation, more duplication.) Either way, `docker compose run --rm mcp-agent --query "Check refill risk for Kristle Mraz"` must keep working with no Phase 2 anywhere.

## One safety net I'd add

Since Phase 1 is stable and cloud-tested, **tag a known-good snapshot** (e.g. `git tag phase1-v1`) before Phase 2 work lands. It gives you a guaranteed independently-deployable reference point and a trivial way to prove "Phase 1 still stands alone" at any time. Low effort, high peace-of-mind.

## Net effect

- `docker compose up` + Phase 1 tests + `deploy.sh` → **behave identically to today, forever.**
- Phase 2 is opt-in locally (`--profile phase2`, plus `--profile gateway` when you want the gated path), and stays out of the cloud path until its own deploy tooling is ready.

Two decisions for you, then I'm ready to write the consolidated plan (still no app code):

1. **Agent isolation:** feature-flagged claims capability inside the existing agent (my rec), or a separate claims-agent entrypoint?
2. **Tag `phase1-v1`** now as the known-good snapshot before Phase 2 begins — yes/no?

## Turn 4

### Prompt

Yes, tag Phase 1 now. I juse tested it!

ALso, maybe building a seperate agent just for claims is a better idea than combining two agents?

### Claude response

Both make sense. The separate claims agent is the more consistent choice — I'll explain why after I tag Phase 1.

**Git context before the write:** worktree `/workspaces/fhir-agent`, branch `main`, HEAD `d4cd4be`. Intended action: create an **annotated tag** `phase1-v1` on the current commit. This adds a tag pointer only — it does **not** commit to `main` or alter history. Let me verify the tree is clean first, then tag.

Clean tree, on `main` at `d4cd4be`, no existing tags. Creating the annotated tag:

✅ Annotated tag `phase1-v1` created locally on `d4cd4be` (current `main` HEAD). It's **local only** so far — pushing to `origin` is an outward-facing step, so I'll hold unless you confirm. Say "push the tag" and I'll run `git push origin phase1-v1`.

## Separate claims agent — agreed, it's the more consistent choice

Yes, a standalone claims agent beats bolting onto the existing one. It falls straight out of the isolation rule we just set:

**Why it's better here:**
- **Zero coupling.** The Phase 1 refill agent stays byte-for-byte untouched — no feature flags, no conditional tool registration, no risk that a claims change breaks the refill demo. Isolation becomes structural, not disciplined-by-convention.
- **Different job, different tools.** The refill agent's tools are patient/medication/allergy + triage. The claims agent's are claim-submission + adjudication-explanation over the new `/claims` façade. Forcing both into one tool catalog muddies each. Two focused agents read more clearly.
- **Matches the PRD narrative.** The doc frames the MCP layer as an *explanation/orchestration* layer over the claims façade — a distinct deliverable ("MCP Explanation Agent," slice 3). A separate service maps 1:1 to that.
- **Fits the profile model.** It's a new compose service under `profiles: [phase2]`, so `docker compose up` (Phase 1) never starts it.

**The tradeoff to manage (cheaply):** two agents will share plumbing — the Anthropic client setup, tool-loop scaffolding, output formatting, the `ANTHROPIC_API_KEY`/`CLAUDE_API_KEY` handling. To avoid copy-paste drift, I'd factor the genuinely-shared, **non-clinical** bits into a small shared module both agents import, while each keeps its own tools and prompt. That keeps CLAUDE.md's "agent holds no clinical logic" intact and avoids duplicating the boilerplate. If the shared surface turns out to be tiny, a little duplication is fine too — I'll decide once I see how much `mcp-agent/src/agent/` actually shares.

**Structure I'd propose:**
```
mcp-agent/          # Phase 1, unchanged — refill risk agent
claims-agent/       # Phase 2, new — claims explanation/orchestration agent
                    #   reuses shared Anthropic/tool-loop plumbing, its own tools + prompt
```

---

## Where we are

All Phase 2 decisions are now locked:
- Hybrid stack (Java façade + legacy emulator + ACL; reuse Python triage for CDS)
- Fully-runnable e2e demo · convincing legacy shape · Da Vinci-aware, generic resources
- One Kong gateway on the edge (claims + fhir + triage), legacy emulator strictly private; opt-in local `--profile gateway`, zero setup
- **Phase 1 stays fully independent** (additive-only, profiles, cloud deploy untouched, `phase1-v1` tagged)
- **Separate claims agent**, sharing only non-clinical plumbing

Next step options:
1. **Write the consolidated Phase 2 plan** to `docs/phase2-plan.md` on a feature branch (`feature/phase2-planning`) — plan/architecture only, no app code — and open it for review.
2. **Save the locked decisions to project memory** so they persist across sessions.
3. **Push `phase1-v1`** to origin.

Want all three? I'd do the memory write, push the tag (on your OK), then draft the plan doc on a branch.

## Turn 5

### Prompt

First, push the tag

Next, analyze all existing doumentation including READMEs, rules, and what not. MAke sure the new work makes total sense.

LAst, create plan documentation. Neatly save the requirements somewhere. Note that we have deviated somewhat from the PRD. I would like to save the requirements that we actually agreed to implement.

Do NOT do any implementation work yet.

### Claude response

I'll push the tag first, then do a thorough documentation analysis, then write the plan. No implementation.

✅ Tag pushed — `phase1-v1` now on origin, pointing at `d4cd4be`.

Now the documentation analysis. Let me read all the docs, rules, and configs comprehensively so the new work is consistent with what exists. I'll dispatch parallel readers to cover the ground efficiently.

Let me read the key docs in parallel via subagents to cover ground thoroughly, plus read the most critical ones directly.

Both readers are running. While they work, let me read the two most decision-critical files directly myself — the rules engine in full and CLAUDE.md's rules mirror — so I can reconcile the plan against exact conventions.

The triage engine is now crystal clear — first-match-wins `evaluate(medications, allergies) -> RuleResult`, rules registered in a `RULES` list, clinical code sets as constants. Phase 2 clinical safety (drug-allergy/dup-therapy) reuses this via its HTTP API. Let me check `.clinerules` (no agent is covering it) since CLAUDE.md says to keep them in sync.

I've directly confirmed the two most critical things (the triage rules engine internals and that `.clinerules`/`CLAUDE.md` are semantically-equivalent mirrors that must stay in sync). Two background readers are analyzing the remaining service and infra documentation. I'll draft the plan once they report — waiting on their findings so the plan is grounded, not guessed.

## Turn 6

### Prompt

<task-notification>
<task-id>a4286564f3165196d</task-id>
<tool-use-id>toolu_018sUF9rvwGZ2tcB1sTeWsE1</tool-use-id>
<output-file>/tmp/claude-1000/-workspaces-fhir-agent/bebf7ac2-4f1b-4a70-8685-440da76db7e1/tasks/a4286564f3165196d.output</output-file>
<status>completed</status>
<summary>Agent "Analyze service READMEs &amp; rules" finished</summary>
<note>A task-notification fires each time this agent stops with no live background children of its own. The user can send it another message and resume it, so the same task-id may notify more than once.</note>
<result>I've read all the files. Here is the structured summary for your Phase 2 (prescription claim adjudication) planning.

---

# Repo overview

Four cooperating components, strictly layered:

`fhir-service` (Java/HAPI, not read) → `client/platform` (protocol tests) and `client/clinical` (domain client) → `triage-service` (rule engine, FastAPI) → `mcp-agent` (LLM orchestrator). Each layer only knows about the one below it. Clinical logic lives ONLY in `triage-service`; the agent orchestrates and narrates but holds no clinical logic.

---

# 1. What each component does + public interface

## `client/clinical` — `fhir_clinical_client` package
File: `/workspaces/fhir-agent/client/clinical/src/fhir_clinical_client/fhir_client.py`

The domain-abstraction layer. Hides all FHIR mechanics (bundles, search params, HTTP, JSON) behind clinical-domain methods. This is the foundation both the triage service and the agent build on.

Public interface (exported in `__init__.py`, `__version__ = "0.1.0"`):
- `FHIRClient(gateway_url: str, api_key: Optional[str] = None)` — normalizes `gateway_url` (accepts with/without trailing `/fhir`).
- Methods:
  - `get_server_status() -&gt; dict`
  - `create_patient(family, given, gender, birth_date=None) -&gt; str`
  - `get_patient(patient_id) -&gt; Patient`
  - `search_patients(name) -&gt; list[Patient]` (splits name on whitespace, ANDs `name=` params, `_count=20`)
  - `delete_patient(patient_id) -&gt; None`
  - `get_medications(patient_id) -&gt; list[Medication]` (queries `MedicationRequest?patient=...&amp;status=active&amp;_count=100` — active only)
  - `get_allergies(patient_id) -&gt; list[Allergy]` (all statuses)
  - `get_conditions(patient_id) -&gt; list[Condition]` (all statuses)
- Domain dataclasses: `Patient`, `Medication` (`code`=RxNorm, `display`, `status`, `authored_on`, `dosage_text`), `Allergy` (`code`=SNOMED, `display`, `criticality`, `category: list[str]`, `recorded_date`), `Condition`.
- Exceptions: `FHIRClientError(message, status_code=0, body=None)`, and subclasses `AuthenticationError` (401), `NotFoundError` (404).

Domain vocabulary exposed: patients, medications (RxNorm), allergies (SNOMED, criticality low/high/unable-to-assess, category medication/food/environment), conditions (SNOMED, clinical_status). NO coverage/claim/formulary vocabulary exists.

## `client/platform`
File: `/workspaces/fhir-agent/client/platform/README.md` — only an `integration_test.py` for platform engineers testing the raw FHIR server (no Kong/API key). Not a client library. Different audience ("Hat 1"). Not relevant to building clinical workflows.

## `triage-service` — FastAPI rule engine
Files: `/workspaces/fhir-agent/triage-service/src/triage/{main.py,rules.py,models.py}`

Stateless microservice. `POST /triage/refill-risk` (body `{patient_id, medication_id?}`) fetches meds+allergies via `FHIRClient`, runs `rules.evaluate()`, returns a FHIR `RiskAssessment` resource. `GET /health` returns `{status, version}`. `VERSION = "0.1.0"`.

Response model = FHIR `RiskAssessment` (`models.py`): `RiskAssessmentResponse` with `resourceType`, `id` (`risk-{uuid8}`), `status`, `subject`, `prediction: list[PredictionModel]`, `note: list[AnnotationModel]`, `basis: list[ReferenceModel]`. Supporting models: `CodingModel`, `CodeableConceptModel`, `PredictionModel`, `AnnotationModel`, `ReferenceModel`.

## `mcp-agent` — LLM orchestrator
Files: `/workspaces/fhir-agent/mcp-agent/src/agent/{agent.py,tools.py,format.py}`

Raw Anthropic tool-use loop (no framework). `MODEL = "claude-sonnet-4-5"`, `MAX_TOKENS = 1024`. `run_query(client, user_input, messages=None, verbose=True) -&gt; (final_text, messages)` runs the tool loop. Two tools in `tools.py` `TOOL_DEFINITIONS`: `get_patient_summary(name)` and `assess_refill_risk(patient_id, medication_id?)` (the latter HTTP-POSTs to `TRIAGE_SERVICE_URL/triage/refill-risk` via `httpx`). Dispatcher `execute_tool(name, inputs) -&gt; str` (JSON string). `format.py` handles terminal output with `RISK_ICONS`/`RISK_LABELS` keyed on HIGH/MODERATE/LOW.

---

# 2. Conventions you must follow for adjacent code

**Layering (most important):** Never let FHIR mechanics leak upward. All FHIR resource parsing stays in `fhir_client.py` static parsers (`_parse_*`). Clinical logic stays in `triage-service`. The agent gets no new clinical logic — it only orchestrates. For claim adjudication you'd likely add: new `FHIRClient` methods (e.g. `get_coverage`, `get_medication_dispenses`), new domain dataclasses, a new triage-style rule engine/endpoint, and a new agent tool.

**Naming/structure:**
- Client methods: `get_&lt;domain&gt;(patient_id) -&gt; list[&lt;Dataclass&gt;]`; each has a private static `_parse_&lt;domain&gt;(resource) -&gt; Dataclass`; filter Bundle entries by `resourceType`.
- Domain models are `@dataclass` with domain field names (not FHIR names), `Optional[date]` for dates parsed via `FHIRClient._parse_date`.
- Triage rules use dataclasses; risk levels are the `Literal["HIGH","MODERATE","LOW"]` `RiskLevel` type.
- Section-header comment style (`─────`) is used throughout.

**Error handling:**
- Client raises typed `FHIRClientError`/`AuthenticationError`/`NotFoundError` — never raw HTTP.
- Service catches `NotFoundError` → HTTP 404, `FHIRClientError` → HTTP 502.
- Agent tools catch exceptions and return `{"error": ...}` dicts (never raise into the loop); httpx errors mapped to friendly messages.

**Config:** `FHIR_GATEWAY_URL` (required), `FHIR_API_KEY` (optional, local-dev fallback with no auth), `TRIAGE_SERVICE_URL` (default `http://localhost:8001`), `ANTHROPIC_API_KEY` (with `CLAUDE_API_KEY` fallback). Build clients via the `_get_client()`/`_fhir_client()` env pattern. Everything is currently `version 0.1.0`.

**FHIR read/write:** reads via `_request(path, method="GET")` returning `(status, body)`; writes via POST returning 201 and reading `body["id"]`. `_request` sets `Content-Type/Accept: application/fhir+json` and `apikey` header. Client uses stdlib `urllib` deliberately (README design note says Phase 2 async/OAuth would migrate to `httpx`, isolated to `fhir_client.py`).

---

# 3. Claims-adjudication concepts that already exist

**Nothing about insurance/claim adjudication proper exists** — no eligibility, no formulary, no prior-authorization, no Coverage/Claim/ClaimResponse resources anywhere. The clinical client has NO `Coverage`/`Claim` methods. So Phase 2 adjudication (eligibility, formulary, prior-auth, coverage) is greenfield and won't duplicate anything.

**BUT two clinical checks you listed already exist in the triage rule engine** (`rules.py`) — drug-allergy and duplicate-therapy. Do not re-implement these; reuse or call them.

Rule structure (quote):
```python
RiskLevel = Literal["HIGH", "MODERATE", "LOW"]

@dataclass
class RuleResult:
    risk_level: RiskLevel
    rule_id: str
    note: str
    basis_medication_ids: list[str] = field(default_factory=list)
    basis_allergy_ids: list[str] = field(default_factory=list)

@dataclass
class Rule:
    id: str
    name: str
    evaluate: Callable[[list[Medication], list[Allergy]], RuleResult | None]
```

An `evaluate` function returns a `RuleResult` on match or `None` on no-match. The engine iterates the registry, **first match wins**, else a default LOW:
```python
def evaluate(medications, allergies) -&gt; RuleResult:
    for rule in RULES:
        result = rule.evaluate(medications, allergies)
        if result is not None:
            return result
    return _DEFAULT_LOW
```

**Drug-allergy** = `_rule_penicillin_conflict` (rule_id `"penicillin-conflict"`, HIGH) plus `_rule_high_criticality_allergy` (rule_id `"high-criticality-allergy"`, MODERATE). Penicillin detection uses `PENICILLIN_RXNORM_CODES`, `PENICILLIN_DISPLAY_FRAGMENTS`, `PENICILLIN_ALLERGY_SNOMED_CODES` and helpers `_is_penicillin_medication`, `_is_penicillin_allergy`.

**Duplicate-therapy** = `_rule_duplicate_therapeutic_class` (rule_id `"duplicate-therapeutic-class"`, MODERATE). Uses the `THERAPEUTIC_CLASSES: dict[str, set[str]]` map (antihistamine, statin, ace_inhibitor, arb, ssri, ppi) and helper `_therapeutic_class(med)`.

**How to add a new rule** (per the module docstring and README: "Adding a new rule is adding one item to RULES"):
1. Write `def _rule_&lt;name&gt;(medications, allergies) -&gt; RuleResult | None:` returning a `RuleResult` (populate `risk_level`, `rule_id`, `note`, `basis_medication_ids`/`basis_allergy_ids`) or `None`.
2. Append a `Rule(id=..., name=..., evaluate=_rule_&lt;name&gt;)` to the `RULES` list, positioned by priority (first match wins — order matters).

Registry today:
```python
RULES: list[Rule] = [
    Rule(id="penicillin-conflict", name="Penicillin family drug-allergy conflict", evaluate=_rule_penicillin_conflict),
    Rule(id="duplicate-therapeutic-class", name="Duplicate therapeutic class", evaluate=_rule_duplicate_therapeutic_class),
    Rule(id="high-criticality-allergy", name="High-criticality allergy on record", evaluate=_rule_high_criticality_allergy),
]
```

Caveat: the current `Rule.evaluate` signature is fixed at `Callable[[list[Medication], list[Allergy]], RuleResult | None]`. Adjudication rules needing coverage/formulary/dispense data won't fit this signature — see extension notes below.

---

# 4. Extension points to reuse vs. things NOT to modify

**Reuse / extend:**
- `FHIRClient` — add new read methods (`get_coverage`, `get_medication_dispenses`, etc.) and new dataclasses following the `_parse_*` pattern. This is the sanctioned extension point; the client README explicitly anticipates Phase 2 (async/OAuth migration note, `get_appointments` stub at line ~450 in `fhir_client.py`).
- The rule-engine pattern in `rules.py` — mirror `Rule`/`RuleResult`/`evaluate` for an adjudication engine.
- `RiskAssessmentResponse` model pattern — for adjudication you'd likely emit a FHIR `ClaimResponse`/`CoverageEligibilityResponse` in the same "return a FHIR resource so it's audit-storable" style.
- The agent tool pattern (`TOOL_DEFINITIONS` + `execute_tool` dispatcher + `_fhir_client()`/`_triage_url()` factories) — add a new tool + a new service URL env var.
- `format.py` `RISK_ICONS`/`RISK_LABELS`/`DIVIDER` conventions for any new terminal output.

**Do NOT modify (to keep Phase 1 independent):**
- Existing rule functions and the `RULES` registry semantics — don't change signatures/priority ordering of `penicillin-conflict`, `duplicate-therapeutic-class`, `high-criticality-allergy`, or the first-match-wins contract. Adding a Phase-2 adjudication rule set that needs Coverage data means creating a NEW engine/endpoint rather than widening `Rule.evaluate`'s signature (which would ripple through Phase 1).
- The `POST /triage/refill-risk` contract and `RiskAssessmentResponse` shape — the agent and its tests depend on it. Add a new endpoint (e.g. `POST /adjudication/...`) rather than overloading this one.
- `client/platform/` and `fhir-service/` — the top-level `client/README.md` states audiences must not modify each other's folders; clinical/Phase-2 developers stay out of `client/platform/` and `fhir-service/`.
- The `mcp-agent` "no clinical logic" rule — put adjudication decisions in a service, not in the agent or its tools.

One correctness note if you touch `rules.py`: `PENICILLIN_ALLERGY_SNOMED_CODES` contains intentional duplicate literals (`"372687004"` thrice) — harmless in a set, but don't "clean it up" expecting behavior change.</result>
<usage><subagent_tokens>41854</subagent_tokens><tool_uses>13</tool_uses><duration_ms>68174</duration_ms></usage>
</task-notification>

### Claude response

Rich confirmation. Key planning locks from this analysis:
- **Reuse `POST /triage/refill-risk` as-is** for Phase 2 clinical safety — it already takes `{patient_id, medication_id?}`, so the Java claims-service just calls it over HTTP. **No triage changes needed** → Phase 1 stays untouched.
- Adjudication proper (eligibility/formulary/prior-auth/coverage) is **greenfield** — no duplication risk.
- Additive extension points confirmed: new `FHIRClient` methods (for the Python claims-agent), new triage-style engine, mirror the "return a FHIR resource" pattern (`ClaimResponse`/`CoverageEligibilityResponse`).
- Hard constraints: don't touch `Rule.evaluate` signature or the `/triage/refill-risk` contract; agent holds no clinical logic; audiences don't cross into `client/platform` or `fhir-service`.

Waiting on the infra/data reader before drafting — it covers the k8s pattern, seeding conventions, and the emulator-README question I need to resolve.

<details>
<summary>Execution details — 12 tool events</summary>

### Turn 1 activity

- **Bash** `echo "===== gateway tree ====="; find gateway -type f | sort
echo; echo "===== docker-compose.yml (full) ====="; cat docker-compose.yml
echo; echo "===== is kong in compose? ====="; grep -ni kong dock…`
- **Bash** `cd gateway
echo "===== gateway/README.md ====="; cat README.md
echo; echo "===== kong-ingress.yaml ====="; cat kong/kong-ingress.yaml
echo; echo "===== kong-plugins.yaml ====="; cat kong/kong-plugins.…`
- **Bash** `echo "===== fhir-service/k8s ====="; ls -la fhir-service/k8s 2>/dev/null; echo "---"; for f in fhir-service/k8s/*.yaml; do echo "### $f"; grep -nE 'kind:|name:|namespace:|type:|port|ClusterIP|LoadBala…`
- **Bash** `cd /workspaces/fhir-agent
echo "===== fhir-service/k8s ====="; ls -la fhir-service/k8s 2>/dev/null
echo "---files---"; find fhir-service/k8s -type f 2>/dev/null
echo; echo "===== k8s kinds/services ==…`

### Turn 4 activity

- **Bash** `cd /workspaces/fhir-agent
echo "=== branch & HEAD ==="; git rev-parse --abbrev-ref HEAD; git rev-parse --short HEAD
echo "=== status ==="; git status --porcelain || true
echo "=== existing tags ===";…`
- **Bash** `cd /workspaces/fhir-agent
git tag -a phase1-v1 -m "Phase 1: Agentic Healthcare Platform — prescription refill risk triage.

Known-good, independently runnable and cloud-tested snapshot taken before Ph…`

### Turn 5 activity

- **Bash** `cd /workspaces/fhir-agent
git push origin phase1-v1
echo "=== verify remote tag ==="; git ls-remote --tags origin | grep phase1-v1`
- **Bash** `cd /workspaces/fhir-agent
echo "=== All markdown/docs inventory ==="; find . -name '*.md' -not -path '*/node_modules/*' -not -path '*/target/*' -not -path '*/.git/*' -not -path '*/.pytest_cache/*' | s…`
- **Agent** `Analyze service READMEs & rules`
- **Agent** `Analyze infra & data docs`
- **Read** `/workspaces/fhir-agent/triage-service/src/triage/rules.py`
- **Bash** `cd /workspaces/fhir-agent
echo "=== diff CLAUDE.md vs .clinerules (structural) ==="
diff <(grep -E '^#|^##' CLAUDE.md) <(grep -E '^#|^##' .clinerules) && echo "HEADINGS IDENTICAL" || echo "(headings d…`

</details>

---

## Archive metadata

- **Source:** Claude Code
- **Session ID:** `bebf7ac2-4f1b-4a70-8685-440da76db7e1`
- **Created:** 13 July 2026, 22:16 UTC
- **Last updated:** 13 July 2026, 22:54 UTC
- **Turns:** 6
- **Status:** Complete
