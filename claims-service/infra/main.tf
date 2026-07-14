# Cloud Run config for the claims-service — STUB (design/stub per D8; applied in Phase 2b).
# This is the EDGE-facing façade: reachable through the Kong gateway, and the only consumer of
# the internal rxclaim-emulator. It calls triage (reused) and, in M4+, the FHIR server.

terraform {
  required_providers {
    google = { source = "hashicorp/google", version = "~> 5.0" }
  }
}

variable "project_id" { type = string }
variable "region" { type = string, default = "us-central1" }
variable "image" { type = string }

resource "google_cloud_run_v2_service" "claims_service" {
  name     = "claims-service"
  location = var.region

  # Reachable via the gateway/load balancer (Kong fronts /claims). Not wide-open public:
  # front with Kong + Cloud Load Balancer; restrict direct ingress accordingly.
  ingress = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    service_account = "claims-service@${var.project_id}.iam.gserviceaccount.com"
    containers {
      image = var.image
      ports { container_port = 8090 }
      env {
        name  = "RXCLAIM_BASE-URL" # internal-only legacy core
        value = "https://rxclaim-emulator-internal.run.app"
      }
      env {
        name  = "TRIAGE_BASE-URL"
        value = "https://triage-internal.run.app"
      }
      env {
        name  = "PAYER-KB_DIR"
        value = "/kb" # mounted payer knowledge base
      }
      startup_probe { http_get { path = "/actuator/health/readiness" } }
      liveness_probe { http_get { path = "/actuator/health/liveness" } }
    }
    scaling { min_instance_count = 0 } # stateless request/response → scale to zero
  }
}
