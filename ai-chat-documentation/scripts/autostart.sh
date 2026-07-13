#!/usr/bin/env bash
# Auto-start the AI Conversation Archive watcher under Ona service supervision.
#
# Runs a one-shot startup sync (to archive anything written while the workspace
# was down), then hands off to the event-driven watcher in the FOREGROUND so
# that Ona's service supervisor keeps it alive and restarts it on crash. The
# watcher's own lock file prevents duplicate instances.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR"
LOG_DIR="$SCRIPT_DIR/../logs"
mkdir -p "$LOG_DIR"

echo "[autostart] $(date -u +%FT%TZ) starting archive watcher" >> "$LOG_DIR/watcher.log"

# Startup catch-up. Never fail the service if this errors — the watcher retries.
python3 -m archive_ai sync >> "$LOG_DIR/sync.log" 2>&1 \
  || echo "[autostart] startup sync failed; watcher will retry" >> "$LOG_DIR/sync.log"

# Foreground watcher; exec so Ona supervises this process directly.
exec python3 -m archive_ai watch >> "$LOG_DIR/watcher.log" 2>&1
