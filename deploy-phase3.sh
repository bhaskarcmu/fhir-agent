#!/usr/bin/env bash
# deploy-phase3.sh — deploy Provider Search to Cloud Run via infra/terraform/ (Phase 3b).
#
# STUB — written and syntax-checked (`bash -n`) in M7, deliberately NOT executed. Phase 3b
# hasn't started (design.md §13.1); this is the script Phase 2 never built (its own
# deploy-phase2.sh was named in the plan but never written — docs/phase2/plan.md's
# "Cloud-delivery gap"). Real authoring work, not a placeholder: every step here is a real
# command against the actual root Terraform module and the actual per-service Dockerfiles,
# not sketched pseudocode.
#
# Deploys in order:
#   1. Build + push the three Phase 3 images (provider-registry-service, provider-mcp-server,
#      provider-ingest) to the shared Artifact Registry repo.
#   2. terraform init/plan/apply against infra/terraform/ (the root module, M7).
#   3. Reminds you to set the DATABASE_URL secret value out-of-band (never committed to
#      Terraform state or this script — see infra/terraform/main.tf's header comment).
#
# What this deliberately does NOT do: provider-curation-agent and provider-search-agent are
# run-once CLIs (like claims-agent) with no Cloud Run resource — they're built as images for
# local/CI use, not deployed as standing services. See infra/terraform/main.tf's closing
# comment.
#
# Prerequisites:
#   - gcloud authenticated (gcloud auth login) with PROJECT_ID set below or via env
#   - terraform installed (v1.5+)
#   - docker installed and authenticated to the target Artifact Registry
#     (gcloud auth configure-docker $REGION-docker.pkg.dev)
#   - The DATABASE_URL secret's VALUE set separately, after step 2 creates the secret
#     container:
#       echo -n "postgresql://..." | gcloud secrets versions add \
#         provider-registry-database-url --project="$PROJECT_ID" --data-file=-
#
# Usage:
#   PROJECT_ID=my-gcp-project REGION=us-central1 ./deploy-phase3.sh

set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID to your GCP project}"
REGION="${REGION:-us-central1}"
REPO="provider-search"
IMAGE_BASE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
echo "--- Pre-flight checks ---"

command -v gcloud > /dev/null 2>&1 || { echo "Error: gcloud is not installed." >&2; exit 1; }
command -v terraform > /dev/null 2>&1 || { echo "Error: terraform is not installed." >&2; exit 1; }
command -v docker > /dev/null 2>&1 || { echo "Error: docker is not installed." >&2; exit 1; }

gcloud config set project "$PROJECT_ID" > /dev/null

# ---------------------------------------------------------------------------
# 1. Terraform apply first -- creates the Artifact Registry repo the image
#    pushes below need to already exist.
# ---------------------------------------------------------------------------
echo "--- terraform apply (infra/terraform/) ---"
pushd infra/terraform > /dev/null
terraform init
terraform apply -var="project_id=${PROJECT_ID}" -var="region=${REGION}"
popd > /dev/null

# ---------------------------------------------------------------------------
# 2. Build + push images
# ---------------------------------------------------------------------------
echo "--- Building and pushing images to ${IMAGE_BASE} ---"

docker build -t "${IMAGE_BASE}/provider-registry-service:latest" \
  -f provider-registry-service/Dockerfile .
docker push "${IMAGE_BASE}/provider-registry-service:latest"

docker build -t "${IMAGE_BASE}/provider-mcp-server:latest" \
  -f provider-mcp-server/Dockerfile provider-mcp-server
docker push "${IMAGE_BASE}/provider-mcp-server:latest"

docker build -t "${IMAGE_BASE}/provider-ingest:latest" \
  -f data/scripts/provider_ingest/Dockerfile .
docker push "${IMAGE_BASE}/provider-ingest:latest"

# ---------------------------------------------------------------------------
# 3. Re-apply so Cloud Run picks up the freshly-pushed image digests
# ---------------------------------------------------------------------------
echo "--- terraform apply (picking up pushed images) ---"
pushd infra/terraform > /dev/null
terraform apply -var="project_id=${PROJECT_ID}" -var="region=${REGION}"
popd > /dev/null

cat <<EOF

--- Deploy complete ---

Next step (manual, not run by this script -- never commit a real connection string):
  echo -n "<your Neon connection string>" | gcloud secrets versions add \\
    provider-registry-database-url --project="$PROJECT_ID" --data-file=-

Then verify:
  gcloud run services describe provider-registry-service --region="$REGION" --project="$PROJECT_ID"
EOF
