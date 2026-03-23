# API Gateway — Kong

Kong Gateway (Apache 2.0) sits in front of `fhir-service` and enforces:

- **API key authentication** — every request must carry a valid `apikey` header
- **Rate limiting** — 10 requests/second per consumer (DoS protection)
- **Daily quota** — 1,000 requests/day per consumer

Kong is deployed to a dedicated `kong` namespace. The `fhir-service` runs in
the `fhir` namespace. Kong routes traffic between them via the Kong Ingress
Controller, which watches Kubernetes resources in the `fhir` namespace.

## Architecture

```
Client
  │
  │  HTTP + apikey header
  ▼
Kong Proxy (ClusterIP :80, namespace: kong)
  │
  │  key-auth plugin  → reject if no valid key (HTTP 401)
  │  rate-limit plugin → reject if over limit (HTTP 429)
  │
  ▼
fhir-service:8080 (namespace: fhir)
  │
  ▼
Neon PostgreSQL — fhirdb
```

Kong's own configuration (routes, consumers, plugins) is stored in a separate
Neon database (`kongdb`) — completely isolated from `fhirdb`.

## File Structure

```
gateway/
├── README.md                        ← this file
├── kong/
│   ├── kong-values.yaml             ← Helm values for Kong deployment
│   ├── kong-db-secret.yaml.example  ← Secret template (copy, fill, apply, delete)
│   ├── kong-plugins.yaml            ← KongPlugin: key-auth + rate-limiting
│   ├── kong-ingress.yaml            ← Ingress routing traffic to fhir-service
│   └── kong-consumers.yaml          ← test-client consumer + API key
└── tools/
    └── create-key.sh                ← dynamically provision new consumers/keys
```

---

## Prerequisites

- `kubectl` configured for your GKE cluster
- `helm` v3 installed
- `jq` installed (used by `create-key.sh`)
- The `fhir` and `kong` namespaces exist:
  ```bash
  kubectl create namespace kong
  kubectl create namespace fhir
  ```

---

## Step 1 — Create the Kong database Secret

The Neon `kongdb` credentials are never stored in the repo. Create the Secret
manually before deploying Kong.

```bash
# Copy the template
cp gateway/kong/kong-db-secret.yaml.example /tmp/kong-db-secret.yaml

# Fill in the base64-encoded values
NEON_HOST="ep-restless-resonance-amqcyrmq-pooler.c-5.us-east-1.aws.neon.tech"
NEON_USER="neondb_owner"
NEON_DB="kongdb"

kubectl create secret generic kong-db-secret \
  --namespace kong \
  --from-literal=pg_host="${NEON_HOST}" \
  --from-literal=pg_port="5432" \
  --from-literal=pg_database="${NEON_DB}" \
  --from-literal=pg_user="${NEON_USER}" \
  --from-literal=pg_password="<your-neon-password>"

# Verify
kubectl get secret kong-db-secret -n kong
```

---

## Step 2 — Install Kong via Helm

```bash
# Add the Kong Helm repo (once)
helm repo add kong https://charts.konghq.com
helm repo update

# Install Kong (runs migrations against kongdb automatically)
helm install kong kong/kong \
  --namespace kong \
  --version 3.1.0 \
  --values gateway/kong/kong-values.yaml \
  --wait

# Verify pods are running
kubectl get pods -n kong
```

Expected output:
```
NAME                        READY   STATUS    RESTARTS
kong-kong-<hash>            2/2     Running   0
kong-kong-init-migrations-* 0/1     Completed 0
```

---

## Step 3 — Apply Kong custom resources

```bash
# Apply plugins (key-auth + rate-limiting)
kubectl apply -f gateway/kong/kong-plugins.yaml -n fhir

# Apply the Ingress (routes /fhir/* to fhir-service)
kubectl apply -f gateway/kong/kong-ingress.yaml -n fhir

# Apply the test consumer and API key
kubectl apply -f gateway/kong/kong-consumers.yaml -n fhir
```

---

## Step 4 — Port-forward and test

Open two terminals:

**Terminal 1 — Kong proxy (incoming FHIR traffic):**
```bash
kubectl port-forward svc/kong-kong-proxy 8000:80 -n kong
```

**Terminal 2 — Kong Admin API (for create-key.sh):**
```bash
kubectl port-forward svc/kong-kong-admin 8001:8001 -n kong
```

