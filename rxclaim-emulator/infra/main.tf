# Cloud Run config for the rxclaim-emulator — STUB (design/stub per D8; not applied until Phase 2b).
# The point of this stub: the legacy core is INTERNAL-ONLY. It is reachable by claims-service
# over the VPC, never from the edge gateway or the public internet.

terraform {
  required_providers {
    google = { source = "hashicorp/google", version = "~> 5.0" }
  }
}

variable "project_id" { type = string }
variable "region" { type = string, default = "us-central1" }
variable "image" { type = string } # Artifact Registry image ref

resource "google_cloud_run_v2_service" "rxclaim_emulator" {
  name     = "rxclaim-emulator"
  location = var.region

  # INTERNAL ingress = the Cloud Run equivalent of ClusterIP + NetworkPolicy (plan C1/R11).
  # Only VPC/internal callers (claims-service) can reach it; no public URL.
  ingress = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    containers {
      image = var.image
      ports { container_port = 8091 }
      # DB: in cloud, SPRING_DATASOURCE_URL points at the emulator's own Cloud SQL/Neon
      # (Db2-for-i stand-in). Secrets come from Secret Manager (R14), not inline.
      startup_probe { http_get { path = "/actuator/health/readiness" } }
      liveness_probe { http_get { path = "/actuator/health/liveness" } }
    }
    scaling { min_instance_count = 0 } # stateless request/response → scale to zero
  }
}

# No IAM binding grants allUsers. Only the claims-service service account may invoke:
resource "google_cloud_run_v2_service_iam_member" "invoker" {
  name     = google_cloud_run_v2_service.rxclaim_emulator.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:claims-service@${var.project_id}.iam.gserviceaccount.com"
}
