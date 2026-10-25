#!/usr/bin/env bash
# Starts the local FHIR server and the AI chat archive watcher, both detached so
# the codespace is usable immediately. Codespaces has no service supervisor
# (unlike Ona), so archive-watcher.sh keeps the watcher alive itself.
# Logs go to /workspaces/setup.log.
#
# Idempotent, and run from three places: postStartCommand, postAttachCommand and
# every interactive shell (/etc/bash.bashrc, see Dockerfile). Jobs started from
# the lifecycle commands can be killed when the command returns, so the later
# runs restart whatever did not survive; when everything is up this is a no-op.
#
# To keep FHIR stopped (e.g. after `docker compose down`), create
# /workspaces/.no-fhir-autostart; delete it to resume auto-start.
#
# Codespaces only: Ona runs its own fhirServer / aiChatArchiveWatcher services
# (.ona/automations.yaml), and a second watcher there would fight the first.
[ "${CODESPACES:-}" = "true" ] || exit 0
LOG="${SETUP_LOG:-/workspaces/setup.log}"
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SCRIPTS/../.." && pwd)"
TAG="post-start(${1:-manual})"
mkdir -p "${CLAUDE_CONFIG_DIR:-/workspaces/.claude-home}"

# FHIR server (H2, in-memory). docker-in-docker's daemon may still be starting.
if [ ! -e /workspaces/.no-fhir-autostart ] \
   && [ -z "$(docker ps -q --filter name=fhir-agent-fhir --filter status=running 2>/dev/null)" ]; then
  echo "[$TAG] $(date -u +%FT%TZ) FHIR: starting" >> "$LOG"
  setsid nohup bash -c "
    for i in \$(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 2; done
    docker compose -f '$REPO/docker-compose.yml' up -d fhir \
      && echo 'FHIR: started (http://localhost:8080/fhir)' \
      || echo 'FHIR: docker compose up failed'
  " >> "$LOG" 2>&1 < /dev/null &
fi

# The supervisor holds this lock while it runs (see archive-watcher.sh).
# The watcher signs and pushes commits, which needs the Codespaces GitHub token.
# The devcontainer CLI's user-env probe runs an interactive shell (so the
# bash.bashrc hook) before that token exists; a watcher started there can never
# commit, so leave it to a later run that has the token.
if [ -n "${GITHUB_TOKEN:-}" ] && flock -n "${XDG_RUNTIME_DIR:-/tmp}/archive-watcher-supervisor.lock" true; then
  echo "[$TAG] $(date -u +%FT%TZ) archive watcher: starting" >> "$LOG"
  setsid nohup bash "$SCRIPTS/archive-watcher.sh" >> "$LOG" 2>&1 < /dev/null &
fi
