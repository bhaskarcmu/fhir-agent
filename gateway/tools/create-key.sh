#!/usr/bin/env bash
# create-key.sh — provision a new API consumer and key via Kong Admin API.
#
# Usage:
#   ./create-key.sh <username>
#
# Prerequisites:
#   - kubectl port-forward is running for the Kong Admin API:
#       kubectl port-forward svc/kong-kong-admin 8001:8001 -n kong
#   - curl and jq are installed locally.
#
# What it does:
#   1. Creates a KongConsumer with the given username (idempotent — safe to
#      re-run if the consumer already exists).
#   2. Generates a new API key for that consumer.
#   3. Prints the key — copy it and give it to the client.
#
# Example:
#   ./create-key.sh mcp-agent
#   → Consumer "mcp-agent" created.
#   → API key: a3f8c2e1d4b7...
#   → Test: curl -H "apikey: a3f8c2e1d4b7..." http://localhost:8000/fhir/metadata

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ADMIN_URL="${KONG_ADMIN_URL:-http://localhost:8001}"

# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <username>" >&2
  echo "Example: $0 mcp-agent" >&2
  exit 1
fi

USERNAME="$1"

# Validate: only alphanumeric, hyphens, underscores
if [[ ! "$USERNAME" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo "Error: username must contain only letters, numbers, hyphens, and underscores." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Check dependencies
# ---------------------------------------------------------------------------
for cmd in curl jq; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "Error: '$cmd' is required but not installed." >&2
    exit 1
  fi
done

# ---------------------------------------------------------------------------
# Check Admin API is reachable
# ---------------------------------------------------------------------------
if ! curl -sf "${ADMIN_URL}" -o /dev/null; then
  echo "Error: Kong Admin API not reachable at ${ADMIN_URL}" >&2
  echo "Run: kubectl port-forward svc/kong-kong-admin 8001:8001 -n kong" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Step 1: Create consumer (idempotent — 409 is fine)
# ---------------------------------------------------------------------------
echo "Creating consumer '${USERNAME}'..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${ADMIN_URL}/consumers" \
  -H "Content-Type: application/json" \
  -d "{\"username\": \"${USERNAME}\"}")

if [[ "$HTTP_STATUS" == "201" ]]; then
  echo "  Consumer '${USERNAME}' created."
elif [[ "$HTTP_STATUS" == "409" ]]; then
  echo "  Consumer '${USERNAME}' already exists — adding a new key."
else
  echo "Error: unexpected status ${HTTP_STATUS} when creating consumer." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Step 2: Generate an API key for the consumer
# ---------------------------------------------------------------------------
echo "Generating API key..."
RESPONSE=$(curl -s -X POST "${ADMIN_URL}/consumers/${USERNAME}/key-auth")

API_KEY=$(echo "$RESPONSE" | jq -r '.key // empty')

if [[ -z "$API_KEY" ]]; then
  echo "Error: failed to generate API key. Response:" >&2
  echo "$RESPONSE" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Consumer : ${USERNAME}"
echo "  API Key  : ${API_KEY}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Test (requires Kong proxy port-forward on 8000):"
echo "  kubectl port-forward svc/kong-kong-proxy 8000:80 -n kong"
echo "  curl -s -H \"apikey: ${API_KEY}\" http://localhost:8000/fhir/metadata | jq .resourceType"
echo ""
echo "Store this key securely — it cannot be retrieved again."
