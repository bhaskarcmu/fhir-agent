# Cloud Run Job config for the provider ingestion pipeline — STUB (design.md §13;
# not applied until Phase 3b). Matches the "manually re-run, one-time-per-state
# seed" decision (PRD §6 Freshness) — this is a manually-triggered Job, not a
# scheduled service. Where a live weekly refresh would fit later (Cloud Scheduler
# -> this same Job) is noted in design.md §6, not built now.
#
# Writes directly to provider-registry-service's Postgres (design.md §6, decision
# P10) — no HTTP call to the service itself, so this Job's only network dependency
# besides the database is the public NPPES/NUCC/Census sources it fetches from.

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
  type = string # Artifact Registry image ref (data/scripts/provider_ingest/, packaged with a Dockerfile)
}

variable "database_url_secret" {
  type        = string
  description = "Secret Manager secret name holding DATABASE_URL (Neon Postgres connection string)"
}

variable "states" {
  type        = string
  default     = "NC"
  description = "Comma-separated state codes to ingest, e.g. NC or NC,CA,MT"
}

resource "google_cloud_run_v2_job" "provider_ingest" {
  name     = "provider-ingest"
  location = var.region

  template {
    template {
      containers {
        image = var.image
        args  = ["--states", var.states]

        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = var.database_url_secret
              version = "latest"
            }
          }
        }
      }
      # One-shot batch job, not a long-running service -- no min/max instance
      # scaling knobs to set; a manual `gcloud run jobs execute` per re-run.
      max_retries = 1
    }
  }
}

# No public invoker. Triggered manually (`gcloud run jobs execute provider-ingest`)
# or, later, by Cloud Scheduler -- not built this milestone (design.md §6).
