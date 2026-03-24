#!/usr/bin/env bash
# deploy.sh — deploy the full fhir-agent stack to a GKE cluster.
#
# Deploys in order:
#   1. Kong API gateway (Helm, namespace: kong)
#   2. fhir-service (kubectl, namespace: fhir)
#   3. Kong plugins + ingress
#
# Prerequisites:
#   - kubectl configured for your GKE cluster (gcloud container clusters get-credentials)
#   - helm installed (v3+)
#   - Kubernetes secrets already created:
#       kubectl create secret generic kong-db-secret --namespace kong \
#         --from-literal=pg_host=... --from-literal=pg_port=5432 \
#         --from-literal=pg_database=kongdb --from-literal=pg_user=neondb_owner \
#         --from-literal=pg_password="endpoint=<endpoint-id>;<password>"
#       kubectl create secret generic fhir-service-secret --namespace fhir \
#         --from-literal=SPRING_DATASOURCE_URL="jdbc:postgresql://HOST/fhirdb?user=USER&password=PASS&sslmode=require"
#   - IMAGE variable set to your registry path (see below)
#
# Usage:
#   IMAGE=ghcr.io/bhaskarcmu/fhir-service:latest ./deploy.sh
#
# To run smoke tests after deployment:
#   kubectl port-forward svc/kong-kong-proxy 8000:80 -n kong &
#   kubectl port-forward svc/kong-kong-admin 8001:8001 -n kong &
#   ./gateway/tools/create-key.sh test-client   # save the printed key
#   FHIR_GATEWAY_URL=http://localhost:8000 FHIR_API_KEY=<key> python3 fhir-service/tests/smoke_test.py

set -euo pipefail

IMAGE="${IMAGE:-}"
if [[ -z "$IMAGE" ]]; then
  echo "Error: IMAGE environment variable is required." >&2
  echo "Usage: IMAGE=ghcr.io/<org>/fhir-service:latest ./deploy.sh" >&2
  exit 1
fi

echo "=== fhir-agent deploy ==="
echo "  Image: ${IMAGE}"
echo ""

# ---------------------------------------------------------------------------
# Step 1: Namespaces
# ---------------------------------------------------------------------------
echo "--- Step 1: Namespaces ---"
kubectl apply -f fhir-service/k8s/namespace.yaml
kubectl create namespace kong --dry-run=client -o yaml | kubectl apply -f -
echo ""

# ---------------------------------------------------------------------------
# Step 2: Kong via Helm
# ---------------------------------------------------------------------------
echo "--- Step 2: Kong (Helm install) ---"
helm repo add kong https://charts.konghq.com --force-update
helm repo update
helm upgrade --install kong kong/kong \
  --namespace kong \
  --version 3.1.0 \
  --values gateway/kong/kong-values.yaml \
  --timeout 300s
echo ""

# ---------------------------------------------------------------------------
# Step 3: Wait for Kong migrations and pod
# ---------------------------------------------------------------------------
echo "--- Step 3: Waiting for Kong ---"
kubectl wait --for=condition=complete job/kong-kong-init-migrations \
  -n kong --timeout=180s
kubectl wait --for=condition=ready pod -l app=kong-kong \
  -n kong --timeout=120s
echo "  Kong is ready."
echo ""

# ---------------------------------------------------------------------------
# Step 4: fhir-service
# ---------------------------------------------------------------------------
echo "--- Step 4: fhir-service ---"
kubectl apply -f fhir-service/k8s/configmap.yaml -n fhir
kubectl apply -f fhir-service/k8s/service.yaml -n fhir
# Substitute IMAGE_PLACEHOLDER in-memory — never modifies the committed file
sed "s|IMAGE_PLACEHOLDER|${IMAGE}|g" fhir-service/k8s/deployment.yaml \
  | kubectl apply -f - -n fhir
echo ""

# ---------------------------------------------------------------------------
# Step 5: Wait for fhir-service
# ---------------------------------------------------------------------------
echo "--- Step 5: Waiting for fhir-service (HAPI FHIR schema migration ~3min) ---"
kubectl wait --for=condition=ready pod -l app=fhir-service \
  -n fhir --timeout=360s
echo "  fhir-service is ready."
echo ""

# ---------------------------------------------------------------------------
# Step 6: Kong plugins + ingress
# ---------------------------------------------------------------------------
echo "--- Step 6: Kong plugins and ingress ---"
kubectl apply -f gateway/kong/kong-plugins.yaml -n fhir
kubectl apply -f gateway/kong/kong-ingress.yaml -n fhir
echo ""

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo "=== Deploy complete ==="
echo ""
echo "Next steps:"
echo "  1. Port-forward Kong proxy:"
echo "       kubectl port-forward svc/kong-kong-proxy 8000:80 -n kong"
echo ""
echo "  2. Port-forward Kong Admin API:"
echo "       kubectl port-forward svc/kong-kong-admin 8001:8001 -n kong"
echo ""
echo "  3. Provision your first API key:"
echo "       ./gateway/tools/create-key.sh mcp-agent"
echo ""
echo "  4. Run smoke tests:"
echo "       FHIR_GATEWAY_URL=http://localhost:8000 FHIR_API_KEY=<key> \\"
echo "         python3 fhir-service/tests/smoke_test.py"
