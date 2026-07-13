#!/usr/bin/env bash
set -u

SYNC_SCRIPT="/workspaces/.ai-chat-history/ai-chat-documentation/scripts/sync_cline.sh"
WATCH_LOG="/workspaces/.ai-chat-history/ai-chat-documentation/logs/watcher.log"

while true; do
    "$SYNC_SCRIPT" >> "$WATCH_LOG" 2>&1 || true
    sleep 300
done
