# Gateway Runbook

**The single operational source of truth for the Kong edge**, across both phases and all three
strangler states. If a gateway question has an operational answer, it is here or linked from
here.

The gateway is the one genuinely **cross-phase** artifact, and the only place where "Phase 1 vs
Phase 2" is an operational fact rather than a documentation boundary. Two Kong deployments exist
by design. That is not drift — it is a bounded, reversible migration (decision **C2** + the
gateway-strangler). This page exists so nobody has to reconstruct that from two READMEs and a
plan.

| You want to… | Go to |
|---|---|
| Run the gated stack locally | [§3 Local](#3-local-operations-phase-2-db-less-kong) |
| Know which gateway owns a route | [§2 Route ownership](#2-route-ownership) |
| Deploy or operate the cloud gateway | [§4 Cloud](#4-cloud-operations) |
| Migrate `/fhir` off the old gateway | [§5 Strangler](#5-the-strangler-s0--s1--s2) |
| Understand why there are two Kongs | [§1 States](#1-the-two-gateways-and-three-states) |
| Fix something | [§6 Troubleshooting](#6-troubleshooting) |

---

## 1. The two gateways, and three states

| | **Phase 1 Kong (KIC)** | **Phase 2 Kong (DB-less)** |
|---|---|---|
| Config dialect | Kubernetes CRDs (Ingress + plugins) | Declarative YAML, one file |
| Config source | `gateway/kong/kong-ingress.yaml`, `kong-plugins.yaml`, `kong-values.yaml` | `gateway/kong/kong.tmpl.yml` → generated `kong.yml` |
| Backing store | PostgreSQL (`kongdb`) | **None** (`KONG_DATABASE: off`, in-memory) |
| Install | Helm, on GKE | `docker compose --profile gateway` |
| Runs locally? | No — cloud only | **Yes** |
| Runs in cloud? | **Yes** — deployed today | No — not deployed ([§4](#4-cloud-operations)) |
| Fronts | `/fhir` | `/claims`, `/fhir`, `/triage` |
| Owner | Platform/SRE (existing) | Phase 2 |
| Docs | [`gateway/README.md`](../gateway/README.md) — deploy steps | this page + [`plan.md` §3](./phase2/plan.md#3-gateway--localcloud-parity) |

**Why two.** Phase 1's KIC Kong is deployed, working, and serving real traffic. Rewriting it to
adopt Phase 2's dialect would rework a proven cloud path for no functional gain and put R9
(Phase 1 independence) at risk. So Phase 2 brings its own DB-less Kong, and the old one is
strangled **on our schedule, with a rollback** — not in a big-bang cutover.

**Current state: S0.** See [§5](#5-the-strangler-s0--s1--s2) for S1/S2.

## 2. Route ownership

| Route | Upstream | S0 (today) | S1 | S2 | Notes |
|---|---|---|---|---|---|
| `/fhir` | `fhir-service:8080` | **KIC (cloud)** | **KIC (cloud)** | **DB-less** | The only route that ever changes owner. Proven in the local DB-less config already. |
| `/claims` | `claims-service:8090` | DB-less (local only) | **DB-less** | **DB-less** | Phase 2 façade — the edge entry point for adjudication. |
| `/triage` | `triage-service:8001` | DB-less (local only) | **DB-less** | **DB-less** | Phase 1 service, newly *routable* at the edge. Its behaviour is unchanged (R9). |
| *(none)* | `rxclaim-emulator:8091` | — | — | — | **Deliberately unroutable.** No edge route, ever. |

**The emulator has no route and no published port.** This is what makes the API-façade and
anti-corruption story real rather than cosmetic: there is no path from the edge to the legacy
core except through `claims-service`. If you ever find yourself adding a route for it, stop —
that is the architecture failing, not a config gap.

All routes use `strip_path: false`, so upstreams see the full path (`/claims/adjudicate` arrives
as `/claims/adjudicate`).

## 3. Local operations (Phase 2 DB-less Kong)

### The three local modes

```bash
docker compose up -d                                       # Phase 1 only. No Kong, no keys.
docker compose --profile phase2 up -d                      # + Phase 2 services, direct calls. No Kong.
docker compose --profile phase2 --profile gateway up -d    # + edge Kong fronting everything.
```

The default and `phase2` inner loops are **deliberately Kong-less** — zero gateway setup for
everyday development. Reach for `--profile gateway` when you specifically want to test the
**gated** path (auth, the edge contract, cloud parity).

### Template → generated config (read this before editing anything)

**The committed file is a template. `kong.yml` does not exist in your working tree and must
never be committed.**

```
gateway/kong/kong.tmpl.yml          ← COMMITTED. Contains the literal placeholder __DEV_KEY__
        │
        │  at `docker compose up`, inside the Kong container's entrypoint:
        │    KEY=$(cat /proc/sys/kernel/random/uuid | tr -d '-')
        │    sed "s/__DEV_KEY__/$KEY/" /kong/kong.tmpl.yml > /tmp/kong.yml
        │    echo "[kong] DEV APIKEY: $KEY"
        ▼
/tmp/kong.yml (inside the container)  ← GENERATED, ephemeral, never on your disk
        │
        ▼
   KONG_DECLARATIVE_CONFIG=/tmp/kong.yml   ← what Kong actually loads
```

Consequences worth internalising:

- **Edit `kong.tmpl.yml`**, never `kong.yml`. Docs (and older plan text) that say "`kong.yml`"
  mean *the declarative config*, whose committed form is the template.
- **The dev API key is generated fresh on every `up`.** It is not stable across restarts and no
  secret is ever committed (R10, gitleaks-clean).
- **Changing the template requires a container restart** to re-render.

### Get the dev API key

```bash
docker compose logs kong | grep 'DEV APIKEY'
# [kong] DEV APIKEY: <32 hex characters, generated at startup>
```

> The placeholder above is deliberate. Docs that carry realistic-looking keys train readers to
> wave secret scanners through ("that's just the doc example") — and that habit is how a real one
> eventually lands. This repo's scan stays clean, so an alert always means something.

### Call the gated edge

```bash
KEY=$(docker compose logs kong | grep -o 'DEV APIKEY: .*' | tail -1 | cut -d' ' -f3)

curl -H "apikey: $KEY" http://localhost:8000/fhir/metadata          # FHIR through the edge
curl -H "apikey: $KEY" http://localhost:8000/claims/adjudicate \
     -H 'Content-Type: application/json' --data @claim.json          # adjudicate through the edge

curl -i http://localhost:8000/fhir/metadata                          # no key → expect 401
```

`key-auth` runs with `hide_credentials: true`, so the key is stripped before the request reaches
the upstream — services never see it.

### Point the tooling at the gateway

Switching is **config-only**, via environment variables — no code changes:

| Variable | Direct (default) | Gated |
|---|---|---|
| `CLAIMS_GATEWAY_URL` | `http://localhost:8090` | `http://localhost:8000` |
| `FHIR_GATEWAY_URL` | `http://localhost:8080/fhir` | `http://localhost:8000/fhir` |
| `TRIAGE_SERVICE_URL` | `http://localhost:8001` | `http://localhost:8000/triage` |
| `CLAIMS_API_KEY` / `FHIR_API_KEY` | *(unset)* | the generated dev key |

```bash
CLAIMS_GATEWAY_URL=http://localhost:8000 CLAIMS_API_KEY=$KEY python3 data/scripts/seed_claims_demo.py
CLAIMS_GATEWAY_URL=http://localhost:8000 CLAIMS_API_KEY=$KEY pytest e2e/
```

## 4. Cloud operations

### Phase 1 gateway (KIC on GKE) — deployed, real

This is the **only** gateway running in cloud today. It is fully documented, procedure by
procedure, in [`gateway/README.md`](../gateway/README.md): create the Kong DB secret, install via
Helm, apply the CRDs, port-forward and test, provision consumer keys with `create-key.sh`.

That page is the operational authority for Phase 1 cloud. It is **not** duplicated here — this
runbook owns the *cross-phase* picture (which gateway owns what, and how the migration runs).

> `gateway/kong/kong-consumers.yaml` contains **provisioning instructions only** — no Kubernetes
> resources. Do not apply it. Use `create-key.sh` after deployment.

### Phase 2 gateway (DB-less on Cloud Run) — ⚠️ NOT DEPLOYED

**There is no cloud deploy procedure for the Phase 2 gateway, because it has never been
deployed, and the IaC to deploy it does not exist.** Specifically:

- No `infra/terraform/` root module and no `deploy-phase2.sh`.
- The per-service Cloud Run stubs (`claims-service/infra/main.tf`,
  `rxclaim-emulator/infra/main.tf`) are unreferenced fragments.
- No Kong Cloud Run service definition exists at all.

See the [cloud-delivery gap](./phase2/plan.md#6-workstreams--milestones) and §16 item 9.

**What is genuinely de-risked**, and worth saying precisely: the *declarative dialect* is the
same one intended for cloud (C2), and it is exercised locally on every `--profile gateway` run.
Only the upstream URLs change (Cloud Run URLs instead of compose service names). So the config
shape is proven; the deployment is not. Writing this runbook's cloud half is part of item 10.

## 5. The strangler: S0 → S1 → S2

| State | Phase 1 KIC Kong | Phase 2 DB-less Kong | `/fhir` served by | Requires Phase 1 change? |
|---|---|---|---|---|
| **S0 — today** | `/fhir` (GKE) | local only | KIC | — |
| **S1 — Phase 2b deploy** | `/fhir` (GKE, untouched) | `/claims`, `/triage` (Cloud Run) | KIC | **No** (R9 preserved) |
| **S2 — opt-in migration** | idle, then removed | `/claims`, `/triage`, **`/fhir`** | DB-less | No |

### S0 → S1

Deploy the Phase 2 DB-less Kong alongside the existing KIC Kong, serving **only** `/claims` and
`/triage`. **Touch nothing in Phase 1** — no Helm changes, no CRD changes, no `deploy.sh`
changes. Phase 1's `/fhir` keeps flowing through KIC exactly as before. This is the whole point
of the hybrid: S1 is additive, so it cannot break Phase 1.

*Blocked on:* the cloud IaC ([§4](#4-cloud-operations)).

### S1 → S2 (the only risky step)

1. Add the `/fhir` route to the DB-less config. **It is already proven** — the local template
   has carried this route since day one, which is precisely why it is there.
2. Provision consumer keys on the DB-less Kong for existing `/fhir` consumers.
3. Verify the DB-less Kong serves `/fhir` correctly **while still receiving no production
   traffic**.
4. Cut DNS/ingress over.
5. Watch. Keep the KIC Kong running and healthy.
6. Only after S2 is confirmed healthy: decommission the KIC Kong.

### Rollback

**Re-point DNS/ingress to the KIC Kong.** It is still running and untouched throughout S1→S2 —
that is why step 5 exists and why decommissioning is last. Rollback needs no config restore, no
redeploy, and no Phase 1 change: the old path was never dismantled, only bypassed.

**Ownership:** platform/SRE owns the S1→S2 cutover and rollback. S0→S1 requires no Phase 1
change and is Phase 2's to run.

## 6. Troubleshooting

**`401` on every gated call.** The key rotates on every `up`. Re-read it:
`docker compose logs kong | grep 'DEV APIKEY'`. A key from a previous session is dead.

**Edited `kong.yml` and nothing happened.** There is no `kong.yml` in the repo. Edit
`gateway/kong/kong.tmpl.yml` and restart the container (see [§3](#3-local-operations-phase-2-db-less-kong)).

**Port `8001` conflict.** `triage` owns `8001` locally. Kong's **admin** API must not use it —
map admin to `8081` if you enable it. It is currently `KONG_ADMIN_LISTEN: "off"` (nothing to
conflict). The proxy stays on `8000` to match the cloud port-forward convention.

**Kong won't start.** The generated config is invalid — usually a template edit that broke YAML.
`docker compose logs kong` shows the parse error with a line number *from the generated file*;
map it back to the template (the only substitution is `__DEV_KEY__`, so line numbers align).

**Everything 404s through the edge but works direct.** Check `strip_path: false` on the route.
With `strip_path: true`, `/claims/adjudicate` reaches the upstream as `/adjudicate`.

**`503` through the edge while the upstream is healthy direct.** Kong (DB-less) resolves
upstream DNS at startup and caches it. If you recreate a service container it gets a new IP and
Kong keeps dialling the old one — a `401`→`503` pattern where the route and key clearly work but
nothing reaches the service. Restart the gateway:

```bash
docker compose restart kong    # note: this rotates the dev API key — re-read it
```

Seen in practice after `docker compose up -d --force-recreate claims-service`.

**A container is `running` but has no published port.** If compose failed to bind the port at
create time (something else held it — a stray `java -jar` on `:8090` is the classic), the
container can end up running *without* its mapping. `docker compose ps` shows an empty Ports
column. Free the port, then `docker compose up -d --force-recreate <service>`.

**PHI in gateway logs (⚠️ applies to Phase 1 today).** Kong's `file-log` records request URIs,
which contain patient and member identifiers. Treat gateway logs as **restricted**, or scrub
them (R14). This is a real, current exposure — not a Phase 2 concern.

## See also

- [`gateway/README.md`](../gateway/README.md) — Phase 1 KIC deploy procedures (the authority)
- [`plan.md` §3](./phase2/plan.md#3-gateway--localcloud-parity) — gateway design and parity rationale
- [`decisions.md`](./phase2/decisions.md) — C2 (DB-less everywhere), D4 (gateway placement)
- [`requirements.md` R11](./phase2/requirements.md) — gateway placement & internal isolation
