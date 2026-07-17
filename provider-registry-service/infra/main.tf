# Cloud Run config for provider-registry-service — STUB (design.md §13; not applied
# until Phase 3b). The point of this stub: the registry is INTERNAL-ONLY. It is
# reachable by provider-mcp-server over the VPC, never from the edge gateway or the
# public internet (design.md §9 — never on the Kong edge).
#
# design.md §13's callout applies here explicitly: this per-service stub existing does
# NOT by itself make Phase 3b "just a deploy" — see the root module note in that
# callout. This file only covers provider-registry-service's own Cloud Run service.

terraform {
  required_providers {
    google = { source = "hashicorp/google", version = "~> 5.0" }
  }
}

variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "image" {
  type = string # Artifact Registry image ref
}

variable "database_url_secret" {
  type        = string
  description = "Secret Manager secret name holding DATABASE_URL (Neon Postgres connection string)"
}

resource "google_cloud_run_v2_service" "provider_registry" {
  name     = "provider-registry-service"
  location = var.region

  # INTERNAL ingress = the Cloud Run equivalent of ClusterIP + NetworkPolicy, matching
  # rxclaim-emulator's precedent. Only VPC/internal callers (provider-mcp-server) can
  # reach it; no public URL.
  ingress = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    containers {
      image = var.image
      ports { container_port = 8002 }

      # DATABASE_URL comes from Secret Manager (R14-equivalent posture), not inline.
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = var.database_url_secret
            version = "latest"
          }
        }
      }

      startup_probe {
        http_get {
          path = "/health"
        }
      }
      liveness_probe {
        http_get {
          path = "/health"
        }
      }
    }
    scaling { min_instance_count = 0 } # stateless request/response -> scale to zero
  }
}

# No IAM binding grants allUsers. Only provider-mcp-server's service account may invoke:
resource "google_cloud_run_v2_service_iam_member" "invoker" {
  name     = google_cloud_run_v2_service.provider_registry.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:provider-mcp-server@${var.project_id}.iam.gserviceaccount.com"
}
