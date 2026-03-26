#!/usr/bin/env bash
# expunge.sh — Hard-purge all data from fhir-service.
#
# Calls HAPI FHIR's $expunge operation, which physically removes all rows
# from all internal tables: resources, history, search indexes, version
# counters, reference links. The database is left in the same state as a
# fresh server start.
#
# This is NOT a FHIR DELETE (which soft-deletes and retains history).
# This is a complete wipe. Use it when you want to reload from scratch.
#
# Requires expunge_enabled: true in fhir-service application.yaml.
# This is enabled by default for local and dev profiles. To disable in
# production, set the environment variable HAPI_FHIR_EXPUNGE_ENABLED=false
# when starting fhir-service.
#
# Environment variables:
#   FHIR_BASE_URL   Base URL of the FHIR server (required)
#   FHIR_API_KEY    Kong API key (omit for local H2)
#
# Usage:
#   # Local
#   FHIR_BASE_URL=http://localhost:8080/fhir ./data/scripts/expunge.sh
#
#   # Deployed (Neon via Kong)
#   FHIR_BASE_URL=http://<kong-ip>:8000/fhir \
#   FHIR_API_KEY=<your-key> \
#   ./data/scripts/expunge.sh
#
# Full reload workflow:
#   ./data/scripts/expunge.sh
#   ./data/scripts/generate.sh -p 100
#   FHIR_BASE_URL=http://localhost:8080/fhir python3 data/scripts/load.py

set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
FHIR_BASE_URL="${FHIR_BASE_URL:-}"
FHIR_API_KEY="${FHIR_API_KEY:-}"

if [ -z "${FHIR_BASE_URL}" ]; then
    echo "ERROR: FHIR_BASE_URL is not set." >&2
    echo "  Example: FHIR_BASE_URL=http://localhost:8080/fhir ./data/scripts/expunge.sh" >&2
    exit 1
fi

FHIR_BASE_URL="${FHIR_BASE_URL%/}"   # strip trailing slash
EXPUNGE_URL="${FHIR_BASE_URL}/\$expunge"

# ─────────────────────────────────────────────────────────────────────────────
# Check dependencies
# ─────────────────────────────────────────────────────────────────────────────
for cmd in curl python3; do
    if ! command -v "${cmd}" &>/dev/null; then
        echo "ERROR: '${cmd}' is required but not installed." >&2
        exit 1
    fi
done

# ─────────────────────────────────────────────────────────────────────────────
# Confirmation prompt
# ─────────────────────────────────────────────────────────────────────────────
echo "FHIR data expunge"
echo "  Server : ${FHIR_BASE_URL}"
echo "  Auth   : ${FHIR_API_KEY:+API key set}${FHIR_API_KEY:-none (local)}"
echo
echo "WARNING: This will permanently delete ALL data from the FHIR server."
echo "  Resources, history, search indexes, and reference links will be removed."
echo "  This cannot be undone."
echo
read -r -p "Type 'yes' to confirm: " confirm
if [ "${confirm}" != "yes" ]; then
    echo "Aborted."
    exit 0
fi
echo

# ─────────────────────────────────────────────────────────────────────────────
# Build curl arguments
# ─────────────────────────────────────────────────────────────────────────────
CURL_ARGS=(
    -s
    -X POST
    -H "Content-Type: application/fhir+json"
    -H "Accept: application/fhir+json"
    -w "\n%{http_code}"
    -d '{
      "resourceType": "Parameters",
      "parameter": [
        { "name": "expungeEverything", "valueBoolean": true }
      ]
    }'
)

if [ -n "${FHIR_API_KEY}" ]; then
    CURL_ARGS+=(-H "apikey: ${FHIR_API_KEY}")
fi

CURL_ARGS+=("${EXPUNGE_URL}")

# ─────────────────────────────────────────────────────────────────────────────
# Execute
# ─────────────────────────────────────────────────────────────────────────────
echo "Sending expunge request ..."
RESPONSE=$(curl "${CURL_ARGS[@]}")

# Last line is the HTTP status code (from -w "%{http_code}")
HTTP_STATUS=$(echo "${RESPONSE}" | tail -n1)
BODY=$(echo "${RESPONSE}" | head -n -1)

# ─────────────────────────────────────────────────────────────────────────────
# Evaluate response
# ─────────────────────────────────────────────────────────────────────────────
if [ "${HTTP_STATUS}" = "200" ]; then
    echo "Expunge complete (HTTP 200)."
    echo
    # Parse and display the count of expunged resources if present
    EXPUNGED=$(echo "${BODY}" | python3 -c "
import json, sys
try:
    body = json.load(sys.stdin)
    for p in body.get('parameter', []):
        if p.get('name') == 'count':
            print(f\"  Resources expunged: {p.get('valueInteger', 'unknown')}\")
            break
except Exception:
    pass
" 2>/dev/null || true)
    [ -n "${EXPUNGED}" ] && echo "${EXPUNGED}"
elif [ "${HTTP_STATUS}" = "404" ]; then
    echo "ERROR: \$expunge endpoint not found (HTTP 404)." >&2
    echo "  Ensure expunge_enabled: true is set in fhir-service/src/main/resources/application.yaml" >&2
    exit 1
elif [ "${HTTP_STATUS}" = "401" ]; then
    echo "ERROR: Authentication failed (HTTP 401). Check FHIR_API_KEY." >&2
    exit 1
else
    echo "ERROR: Unexpected response (HTTP ${HTTP_STATUS})." >&2
    echo "${BODY}" | python3 -m json.tool 2>/dev/null || echo "${BODY}" >&2
    exit 1
fi

# ─────────────────────────────────────────────────────────────────────────────
# Verify
# ─────────────────────────────────────────────────────────────────────────────
echo "Verifying ..."
VERIFY_ARGS=(-s -H "Accept: application/fhir+json")
[ -n "${FHIR_API_KEY}" ] && VERIFY_ARGS+=(-H "apikey: ${FHIR_API_KEY}")

PATIENT_COUNT=$(curl "${VERIFY_ARGS[@]}" \
    "${FHIR_BASE_URL}/Patient?_summary=count" | \
    python3 -c "import json,sys; print(json.load(sys.stdin).get('total', '?'))" 2>/dev/null || echo "?")

echo "  Patient count after expunge: ${PATIENT_COUNT}"
if [ "${PATIENT_COUNT}" = "0" ]; then
    echo "  Server is clean."
else
    echo "  WARNING: Expected 0 patients after expunge, got ${PATIENT_COUNT}."
    echo "  The server may need a moment to finish. Try querying again shortly."
fi

echo
echo "Ready to reload:"
echo "  ./data/scripts/generate.sh -p 100"
echo "  FHIR_BASE_URL=${FHIR_BASE_URL} python3 data/scripts/load.py"
