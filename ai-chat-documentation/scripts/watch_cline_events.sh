#!/usr/bin/env bash
set -Eeuo pipefail

# --- RETIRED: legacy Cline archiver -----------------------------------------
# Superseded by the archive_ai watcher (aiChatArchiveWatcher Ona service).
# This will not run unless explicitly re-enabled with CLINE_ARCHIVER_ENABLED=1.
if [ "${CLINE_ARCHIVER_ENABLED:-0}" != "1" ]; then
    echo "Legacy Cline archiver is retired. Set CLINE_ARCHIVER_ENABLED=1 to run." >&2
    exit 0
fi
# ----------------------------------------------------------------------------

ARCHIVE_ROOT="/workspaces/.ai-chat-history/ai-chat-documentation"
SYNC_SCRIPT="$ARCHIVE_ROOT/scripts/sync_cline.sh"
WATCH_LOG="$ARCHIVE_ROOT/logs/event-watcher.log"

# Allow Cline to finish a burst of related writes before exporting.
DEBOUNCE_SECONDS="${DEBOUNCE_SECONDS:-15}"

mkdir -p "$ARCHIVE_ROOT/logs"

log() {
    printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" \
        >> "$WATCH_LOG"
}

find_cline_tasks() {
    local candidate

    for candidate in \
        "$HOME/.config/Code/User/globalStorage/saoudrizwan.claude-dev/tasks" \
        "$HOME/.config/Code - OSS/User/globalStorage/saoudrizwan.claude-dev/tasks" \
        "$HOME/.local/share/code-server/User/globalStorage/saoudrizwan.claude-dev/tasks" \
        "$HOME/.vscode-server/data/User/globalStorage/saoudrizwan.claude-dev/tasks"
    do
        if [[ -d "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done

    find "$HOME" \
        -type d \
        -path '*/globalStorage/saoudrizwan.claude-dev/tasks' \
        -print \
        -quit \
        2>/dev/null
}

CLINE_TASKS="$(find_cline_tasks || true)"

if [[ -z "$CLINE_TASKS" || ! -d "$CLINE_TASKS" ]]; then
    log "ERROR: Could not locate Cline task storage."
    printf 'Could not locate Cline task storage.\n' >&2
    exit 1
fi

if ! command -v inotifywait >/dev/null 2>&1; then
    log "ERROR: inotifywait is not installed."
    printf 'inotifywait is not installed. Install inotify-tools first.\n' >&2
    exit 1
fi

log "Watching Cline task directory: $CLINE_TASKS"
log "Debounce interval: ${DEBOUNCE_SECONDS} seconds"

# Perform one initial synchronisation when the watcher starts.
if "$SYNC_SCRIPT" >> "$WATCH_LOG" 2>&1; then
    log "Initial synchronisation completed."
else
    log "WARNING: Initial synchronisation failed."
fi

while true; do
    # Wait until at least one relevant filesystem event occurs.
    changed_file="$(
        inotifywait \
            --recursive \
            --quiet \
            --event close_write \
            --event create \
            --event moved_to \
            --event moved_from \
            --event delete \
            --format '%w%f' \
            "$CLINE_TASKS"
    )"

    log "Detected change: $changed_file"

    # Debounce the burst. Continue waiting until the directory has been quiet
    # for the configured number of seconds.
    while inotifywait \
        --recursive \
        --quiet \
        --timeout "$DEBOUNCE_SECONDS" \
        --event close_write \
        --event create \
        --event moved_to \
        --event moved_from \
        --event delete \
        "$CLINE_TASKS" \
        >/dev/null 2>&1
    do
        log "Additional change detected; resetting debounce interval."
    done

    log "Change burst complete; running synchronisation."

    if "$SYNC_SCRIPT" >> "$WATCH_LOG" 2>&1; then
        log "Synchronisation completed."
    else
        log "ERROR: Synchronisation failed."
    fi
done
