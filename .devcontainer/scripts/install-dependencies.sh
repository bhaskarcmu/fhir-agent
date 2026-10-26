#!/usr/bin/env bash
# Editable Python installs + Maven dependency warm-up.
# Runs as devcontainer.json's updateContentCommand, in Codespaces (including
# prebuilds, so startup stays fast) and in local Dev Containers.
set -euo pipefail
cd "$(dirname "$0")/../.."

python -m pip install --upgrade pip
python -m pip install \
  -e "client/clinical[dev]" -e "agent-platform[dev]" -e "triage-service[dev]" -e "mcp-agent[dev]" \
  -e "provider-registry-service[dev]" -e "provider-curation-agent[dev]" -e "provider-mcp-server[dev]" \
  -e "provider-search-agent[dev]" -e "outcome-prediction-service[dev,api]" -e "outcome-prediction-lab[dev]" \
  -e "outcome-prediction-agent[dev]"

cd fhir-service
./mvnw -q -DskipTests dependency:go-offline
