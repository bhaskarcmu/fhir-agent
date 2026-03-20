#!/bin/bash
# Defensive setup of AI tools – logs all attempts but never exits with error

LOG_FILE="/workspaces/setup.log"
echo "=== Starting AI tool setup at $(date) ===" >> "$LOG_FILE"

# Ensure we are in the workspace
cd /workspaces || { echo "Could not cd to /workspaces" >> "$LOG_FILE"; exit 0; }

# 1. Claude Code configuration
if command -v claude &> /dev/null; then
    echo "Claude Code binary found." >> "$LOG_FILE"
    # Try to authenticate if API key is present
    if [ -n "$CLAUDE_API_KEY" ]; then
        mkdir -p ~/.claude
        echo "{\"apiKey\": \"$CLAUDE_API_KEY\"}" > ~/.claude/config.json
        echo "Claude Code API key written." >> "$LOG_FILE"
    else
        echo "No CLAUDE_API_KEY set, Claude will prompt later." >> "$LOG_FILE"
    fi
else
    echo "Claude Code not installed." >> "$LOG_FILE"
fi

# 2. Continue.dev configuration
mkdir -p .vscode
cat > .vscode/settings.json <<EOF
{
    "continue.models": [
        {
            "title": "Claude 3.5 Sonnet",
            "provider": "anthropic",
            "model": "claude-3-5-sonnet-20241022",
            "apiKey": "${CLAUDE_API_KEY}"
        }
    ],
    "continue.tabAutocompleteModel": {
        "title": "Claude 3.5 Sonnet",
        "provider": "anthropic",
        "model": "claude-3-5-sonnet-20241022",
        "apiKey": "${CLAUDE_API_KEY}"
    }
}
EOF
echo "Continue.dev settings written." >> "$LOG_FILE"

# 3. Roo Code configuration
mkdir -p ~/.roo-cline
cat > ~/.roo-cline/settings.json <<EOF
{
    "apiKey": "${CLAUDE_API_KEY}",
    "provider": "anthropic",
    "model": "claude-3-5-sonnet-20241022",
    "maxTokens": 4096,
    "temperature": 0.7
}
EOF
echo "Roo Code settings written." >> "$LOG_FILE"

# 4. GitHub Copilot CLI – test if gh extension is installed
if command -v gh &> /dev/null; then
    if gh extension list | grep -q copilot; then
        echo "GitHub Copilot CLI extension is installed." >> "$LOG_FILE"
    else
        echo "GitHub Copilot CLI extension not found. Attempting to install..." >> "$LOG_FILE"
        gh extension install github/gh-copilot 2>> "$LOG_FILE" || echo "Manual install failed" >> "$LOG_FILE"
    fi
else
    echo "GitHub CLI not installed, Copilot CLI unavailable." >> "$LOG_FILE"
fi

# 5. Summary of errors from Dockerfile (if any)
if [ -f /var/log/devcontainer/errors.log ]; then
    echo "=== Errors from Dockerfile build ===" >> "$LOG_FILE"
    cat /var/log/devcontainer/errors.log >> "$LOG_FILE"
fi

if [ -f /var/log/devcontainer/copilot.log ]; then
    echo "=== Copilot CLI installation attempts ===" >> "$LOG_FILE"
    cat /var/log/devcontainer/copilot.log >> "$LOG_FILE"
fi

echo "=== AI tool setup completed at $(date) ===" >> "$LOG_FILE"
