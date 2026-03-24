# FHIR R4 Server

A standards-compliant, multi-database FHIR R4 server built on
[HAPI FHIR JPA 8.8.0](https://hapifhir.io). This is the **shared FHIR data layer**
for the agentic healthcare platform.

## Purpose

This module provides:
- **Generic FHIR R4 endpoints** for all resources (Patient, MedicationRequest, AllergyIntolerance, etc.)
- **Zero-config local development** with H2 in-memory database
- **Cloud deployment** with Neon serverless PostgreSQL
- **MCP tool targets** for the agentic orchestration layer (`mcp-agent`)

It is intentionally generic — **not EHR-specific**. Epic and Athena customizations
live in separate emulator modules (`epic-emulator/`, `athena-emulator/`).

## Integration with Platform

```
┌─────────────────┐
│   MCP Agent     │  ← Uses FHIR tools (get_patient, get_medications, etc.)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  FHIR Server    │  ← This module
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
   H2       Neon    (selectable via SPRING_PROFILES_ACTIVE)
```

## Database Profiles

| Profile | Database | Use Case | How to start |
|---------|----------|----------|--------------|
| default | H2 in-memory | Local development | `./mvnw spring-boot:run` |
| neon | Neon serverless PostgreSQL | Production / staging | `SPRING_PROFILES_ACTIVE=neon ./mvnw spring-boot:run` |

## Key Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /fhir/metadata` | FHIR CapabilityStatement (R4) |
| `POST /fhir/Patient` | Create a Patient resource |
| `GET /fhir/Patient/{id}` | Read a Patient resource |
| `GET /fhir/Patient?family=Smith` | Search patients by family name |
| `GET /actuator/health` | Health check (`{"status":"UP"}`) |

## Key Features

- **Optimistic locking** via `ETag` and `If-Match` headers (FHIR version-aware updates)
- **FHIR CapabilityStatement** at `GET /fhir/metadata`
- **Versioned profile URL fallback** (e.g., `Patient|4.0.1` → `Patient`)
- **Binary storage** — database (default) or filesystem
- **Master Data Management (MDM)** for patient matching (opt-in via `hapi.fhir.mdm_enabled=true`)
- **Custom interceptors and operations** via `hapi.fhir.custom-interceptor-classes` and `hapi.fhir.custom-provider-classes`

## Running Locally (H2)

```bash
cd fhir-service
./mvnw spring-boot:run
```

Server starts on `http://localhost:8080`. Verify with:

```bash
curl http://localhost:8080/actuator/health
curl http://localhost:8080/fhir/metadata
```

## Running with Neon (PostgreSQL)

Set the following environment variables (or store them as Ona project secrets):

```bash
export SPRING_DATASOURCE_URL="jdbc:postgresql://host/db?user=USER&password=PASS&sslmode=require"
export SPRING_DATASOURCE_DRIVER_CLASS_NAME="org.postgresql.Driver"
export SPRING_JPA_PROPERTIES_HIBERNATE_DIALECT="ca.uhn.fhir.jpa.model.dialect.HapiFhirPostgresDialect"
export HIBERNATE_DIALECT="ca.uhn.fhir.jpa.model.dialect.HapiFhirPostgresDialect"

SPRING_PROFILES_ACTIVE=neon ./mvnw spring-boot:run
```

Get your Neon connection string from the [Neon Dashboard](https://console.neon.tech) →
select your project → **Connection string** → choose **JDBC** format.

## Custom Extensions

### Custom Spring Beans

To auto-wire custom Spring beans (interceptors, operations, etc.) into the server:

1. Create your bean class in a custom package:

```java
package com.yourcompany.fhir.custom;

@Component
public class MyAuditInterceptor implements IServerInterceptor { ... }
```

2. Register the package in `application.yaml`:

```yaml
hapi:
  fhir:
    custom-bean-packages:
      - com.yourcompany.fhir.custom
```

3. Your beans are auto-discovered and wired by Spring on startup.

You can also register interceptors and operation providers by class name without
making them Spring beans:

```yaml
hapi:
  fhir:
    custom-interceptor-classes: com.yourcompany.fhir.custom.MyInterceptor
    custom-provider-classes: com.yourcompany.fhir.custom.MyOperation
```

See `CustomBeanTest`, `CustomInterceptorTest`, and `CustomOperationTest` for working examples.

## Relationship to Other Modules

| Module | Role |
|--------|------|
| `fhir-service` (this) | Generic FHIR R4 data layer — no EHR-specific behaviour |
| `epic-emulator` | Future: Epic-specific auth stubs, custom profiles, proprietary extensions |
| `athena-emulator` | Future: Athena-specific customizations |
| `triage-service` | Future: Drug-allergy risk evaluation business logic |
| `mcp-agent` | Future: LLM-powered orchestration using FHIR tools |

## Kubernetes Deployment

All manifests live in `fhir-service/k8s/`:

```
fhir-service/k8s/
├── namespace.yaml        — fhir namespace
├── configmap.yaml        — Spring profile, driver class, Hibernate dialect (non-secret)
├── secret.yaml.example   — template for Neon JDBC URL (real file gitignored)
├── service.yaml          — ClusterIP Service, name: fhir-service, port: 8080
└── deployment.yaml       — Deployment with probes, resource limits, security context
```

Once deployed, all traffic to `fhir-service` passes through the Kong API
gateway (`gateway/`) which enforces authentication and rate limiting.
See [`gateway/README.md`](../gateway/README.md) for the full gateway guide.

### Step 1 — Build the container image

```bash
# From the repo root
docker build -t fhir-service:latest fhir-service/
```

The build takes ~5 minutes on first run (Maven downloads ~500 MB of HAPI FHIR
dependencies). Subsequent builds with only source changes are fast — the
dependency layer is cached.

Verify the image starts locally (H2 profile, no env vars needed):

```bash
docker run --rm -p 8080:8080 fhir-service:latest
# Wait ~60s for HAPI FHIR schema init, then:
curl http://localhost:8080/actuator/health
# → {"status":"UP"}
```

### Step 2 — Push to a registry

#### Option A: GHCR (GitHub Container Registry — cloud-agnostic)

```bash
# Authenticate (once)
echo $GITHUB_TOKEN | docker login ghcr.io -u <github-username> --password-stdin

# Tag and push
IMAGE=ghcr.io/<github-org>/fhir-service:latest
docker tag fhir-service:latest ${IMAGE}
docker push ${IMAGE}
```

Make the package public (or configure an imagePullSecret) in GitHub →
your org → Packages → fhir-service → Package settings → Change visibility.

#### Option B: GCP Artifact Registry

```bash
# Create the repository once (if it doesn't exist)
gcloud artifacts repositories create fhir-agent \
  --repository-format=docker \
  --location=us-central1 \
  --project=<project-id>

# Authenticate Docker to Artifact Registry (once per machine)
gcloud auth configure-docker us-central1-docker.pkg.dev

# Tag and push
IMAGE=us-central1-docker.pkg.dev/<project-id>/fhir-agent/fhir-service:latest
docker tag fhir-service:latest ${IMAGE}
docker push ${IMAGE}
```

### Step 3 — Substitute the image in deployment.yaml

```bash
# Replace the IMAGE_PLACEHOLDER with your registry path
sed -i "s|IMAGE_PLACEHOLDER|${IMAGE}|g" fhir-service/k8s/deployment.yaml
```

> **Note:** `deployment.yaml` is committed with `IMAGE_PLACEHOLDER`. Run this
> `sed` substitution locally before applying — do not commit the substituted
> file (the image tag changes with every build).

### Step 4 — Apply manifests

```bash
# 1. Namespace (idempotent — safe to re-run)
kubectl apply -f fhir-service/k8s/namespace.yaml

# 2. Non-secret config
kubectl apply -f fhir-service/k8s/configmap.yaml -n fhir

# 3. Neon fhirdb credentials (never stored in the repo)
#    Get your JDBC URL: Neon Dashboard → project → Connection string → JDBC format
kubectl create secret generic fhir-service-secret \
  --namespace fhir \
  --from-literal=SPRING_DATASOURCE_URL="jdbc:postgresql://HOST/DB?user=USER&password=PASS&sslmode=require"

# 4. Service (must exist before Deployment so Kong can resolve it)
kubectl apply -f fhir-service/k8s/service.yaml -n fhir

# 5. Deployment
kubectl apply -f fhir-service/k8s/deployment.yaml -n fhir

# 6. Verify pod is running
kubectl get pods -n fhir
kubectl logs -f deployment/fhir-service -n fhir
```

Expected pod status after ~3 minutes:
```
NAME                            READY   STATUS    RESTARTS
fhir-service-<hash>             1/1     Running   0
```

### Step 5 — Apply Kong gateway resources

With `fhir-service` running, apply the Kong resources that route traffic to it:

```bash
kubectl apply -f gateway/kong/kong-plugins.yaml -n fhir
kubectl apply -f gateway/kong/kong-ingress.yaml -n fhir
```

Then provision your first API key (requires Kong Admin API port-forward):

```bash
kubectl port-forward svc/kong-kong-admin 8001:8001 -n kong
./gateway/tools/create-key.sh mcp-agent
```

See [`gateway/README.md`](../gateway/README.md) for the full Kong deployment
and key management guide.

### Health probes

| Probe | Path | Notes |
|---|---|---|
| Liveness | `GET /actuator/health/liveness` | Restarts pod if unhealthy |
| Readiness | `GET /actuator/health/readiness` | Removes pod from Service endpoints if unready |

Both probes have `initialDelaySeconds: 180` — HAPI FHIR runs schema migrations
and loads all FHIR R4 structure definitions on first boot. Against a remote Neon
database this takes approximately 3 minutes (validated on GKE).

### Resource sizing

| | Request | Limit |
|---|---|---|
| CPU | 250m | 1000m |
| Memory | 1Gi | 2Gi |

The JVM heap is capped at 75% of the memory limit (1.5Gi of 2Gi) via
`-XX:MaxRAMPercentage=75.0`. This is the validated minimum from actual GKE
deployment — the pod was OOMKilled at 1Gi during startup. Increase limits
if you enable Elasticsearch, MDM, or bulk import.

## Building and Testing

```bash
cd fhir-service
./mvnw clean verify        # build + all tests
./mvnw test                # tests only
./mvnw package -DskipTests # build only
```

Requires Java 21 and Maven 3.8+ (or use the included `./mvnw` wrapper).
