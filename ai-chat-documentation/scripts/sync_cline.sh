#!/usr/bin/env bash
set -Eeuo pipefail

ARCHIVE_WORKTREE="/workspaces/.ai-chat-history"
ARCHIVE_ROOT="$ARCHIVE_WORKTREE/ai-chat-documentation"
LOG_DIR="$ARCHIVE_ROOT/logs"
LOCK_DIR="/tmp/cline-chat-sync.lock"

mkdir -p "$LOG_DIR"

log() {
    printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" \
        >> "$LOG_DIR/sync.log"
}

# Prevent overlapping runs.
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    exit 0
fi
trap 'rmdir "$LOCK_DIR"' EXIT

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
    printf 'Try: find "$HOME" -type d -path '\''*globalStorage*saoudrizwan.claude-dev/tasks'\'' 2>/dev/null\n' >&2
    exit 1
fi

log "Using Cline storage: $CLINE_TASKS"

python3 "$ARCHIVE_ROOT/scripts/export_cline.py" \
    --cline-tasks "$CLINE_TASKS" \
    --archive-root "$ARCHIVE_ROOT"

cd "$ARCHIVE_WORKTREE"

# Incorporate remote updates without generating a merge commit.
git pull --rebase --autostash origin ai-chat-history

git add ai-chat-documentation

if git diff --cached --quiet; then
    log "No archive changes."
    exit 0
fi

# A final staged-content check for common credentials.
if git diff --cached --no-ext-diff --unified=0 | grep -E \
    'sk-ant-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY' \
    >/dev/null
then
    git reset
    log "ERROR: Possible credential detected. Commit cancelled."
    printf 'Possible credential detected. Nothing was committed or pushed.\n' >&2
    exit 2
fi

git commit -m "Archive Cline conversations: $(date -u '+%Y-%m-%d %H:%M UTC')"
git push origin ai-chat-history

log "Archive committed and pushed successfully."
