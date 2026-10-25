#!/usr/bin/env bash
# Runs on every codespace start (devcontainer.json postStartCommand).
# Starts the local FHIR server and the AI chat archive watcher, both detached so
# the codespace is usable immediately. Codespaces has no service supervisor
# (unlike Ona), so archive-watcher.sh keeps the watcher alive itself.
# Logs go to /workspaces/setup.log.
#
# Codespaces only: Ona runs its own fhirServer / aiChatArchiveWatcher services
# (.ona/automations.yaml), and a second watcher there would fight the first.
[ "${CODESPACES:-}" = "true" ] || exit 0
LOG=/workspaces/setup.log
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SCRIPTS/../.." && pwd)"

echo "=== post-start $(date -u +%FT%TZ) ===" >> "$LOG"
mkdir -p "${CLAUDE_CONFIG_DIR:-/workspaces/.claude-home}"

# FHIR server (H2, in-memory). docker-in-docker's daemon may still be starting.
setsid nohup bash -c "
  for i in \$(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 2; done
  docker compose -f '$REPO/docker-compose.yml' up -d fhir \
    && echo 'FHIR: started (http://localhost:8080/fhir)' \
    || echo 'FHIR: docker compose up failed'
" >> "$LOG" 2>&1 < /dev/null &

setsid nohup bash "$SCRIPTS/archive-watcher.sh" >> "$LOG" 2>&1 < /dev/null &
