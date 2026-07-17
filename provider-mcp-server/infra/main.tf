# Cloud packaging stub for provider-mcp-server — STUB (design.md §13; not applied until
# Phase 3b). Deliberately NOT a google_cloud_run_v2_service resource.
#
# Why: this server speaks MCP over stdio — its transport IS the container's stdin/stdout
# when spawned as a local child process (design.md §8). Cloud Run's request model expects
# a container listening on $PORT and answering HTTP health checks; an stdio-only process
# has neither, and Cloud Run would kill it as unhealthy. Writing a
# google_cloud_run_v2_service resource here would `terraform validate` cleanly while being
# actively misleading about what's actually deployable — exactly the "stub exists" vs.
# "stub is deploy-ready" gap this design already calls out (§13's cloud-delivery-gap
# callout, decisions.md P8). So this file only provisions real packaging infrastructure
# (the container image target), not a service that can't actually serve this transport.
#
# What Phase 3b must actually decide before this server can run as a real Cloud Run
# service (design.md §13.1, not resolved here): switch transports. Verified real, not
# assumed: the installed `mcp` SDK (v1.28.1) already ships `mcp.server.sse`,
# `mcp.server.streamable_http`, and `mcp.server.websocket` alongside `mcp.server.stdio` --
# the protocol-level building blocks for a network-reachable transport exist today: this
# is an application-code decision (which transport, how the agent then reaches it), not a
# missing-SDK-feature blocker.

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

variable "repository_id" {
  type    = string
  default = "provider-search"
}

# The only real infra this milestone needs: somewhere to publish the built image so
# Phase 3b has a real artifact to point a (future, transport-resolved) Cloud Run
# resource at. No IAM invoker binding, no ingress setting -- there is no service yet.
resource "google_artifact_registry_repository" "provider_mcp_server" {
  location      = var.region
  repository_id = var.repository_id
  format        = "DOCKER"
  description   = "Provider Search container images, including provider-mcp-server (stdio-only until Phase 3b resolves transport)"
}
