#!/usr/bin/env bash
# Keeps the AI chat archive watcher running: restores the ai-chat-history
# worktree if it is missing, runs its autostart.sh, and restarts it if it exits.
# Started detached by post-start.sh; a lock makes extra copies exit at once.
set -u
REPO="${ARCHIVE_SOURCE_WORKTREE:-/workspaces/fhir-agent}"
ARCHIVE="${ARCHIVE_WORKTREE:-/workspaces/.ai-chat-history}"
RETRY_SECONDS="${ARCHIVE_SUPERVISOR_RETRY_SECONDS:-30}"
LOCK_DIR="${XDG_RUNTIME_DIR:-/tmp}"

exec 9> "$LOCK_DIR/archive-watcher-supervisor.lock"
flock -n 9 || exit 0

# This supervisor is the only launcher, so any watcher.lock left over from before
# a restart is stale (and its PID may since have been reused by another process).
rm -f "$ARCHIVE/ai-chat-documentation/logs/watcher.lock"

while true; do
  if [ ! -e "$ARCHIVE/.git" ]; then
    git -C "$REPO" worktree prune
    if ! { git -C "$REPO" fetch -q origin ai-chat-history \
           && git -C "$REPO" worktree add -q "$ARCHIVE" ai-chat-history; }; then
      echo "[archive-watcher] $(date -u +%FT%TZ) worktree restore failed; retrying in ${RETRY_SECONDS}s"
      sleep "$RETRY_SECONDS"
      continue
    fi
  fi
  bash "$ARCHIVE/ai-chat-documentation/scripts/autostart.sh"
  rc=$?
  echo "[archive-watcher] $(date -u +%FT%TZ) watcher exited ($rc); restarting in ${RETRY_SECONDS}s"
  sleep "$RETRY_SECONDS"
done
