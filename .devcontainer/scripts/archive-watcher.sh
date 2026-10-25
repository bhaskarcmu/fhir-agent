#!/usr/bin/env bash
# Keeps the AI chat archive watcher running: restores the ai-chat-history
# worktree if it is missing, runs its autostart.sh, and restarts it if it exits.
# Started detached by post-start.sh; a lock makes extra copies exit (after a
# short wait, since post-start.sh probes the same lock to see if one is running).
set -u
REPO="${ARCHIVE_SOURCE_WORKTREE:-/workspaces/fhir-agent}"
ARCHIVE="${ARCHIVE_WORKTREE:-/workspaces/.ai-chat-history}"
RETRY_SECONDS="${ARCHIVE_SUPERVISOR_RETRY_SECONDS:-30}"
LOCK_DIR="${XDG_RUNTIME_DIR:-/tmp}"

exec 9> "$LOCK_DIR/archive-watcher-supervisor.lock"
flock -w 5 9 || exit 0

WATCHER_LOCK="$ARCHIVE/ai-chat-documentation/logs/watcher.lock"

# True if watcher.lock names a running archive_ai process. A supervisor can be
# killed while its watcher survives; starting another beside it (autostart.sh
# also runs a sync) would put two processes on one git worktree at once.
watcher_alive() {
  local pid
  pid=$(head -1 "$WATCHER_LOCK" 2>/dev/null) || return 1
  [ -n "$pid" ] && grep -qa archive_ai "/proc/$pid/cmdline" 2>/dev/null
}

while true; do
  if watcher_alive; then
    sleep "$RETRY_SECONDS"
    continue
  fi
  # Any lock left now is stale (its PID may since have been reused).
  rm -f "$WATCHER_LOCK"
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
