# Phase 8 reference-data archive — a private GCS bucket that mirrors the original MEPS files
# (docs/phase8/decisions.md O41). NOT YET APPLIED: this repo provisions no GCP credentials;
# CI runs `terraform validate` only, like every other module here. Apply steps:
# outcome-prediction-service/README.md, "Private mirror".
#
# A standalone root module (it declares its own provider), unlike the Phase 3 per-service
# stubs composed by infra/terraform: this archive is independent of any Phase 3b/8b
# deployment and is useful the moment it exists, so it can be applied on its own.
#
# What protects the data, and why there's no object versioning:
#   - private:     uniform bucket-level access, public access prevention ENFORCED, no
#                  allUsers/allAuthenticatedUsers bindings anywhere.
#   - immutable:   a retention policy — while it runs, an object can't be deleted OR
#                  overwritten by anyone. That is stronger than versioning (which keeps old
#                  copies of overwritten objects), so versioning would add cost and nothing else.
#                  Keys are content-addressed (meps/sha256/<sha>/<name>), so there is never a
#                  reason to overwrite one anyway.
#   - recoverable: soft delete keeps deleted objects restorable after retention expires.
#   - off-site:    the default location "US" is multi-region (geo-redundant) — the "1
#                  off-site copy" of 3-2-1, alongside AHRQ and each workspace's cache.
#   - least privilege: writers get objectCreator (create only: no read, no delete, no
#                  overwrite); readers get objectViewer.

terraform {
  required_providers {
    google = { source = "hashicorp/google", version = "~> 5.0" }
  }
}

provider "google" {
  project = var.project_id
}

variable "project_id" {
  type = string
}

variable "bucket_name" {
  type        = string
  default     = null
  description = "Globally unique bucket name; defaults to <project_id>-phase8-reference-data."
}

variable "location" {
  type        = string
  default     = "US"
  description = "Multi-region by default for geo-redundancy. A single region is cheaper but not off-site."
}

variable "retention_days" {
  type        = number
  default     = 3650
  description = "Objects can't be deleted or overwritten for this long after upload."
}

variable "lock_retention" {
  type        = bool
  default     = false
  description = <<-EOT
    IRREVERSIBLE. Locking makes the retention policy permanent: it can never be shortened or
    removed, and the bucket can't be deleted until every object has aged out. Leave false until
    the mirror has been verified; flip it as a deliberate, separate change.
  EOT
}

variable "reader_members" {
  type        = list(string)
  default     = []
  description = "IAM members allowed to read (e.g. user:alice@example.com, serviceAccount:ci@...)."
}

variable "writer_members" {
  type        = list(string)
  default     = []
  description = "IAM members allowed to upload new objects (create-only)."
}

locals {
  bucket_name = coalesce(var.bucket_name, "${var.project_id}-phase8-reference-data")
}

resource "google_storage_bucket" "reference_data" {
  name                        = local.bucket_name
  location                    = var.location
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  retention_policy {
    retention_period = var.retention_days * 86400
    is_locked        = var.lock_retention
  }

  soft_delete_policy {
    retention_duration_seconds = 7776000 # 90 days, the maximum
  }

  labels = {
    phase        = "8"
    contents     = "meps-public-use-files"
    contains_phi = "false"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_storage_bucket_iam_member" "readers" {
  for_each = toset(var.reader_members)
  bucket   = google_storage_bucket.reference_data.name
  role     = "roles/storage.objectViewer"
  member   = each.value
}

resource "google_storage_bucket_iam_member" "writers" {
  for_each = toset(var.writer_members)
  bucket   = google_storage_bucket.reference_data.name
  role     = "roles/storage.objectCreator"
  member   = each.value
}

output "bucket_name" {
  value = google_storage_bucket.reference_data.name
}

output "mirror_uri" {
  description = "Value for OUTCOME_PREDICTION_MEPS_MIRRORS."
  value       = "gs://${google_storage_bucket.reference_data.name}"
}
