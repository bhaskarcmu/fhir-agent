#!/bin/bash
# Configures AI tool credentials after the devcontainer starts.
# Runs as the postDevcontainerStart automation via .ona/automations.yaml.
# Logs all steps to /workspaces/setup.log. Never exits with error.

LOG_FILE="/workspaces/setup.log"
REPO_DIR="/workspaces/fhir-agent"

echo "=== AI tool setup starting at $(date) ===" >> "$LOG_FILE"

# 1. Claude Code
# Claude Code reads ANTHROPIC_API_KEY from the environment — it does NOT use
# ~/.claude/config.json. Ensure the variable is exported for interactive shells
# by writing it to ~/.bashrc and ~/.profile as a fallback in case the
# devcontainer containerEnv mapping doesn't propagate to all shell sessions.
if command -v claude &> /dev/null; then
    echo "Claude Code: found at $(which claude)" >> "$LOG_FILE"
    if [ -n "$CLAUDE_API_KEY" ]; then
        # /etc/environment is read before shell profiles and may contain a stale
        # empty value from the devcontainer containerEnv mapping. Fix it first.
        if grep -q "^ANTHROPIC_API_KEY=" /etc/environment 2>/dev/null; then
            sudo sed -i "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$CLAUDE_API_KEY|" /etc/environment
        else
            echo "ANTHROPIC_API_KEY=$CLAUDE_API_KEY" | sudo tee -a /etc/environment > /dev/null
        fi

        # Write to all shell profiles so interactive terminals pick it up
        for profile in ~/.bashrc ~/.profile ~/.zshrc ~/.zprofile; do
            touch "$profile"
            if ! grep -q "ANTHROPIC_API_KEY" "$profile" 2>/dev/null; then
                echo "export ANTHROPIC_API_KEY=\"$CLAUDE_API_KEY\"" >> "$profile"
            fi
        done
        # Also export for the current session
        export ANTHROPIC_API_KEY="$CLAUDE_API_KEY"
        echo "Claude Code: ANTHROPIC_API_KEY set in /etc/environment and shell profiles" >> "$LOG_FILE"
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

# 4. GitHub CLI auth (repo access)
# GITHUB_TOKEN_REPO is a classic PAT with repo scope, used for gh CLI commands
# (gh pr, gh issue, etc.) and git operations. Kept separate from GH_TOKEN to
# avoid interfering with Copilot's fine-grained PAT requirements.
if command -v gh &> /dev/null; then
    if [ -n "$GITHUB_TOKEN_REPO" ]; then
        echo "$GITHUB_TOKEN_REPO" | gh auth login --with-token 2>> "$LOG_FILE" \
            && echo "GitHub CLI: authenticated via GITHUB_TOKEN_REPO" >> "$LOG_FILE" \
            || echo "GitHub CLI: auth failed — check GITHUB_TOKEN_REPO secret" >> "$LOG_FILE"
    else
        echo "GitHub CLI: no GITHUB_TOKEN_REPO set — run 'gh auth login' manually" >> "$LOG_FILE"
    fi
else
    echo "GitHub CLI: gh not found" >> "$LOG_FILE"
fi

# 5. GitHub Copilot CLI extension
# GH_TOKEN (fine-grained PAT with Copilot read permission) is scoped to the
# extension install command only — never passed to 'gh auth login', so it
# cannot overwrite the repo credentials configured in step 4 above.
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