### Test authentication

```bash
# Without API key — expect HTTP 401
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/fhir/metadata
# → 401

# With the test-client key — expect HTTP 200
curl -s -H "apikey: test-api-key-change-me" \
  http://localhost:8000/fhir/metadata | jq .resourceType
# → "CapabilityStatement"

# With a wrong key — expect HTTP 401
curl -s -o /dev/null -w "%{http_code}" \
  -H "apikey: wrong-key" http://localhost:8000/fhir/metadata
# → 401
```

### Test rate limiting

```bash
# Send 15 rapid requests — the 11th+ in the same second should return 429
for i in $(seq 1 15); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -H "apikey: test-api-key-change-me" \
    http://localhost:8000/fhir/metadata
done
# → 200 200 200 ... 429 429 429
```

Rate limit headers are returned on every response:
```
X-RateLimit-Limit-Second: 10
X-RateLimit-Remaining-Second: 9
X-RateLimit-Limit-Day: 1000
X-RateLimit-Remaining-Day: 999
```

---

## Provisioning new API keys

Use `create-key.sh` to onboard a new client (requires Admin API port-forward
on port 8001):

```bash
# Make executable (once)
chmod +x gateway/tools/create-key.sh

# Create a consumer and generate a key
./gateway/tools/create-key.sh mcp-agent

# Output:
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   Consumer : mcp-agent
#   API Key  : a3f8c2e1d4b7...
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Give the key to the client. It cannot be retrieved again — if lost, generate
a new one by running the script again (multiple keys per consumer are allowed).

---

## Revoking a key

```bash
# List all keys for a consumer
curl -s http://localhost:8001/consumers/mcp-agent/key-auth | jq '.data[].id'

# Delete a specific key by ID
curl -s -X DELETE http://localhost:8001/consumers/mcp-agent/key-auth/<key-id>
```

---

## Upgrading Kong

```bash
helm upgrade kong kong/kong \
  --namespace kong \
  --values gateway/kong/kong-values.yaml
```

Migrations run automatically as a pre-upgrade Helm hook.

---

---

## Kong Manager (web UI)

Kong Manager is a free web UI included in the open-source distribution.
It lets you view consumers, keys, plugins, routes, services, and upstreams
without memorising Admin API endpoints.

**Cost:** Zero. Apache 2.0 open-source, no license required.

**Access:**

```bash
kubectl port-forward svc/kong-kong-manager 8002:8002 -n kong
```

Then open in VS Code:
1. Press `Ctrl+Shift+P`
2. Type `Simple Browser: Show`
3. Enter `http://localhost:8002`

A browser panel opens inside VS Code. Alternatively, if working from your
local machine, open `http://localhost:8002` in any browser.

**What you can see in the UI:**

| Section | What it shows |
|---|---|
| Services | `fhir-service` upstream, URL, health |
| Routes | `/fhir` route, methods, plugins attached |
| Consumers | All API clients, creation dates |
| Credentials | Key IDs per consumer (not plaintext — by design) |
| Plugins | `key-auth`, `rate-limiting`, `file-log`, `prometheus` with configs |
| Upstreams | Health status of fhir-service pods |

**Note:** In Kong 3.x open-source, some edit operations in Manager are
read-only. Kong Inc. pushes editing toward their Konnect SaaS product.
All viewing and debugging functionality works fully. Use the Admin API
or `create-key.sh` / `rotate-key.sh` for write operations.

---

## Observability

### Rate limit usage — Neon SQL

Rate limit counters are written to `kongdb` on every request
(`policy: cluster`). Query them in the Neon Dashboard SQL editor:

```sql
-- Requests per consumer across all time windows
SELECT
  identifier  AS consumer_id,
  period_type AS window,
  value       AS request_count
FROM ratelimiting_metrics
ORDER BY period_type, value DESC;

-- Consumers approaching their daily quota (>80% of 1000)
SELECT identifier, value AS requests_today
FROM ratelimiting_metrics
WHERE period_type = 'day'
  AND value > 800
ORDER BY value DESC;

-- All consumers and their keys (for auditing)
SELECT
  c.username,
  k.id        AS key_id,
  k.created_at
FROM keyauth_credentials k
JOIN consumers c ON k.consumer_id = c.id
ORDER BY k.created_at DESC;
```

