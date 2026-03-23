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

## Known Limitations

- **Rate limiting uses `local` policy** — counters are per-pod. If Kong is
  scaled to multiple replicas, limits are not shared across pods. Add Redis
  and switch to `policy: redis` when scaling.
- **No TLS on the proxy** — TLS termination is expected to be handled by a
  GKE Ingress or Cloud Load Balancer in front of Kong. Do not expose the
  ClusterIP proxy directly without TLS in production.
- **test-client key is a placeholder** — replace `test-api-key-change-me`
  in `kong-consumers.yaml` with a strong random value before deploying:
  `openssl rand -hex 32`
