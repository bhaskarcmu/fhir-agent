#!/usr/bin/env bash
# generate.sh — Run Synthea locally to generate a synthetic patient population.
#
# Downloads the Synthea JAR on first run (~100MB, cached in data/synthea/).
# Requires Java 11+ (Java 21 is already in the devcontainer).
# Output lands in data/sample/fhir/ as FHIR R4 transaction bundles,
# one file per patient. load.py treats this output identically to
# the bundles produced by download_sample.sh.
#
# Usage:
#   ./data/scripts/generate.sh [options]
#
# Options:
#   -p COUNT    Number of patients to generate (default: 100)
#   -g GENDER   Gender filter: M or F (default: both)
#   -m MODULE   Clinical module to activate (repeatable, e.g. -m diabetes -m hypertension)
#   -s STATE    US state for demographics (default: Massachusetts)
#   -h          Show this help
#
# Examples:
#   ./data/scripts/generate.sh -p 100
#   ./data/scripts/generate.sh -p 50 -g F -m diabetes
#   ./data/scripts/generate.sh -p 200 -m diabetes -m hypertension -s California
#
# After running, load the data:
#   FHIR_BASE_URL=http://localhost:8080/fhir python3 data/scripts/load.py

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SYNTHEA_DIR="${REPO_ROOT}/data/synthea"
SAMPLE_DIR="${REPO_ROOT}/data/sample/fhir"
PROPERTIES_FILE="${SYNTHEA_DIR}/synthea.properties"

# Synthea release to use. Pin to a specific version for reproducibility.
SYNTHEA_VERSION="3.3.0"
SYNTHEA_JAR="${SYNTHEA_DIR}/synthea-${SYNTHEA_VERSION}.jar"
SYNTHEA_URL="https://github.com/synthetichealth/synthea/releases/download/v${SYNTHEA_VERSION}/synthea-with-dependencies.jar"

# ─────────────────────────────────────────────────────────────────────────────
# Defaults
# ─────────────────────────────────────────────────────────────────────────────
PATIENT_COUNT=100
GENDER=""
MODULES=()
STATE="Massachusetts"

# ─────────────────────────────────────────────────────────────────────────────
# Argument parsing
# ─────────────────────────────────────────────────────────────────────────────
usage() {
    sed -n '/^# Usage:/,/^[^#]/p' "$0" | grep '^#' | sed 's/^# \?//'
    exit 0
}

while getopts ":p:g:m:s:h" opt; do
    case ${opt} in
        p) PATIENT_COUNT="${OPTARG}" ;;
        g) GENDER="${OPTARG}" ;;
        m) MODULES+=("${OPTARG}") ;;
        s) STATE="${OPTARG}" ;;
        h) usage ;;
        :) echo "ERROR: Option -${OPTARG} requires an argument." >&2; exit 1 ;;
        \?) echo "ERROR: Unknown option -${OPTARG}" >&2; exit 1 ;;
    esac
done

# ─────────────────────────────────────────────────────────────────────────────
# Check dependencies
# ─────────────────────────────────────────────────────────────────────────────
if ! command -v java &>/dev/null; then
    echo "ERROR: Java is required but not found. Java 21 should be in the devcontainer." >&2
    exit 1
fi

JAVA_VERSION=$(java -version 2>&1 | awk -F '"' '/version/ {print $2}' | cut -d. -f1)
if [ "${JAVA_VERSION}" -lt 11 ]; then
    echo "ERROR: Java 11+ required. Found Java ${JAVA_VERSION}." >&2
    exit 1
fi

if ! command -v curl &>/dev/null; then
    echo "ERROR: curl is required to download the Synthea JAR." >&2
    exit 1
fi

# ─────────────────────────────────────────────────────────────────────────────
# Download Synthea JAR if not cached
# ─────────────────────────────────────────────────────────────────────────────
mkdir -p "${SYNTHEA_DIR}" "${SAMPLE_DIR}"

if [ ! -f "${SYNTHEA_JAR}" ]; then
    echo "Synthea JAR not found. Downloading v${SYNTHEA_VERSION} (~100MB) ..."
    curl -L --progress-bar -o "${SYNTHEA_JAR}" "${SYNTHEA_URL}"
    echo "Cached at ${SYNTHEA_JAR}"
    echo
else
    echo "Using cached Synthea JAR: ${SYNTHEA_JAR}"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Build Synthea arguments
# ─────────────────────────────────────────────────────────────────────────────
SYNTHEA_ARGS=(
    -jar "${SYNTHEA_JAR}"
    --exporter.baseDirectory="${SAMPLE_DIR}/../"   # synthea.properties sets the subdir
    -c "${PROPERTIES_FILE}"
    -p "${PATIENT_COUNT}"
)

if [ -n "${GENDER}" ]; then
    SYNTHEA_ARGS+=(-g "${GENDER}")
fi

for module in "${MODULES[@]+"${MODULES[@]}"}"; do
    SYNTHEA_ARGS+=(-m "${module}")
done

# State goes last as a positional argument
SYNTHEA_ARGS+=("${STATE}")

# ─────────────────────────────────────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────────────────────────────────────
echo "Generating ${PATIENT_COUNT} patient(s) — state: ${STATE}"
[ -n "${GENDER}" ]          && echo "  Gender  : ${GENDER}"
[ ${#MODULES[@]} -gt 0 ]    && echo "  Modules : ${MODULES[*]}"
echo "  Output  : ${SAMPLE_DIR}"
echo

cd "${REPO_ROOT}"
java "${SYNTHEA_ARGS[@]}"

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
BUNDLE_COUNT=$(find "${SAMPLE_DIR}" -name "*.json" | wc -l | tr -d ' ')
echo
echo "Done. ${BUNDLE_COUNT} bundle file(s) in ${SAMPLE_DIR}"
echo
echo "Next step — load into fhir-service:"
echo "  FHIR_BASE_URL=http://localhost:8080/fhir python3 data/scripts/load.py"
