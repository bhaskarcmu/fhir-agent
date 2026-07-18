# Root Terraform module for Phase 3 — STUB (design.md §13/§13.1; not applied until
# Phase 3b). This is the deliverable Phase 2 named but never built (docs/phase2/plan.md's
# "Cloud-delivery gap": "no root module to apply — the per-service stubs are unreferenced
# fragments"). Phase 3's milestone plan named this explicitly as its own M7 deliverable
# rather than an implied side-effect of per-service stubs (design.md §13's callout) —
# this file is that deliverable, not a repeat of the gap.
#
# Composes the three per-service stubs already built and individually `terraform
# validate`-d in M2/M3/M5, plus the pieces Phase 2's gap analysis named as missing
# (Artifact Registry, Secret Manager) and the wiring between them. Two things this
# deliberately does NOT provision, named rather than silently omitted:
#
#   - No Cloud SQL instance. Postgres is Neon (external SaaS), exactly matching how
#     fhir-service already handles it in Phase 1/2 (NEON_*/SPRING_DATASOURCE_URL env
#     vars, no Terraform-managed database resource anywhere in this repo — checked, not
#     assumed). The Secret Manager secret below holds the Neon connection string; the
#     value itself is set out-of-band (e.g. `gcloud secrets versions add`), same as how
#     NEON_* values are already handled for Phase 1/2 — never committed to Terraform state.
#   - No VPC connector. Neon is reached over its public endpoint with TLS, not a private
#     network path — a Serverless VPC Access connector is only needed to reach resources
#     inside a VPC (e.g. a private Cloud SQL instance), which doesn't apply here. Cloud
#     Run's `ingress = internal` on each service already provides the internal-only
#     reachability posture (design.md §9, §12.1) without one.
#
# provider-mcp-server is intentionally NOT composed as a Cloud Run Service here — see its
# own infra/main.tf (decisions.md P16): an stdio-only process has no $PORT listener, so a
# Cloud Run Service resource for it would validate cleanly while being undeployable.

terraform {
  required_providers {
    google = { source = "hashicorp/google", version = "~> 5.0" }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

# ── Shared secret — the Neon connection string, value set out-of-band ───────────────────
resource "google_secret_manager_secret" "database_url" {
  secret_id = "provider-registry-database-url"
  replication {
    auto {}
  }
}

# ── Compose the per-service stubs ────────────────────────────────────────────────────────
# provider-mcp-server's module owns the ONE shared Artifact Registry repo (it already
# declared one in M5); the other two modules' images publish into that same repo via its
# output, rather than each declaring — and potentially duplicating — their own. Composed
# first so its output is available to the other two.
module "provider_mcp_server" {
  source        = "../../provider-mcp-server/infra"
  project_id    = var.project_id
  region        = var.region
  repository_id = "provider-search"
}

locals {
  image_base = "${var.region}-docker.pkg.dev/${var.project_id}/${module.provider_mcp_server.repository_id}"
}

module "provider_registry_service" {
  source              = "../../provider-registry-service/infra"
  project_id          = var.project_id
  region              = var.region
  image               = "${local.image_base}/provider-registry-service:latest"
  database_url_secret = google_secret_manager_secret.database_url.secret_id
}

module "provider_ingest_job" {
  source              = "../../data/scripts/provider_ingest/infra"
  project_id          = var.project_id
  region              = var.region
  image               = "${local.image_base}/provider-ingest:latest"
  database_url_secret = google_secret_manager_secret.database_url.secret_id
  states              = "NC,CA,MT" # the full curated set (M3/M4), not the single-state default
}

# provider-curation-agent and provider-search-agent are run-once CLIs, like claims-agent —
# no Cloud Run resource for either (same reasoning as Phase 2's claims-agent, which also
# has no Cloud Run config). They're built as images (Dockerfiles exist) for local/CI use,
# not deployed as standing services.

output "artifact_registry_repository" {
  value = module.provider_mcp_server.repository_id
}

output "database_url_secret_id" {
  value = google_secret_manager_secret.database_url.secret_id
}
