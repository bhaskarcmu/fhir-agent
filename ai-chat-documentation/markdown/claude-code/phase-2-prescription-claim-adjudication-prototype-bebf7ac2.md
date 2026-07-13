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

<details>
<summary>Execution details — 6 tool events</summary>

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

</details>

---

## Archive metadata

- **Source:** Claude Code
- **Session ID:** `bebf7ac2-4f1b-4a70-8685-440da76db7e1`
- **Created:** 13 July 2026, 22:16 UTC
- **Last updated:** 13 July 2026, 22:49 UTC
- **Turns:** 4
- **Status:** Complete
