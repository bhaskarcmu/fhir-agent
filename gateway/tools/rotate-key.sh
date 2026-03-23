#!/usr/bin/env bash
# rotate-key.sh — zero-downtime quarterly API key rotation for a Kong consumer.
#
# Usage:
#   ./rotate-key.sh <username>
#
# Prerequisites:
#   - kubectl port-forward is running for the Kong Admin API:
#       kubectl port-forward svc/kong-kong-admin 8001:8001 -n kong
#   - curl and jq are installed locally.
#
# How zero-downtime rotation works:
#   1. A NEW key is generated and given to the client.
#   2. The client switches to the new key and confirms it works.
#   3. Only then is the OLD key deleted.
#   During step 2, both keys are valid simultaneously — no downtime.
#
# Run quarterly (every ~90 days) per consumer. Put a calendar reminder.
#
# Example:
#   ./rotate-key.sh mcp-agent

set -euo pipefail

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
# Check consumer exists
# ---------------------------------------------------------------------------
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  "${ADMIN_URL}/consumers/${USERNAME}")

if [[ "$HTTP_STATUS" == "404" ]]; then
  echo "Error: consumer '${USERNAME}' not found." >&2
  echo "Create it first: ./create-key.sh ${USERNAME}" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Step 1: List existing keys
# ---------------------------------------------------------------------------
echo ""
echo "Current keys for consumer '${USERNAME}':"
EXISTING_KEYS=$(curl -s "${ADMIN_URL}/consumers/${USERNAME}/key-auth")
echo "$EXISTING_KEYS" | jq -r '.data[] | "  ID: \(.id)  Created: \(.created_at | todate)  Key: \(.key[:8])..."'

KEY_COUNT=$(echo "$EXISTING_KEYS" | jq '.data | length')
if [[ "$KEY_COUNT" -eq 0 ]]; then
  echo "  (no keys found — use create-key.sh to provision a new key)"
  exit 1
fi

# Capture the IDs of all existing keys — these will be deleted after rotation
OLD_KEY_IDS=$(echo "$EXISTING_KEYS" | jq -r '.data[].id')

# ---------------------------------------------------------------------------
# Step 2: Generate new key
# ---------------------------------------------------------------------------
echo ""
echo "Generating new key for '${USERNAME}'..."
NEW_KEY_RESPONSE=$(curl -s -X POST "${ADMIN_URL}/consumers/${USERNAME}/key-auth")
NEW_KEY=$(echo "$NEW_KEY_RESPONSE" | jq -r '.key // empty')
NEW_KEY_ID=$(echo "$NEW_KEY_RESPONSE" | jq -r '.id // empty')

if [[ -z "$NEW_KEY" ]]; then
  echo "Error: failed to generate new key. Response:" >&2
  echo "$NEW_KEY_RESPONSE" >&2
  exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  NEW KEY GENERATED"
echo "  Consumer : ${USERNAME}"
echo "  New Key  : ${NEW_KEY}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Both the old and new keys are currently valid."
echo "  Store the new key in your password manager NOW before continuing."
echo ""

# ---------------------------------------------------------------------------
# Step 3: Wait for client confirmation
# ---------------------------------------------------------------------------
read -r -p "  Give the new key to the client and confirm it works. Press Enter to delete the old key(s)... "

# ---------------------------------------------------------------------------
# Step 4: Delete old keys
# ---------------------------------------------------------------------------
echo ""
echo "Deleting old key(s)..."
for OLD_ID in $OLD_KEY_IDS; do
  HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -X DELETE "${ADMIN_URL}/consumers/${USERNAME}/key-auth/${OLD_ID}")
  if [[ "$HTTP_STATUS" == "204" ]]; then
    echo "  Deleted key ID: ${OLD_ID}"
  else
    echo "  Warning: unexpected status ${HTTP_STATUS} deleting key ${OLD_ID}" >&2
  fi
done

# ---------------------------------------------------------------------------
# Step 5: Confirm final state
# ---------------------------------------------------------------------------
REMAINING=$(curl -s "${ADMIN_URL}/consumers/${USERNAME}/key-auth" \
  | jq '.data | length')

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Rotation complete for '${USERNAME}'"
echo "  Active keys: ${REMAINING}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Remind when to rotate next.
# python3 is used for date arithmetic — more portable than `date -d` (Linux)
# or `date -v` (macOS), both of which are unavailable in some environments.
NEXT_DATE=$(python3 -c \
  "from datetime import datetime, timedelta; \
   print((datetime.now() + timedelta(days=90)).strftime('%Y-%m-%d'))" \
  2>/dev/null || echo "in 90 days")
echo "  Next rotation due: ${NEXT_DATE}"
echo "  Add a calendar reminder now."
echo ""