### Request logs — GKE Cloud Logging

The `fhir-request-log` plugin writes a JSON line to stdout for every
request. GKE captures stdout as structured logs in Cloud Logging.

Each log entry contains:
```json
{
  "consumer": { "username": "mcp-agent" },
  "request":  { "method": "GET", "uri": "/fhir/Patient/123", "size": 0 },
  "response": { "status": 200, "size": 4821, "latency": 142 },
  "started_at": 1711234567890
}
```

Query in GKE Cloud Logging:
```
resource.type="k8s_container"
resource.labels.container_name="proxy"
jsonPayload.consumer.username="mcp-agent"
jsonPayload.response.status=401
```

### Prometheus metrics

Kong exposes `/metrics` on port 8100. View raw metrics at any time:

```bash
kubectl port-forward svc/kong-kong-metrics 8100:8100 -n kong
curl http://localhost:8100/metrics | grep kong_http_requests
```

Key metrics:
```
kong_http_requests_total{consumer="mcp-agent",route="fhir",status="200"} 42
kong_latency_ms_bucket{type="request",le="100"} 38
kong_bandwidth_bytes{type="ingress",consumer="mcp-agent"} 18432
```

**Enabling Google Cloud Managed Prometheus (when ready):**
1. GKE Console → your cluster → **Features** → enable **Managed Prometheus**
2. That's it. The `ServiceMonitor` in `kong-values.yaml` is already declared
   and will be discovered automatically. No further configuration needed.

---

## Key management

### Provisioning a new consumer

```bash
# Port-forward Admin API (keep this terminal open)
kubectl port-forward svc/kong-kong-admin 8001:8001 -n kong

# Create consumer and generate key
./gateway/tools/create-key.sh mcp-agent
```

**Immediately store the printed key in a password manager.**
Kong stores only a hash — the plaintext is shown once and never again.

Suggested consumers for this platform:

| Consumer | Purpose |
|---|---|
| `mcp-agent` | LLM orchestration layer |
| `triage-service` | Drug-allergy risk evaluation service |
| `dev-local` | Local development and testing |

### Quarterly key rotation

```bash
./gateway/tools/rotate-key.sh mcp-agent
```

The script:
1. Lists existing keys with creation dates
2. Generates a new key and prints it
3. Pauses — give the new key to the client, wait for confirmation
4. Deletes the old key on Enter
5. Prints the next rotation due date (today + 90 days)

Both keys are valid during the transition window — zero downtime.

### Emergency key revocation

```bash
# Revoke a specific key by ID
KEY_ID=$(curl -s http://localhost:8001/consumers/mcp-agent/key-auth \
  | jq -r '.data[0].id')
curl -s -X DELETE http://localhost:8001/consumers/mcp-agent/key-auth/$KEY_ID
# → HTTP 204, key invalid immediately

# Revoke ALL keys for a consumer (full lockout)
curl -s -X DELETE http://localhost:8001/consumers/mcp-agent
# → Consumer and all keys deleted atomically
```

### Listing all consumers and keys

```bash
# Via Admin API
curl -s http://localhost:8001/consumers | jq '.data[] | {username, id}'
curl -s http://localhost:8001/consumers/mcp-agent/key-auth \
  | jq '.data[] | {id, created_at}'

# Via Neon SQL (kongdb)
-- SELECT c.username, k.id, k.created_at
-- FROM keyauth_credentials k JOIN consumers c ON k.consumer_id = c.id;
```

---

## Known Limitations

- **Rate limiting uses `cluster` policy** — one DB write to Neon per request.
  Accurate across restarts and replicas. Upgrade to `policy: redis` only
  when request volume makes Neon writes a bottleneck (thousands/sec).
- **No TLS on the proxy** — TLS termination is expected to be handled by a
  GKE Ingress or Cloud Load Balancer in front of Kong. Do not expose the
  ClusterIP proxy directly without TLS in production.
- **Kong Manager editing is partially read-only** in Kong 3.x open-source.
  Use Admin API or the provided scripts for write operations.
- **Prometheus metrics are declared but not scraped** until Google Cloud
  Managed Prometheus is enabled in GKE. The `/metrics` endpoint works
  immediately for manual inspection.
