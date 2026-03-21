#!/bin/bash
# Configures AI tool credentials after the devcontainer starts.
# Runs as the postDevcontainerStart automation via .ona/automations.yaml.
# Logs all steps to /workspaces/setup.log. Never exits with error.

LOG_FILE="/workspaces/setup.log"
REPO_DIR="/workspaces/fhir-agent"

echo "=== AI tool setup starting at $(date) ===" >> "$LOG_FILE"

# 1. Claude Code
if command -v claude &> /dev/null; then
    echo "Claude Code: found at $(which claude)" >> "$LOG_FILE"
    if [ -n "$CLAUDE_API_KEY" ]; then
        mkdir -p ~/.claude
        printf '{"apiKey": "%s"}\n' "$CLAUDE_API_KEY" > ~/.claude/config.json
        echo "Claude Code: API key written" >> "$LOG_FILE"
    else
        echo "Claude Code: no CLAUDE_API_KEY set, will prompt on first use" >> "$LOG_FILE"
    fi
else
    echo "Claude Code: binary not found" >> "$LOG_FILE"
fi

# 2. Continue.dev — written into the repo's .vscode directory
# Unquoted heredoc delimiter so shell variables expand correctly
if [ -n "$CLAUDE_API_KEY" ]; then
    mkdir -p "$REPO_DIR/.vscode"
    cat > "$REPO_DIR/.vscode/settings.json" << EOF
{
    "continue.models": [
        {
            "title": "Claude 3.5 Sonnet",
            "provider": "anthropic",
            "model": "claude-3-5-sonnet-20241022",
            "apiKey": "$CLAUDE_API_KEY"
        }
    ],
    "continue.tabAutocompleteModel": {
        "title": "Claude 3.5 Sonnet",
        "provider": "anthropic",
        "model": "claude-3-5-sonnet-20241022",
        "apiKey": "$CLAUDE_API_KEY"
    }
}
EOF
    echo "Continue.dev: settings written to $REPO_DIR/.vscode/settings.json" >> "$LOG_FILE"
else
    echo "Continue.dev: no CLAUDE_API_KEY set, skipping" >> "$LOG_FILE"
fi

# 3. Roo Code
if [ -n "$CLAUDE_API_KEY" ]; then
    mkdir -p ~/.roo-cline
    cat > ~/.roo-cline/settings.json << EOF
{
    "apiKey": "$CLAUDE_API_KEY",
    "provider": "anthropic",
    "model": "claude-3-5-sonnet-20241022",
    "maxTokens": 4096,
    "temperature": 0.7
}
EOF
    echo "Roo Code: settings written" >> "$LOG_FILE"
else
    echo "Roo Code: no CLAUDE_API_KEY set, skipping" >> "$LOG_FILE"
fi

# 4. GitHub Copilot CLI extension
# GH_TOKEN (fine-grained PAT with Copilot read permission) is used only to
# install the extension. It is passed as an environment variable scoped to
# that single command and never passed to 'gh auth login', so it cannot
# overwrite the git repo credentials configured separately via gh auth.
if command -v gh &> /dev/null; then
    if gh extension list 2>/dev/null | grep -q "github/gh-copilot"; then
        echo "GitHub Copilot CLI: already installed" >> "$LOG_FILE"
    else
        echo "GitHub Copilot CLI: installing extension..." >> "$LOG_FILE"
        if [ -n "$GH_TOKEN" ]; then
            GITHUB_TOKEN="$GH_TOKEN" gh extension install github/gh-copilot 2>> "$LOG_FILE" \
                && echo "GitHub Copilot CLI: installed" >> "$LOG_FILE" \
                || echo "GitHub Copilot CLI: install failed" >> "$LOG_FILE"
        else
            gh extension install github/gh-copilot 2>> "$LOG_FILE" \
                && echo "GitHub Copilot CLI: installed" >> "$LOG_FILE" \
                || echo "GitHub Copilot CLI: install failed (no GH_TOKEN set)" >> "$LOG_FILE"
        fi
    fi
else
    echo "GitHub Copilot CLI: gh not found" >> "$LOG_FILE"
fi

echo "=== AI tool setup completed at $(date) ===" >> "$LOG_FILE"
