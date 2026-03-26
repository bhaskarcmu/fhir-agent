#!/usr/bin/env bash
# download_sample.sh — Download pre-generated Synthea FHIR bundles.
#
# Pulls a ready-to-use patient population from the official Synthea sample
# data repository (synthetichealth/synthea-sample-data). No Java required.
# Output lands in data/sample/fhir/ in the same format as generate.sh,
# so load.py treats both sources identically.
#
# Usage:
#   ./data/scripts/download_sample.sh
#
# After running, load the data:
#   FHIR_BASE_URL=http://localhost:8080/fhir python3 data/scripts/load.py

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SAMPLE_DIR="${REPO_ROOT}/data/sample/fhir"
WORK_DIR="${REPO_ROOT}/data/sample"
ZIP_FILE="${WORK_DIR}/synthea-sample-data.zip"

echo "Synthea sample data download"
echo "  Target : ${SAMPLE_DIR}"
echo

# ─────────────────────────────────────────────────────────────────────────────
# Check dependencies
# ─────────────────────────────────────────────────────────────────────────────
for cmd in curl unzip; do
    if ! command -v "${cmd}" &>/dev/null; then
        echo "ERROR: '${cmd}' is required but not installed." >&2
        exit 1
    fi
done

# ─────────────────────────────────────────────────────────────────────────────
# Guard against overwriting existing data
# ─────────────────────────────────────────────────────────────────────────────
if [ -d "${SAMPLE_DIR}" ] && [ "$(ls -A "${SAMPLE_DIR}" 2>/dev/null)" ]; then
    echo "WARNING: ${SAMPLE_DIR} already contains files."
    echo "  Run expunge.sh first if you want a clean reload, or remove the"
    echo "  directory manually: rm -rf ${SAMPLE_DIR}"
    echo
    read -r -p "Continue and add to existing files? [y/N] " confirm
    if [[ ! "${confirm}" =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
fi

mkdir -p "${SAMPLE_DIR}"

# ─────────────────────────────────────────────────────────────────────────────
# Download
# ─────────────────────────────────────────────────────────────────────────────
DOWNLOAD_URL="https://github.com/synthetichealth/synthea-sample-data/archive/refs/heads/master.zip"

echo "Downloading from synthetichealth/synthea-sample-data ..."
curl -L --progress-bar -o "${ZIP_FILE}" "${DOWNLOAD_URL}"
echo

# ─────────────────────────────────────────────────────────────────────────────
# Extract FHIR R4 bundles only
# ─────────────────────────────────────────────────────────────────────────────
echo "Extracting FHIR R4 bundles ..."
# The archive contains output/fhir/ (R4) and output/fhir_stu3/ — we want R4 only.
unzip -q "${ZIP_FILE}" "synthea-sample-data-master/output/fhir/*" -d "${WORK_DIR}/tmp"

EXTRACTED="${WORK_DIR}/tmp/synthea-sample-data-master/output/fhir"
if [ ! -d "${EXTRACTED}" ]; then
    echo "ERROR: Expected FHIR output not found in archive at output/fhir/" >&2
    rm -rf "${WORK_DIR}/tmp" "${ZIP_FILE}"
    exit 1
fi

mv "${EXTRACTED}"/*.json "${SAMPLE_DIR}/" 2>/dev/null || true

# ─────────────────────────────────────────────────────────────────────────────
# Cleanup
# ─────────────────────────────────────────────────────────────────────────────
rm -rf "${WORK_DIR}/tmp" "${ZIP_FILE}"

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
BUNDLE_COUNT=$(find "${SAMPLE_DIR}" -name "*.json" | wc -l | tr -d ' ')
echo "Done. ${BUNDLE_COUNT} bundle files in ${SAMPLE_DIR}"
echo
echo "Next step — load into fhir-service:"
echo "  FHIR_BASE_URL=http://localhost:8080/fhir python3 data/scripts/load.py"
