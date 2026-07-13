#!/usr/bin/env bash
set -u

# --- RETIRED: legacy Cline archiver -----------------------------------------
# Superseded by the archive_ai watcher (aiChatArchiveWatcher Ona service).
# This will not run unless explicitly re-enabled with CLINE_ARCHIVER_ENABLED=1.
if [ "${CLINE_ARCHIVER_ENABLED:-0}" != "1" ]; then
    echo "Legacy Cline archiver is retired. Set CLINE_ARCHIVER_ENABLED=1 to run." >&2
    exit 0
fi
# ----------------------------------------------------------------------------

SYNC_SCRIPT="/workspaces/.ai-chat-history/ai-chat-documentation/scripts/sync_cline.sh"
WATCH_LOG="/workspaces/.ai-chat-history/ai-chat-documentation/logs/watcher.log"

while true; do
    "$SYNC_SCRIPT" >> "$WATCH_LOG" 2>&1 || true
    sleep 300
done
