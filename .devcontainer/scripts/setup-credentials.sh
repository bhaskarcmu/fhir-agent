#!/bin/bash
# Configures AI tool credentials after the devcontainer starts.
# Runs as the postDevcontainerStart automation via .ona/automations.yaml.
# Logs all steps to /workspaces/setup.log. Never exits with error.
#
# SECURITY POLICY: this script never writes secret VALUES into files.
# The Claude key comes from the single Ona secret CLAUDE_API_KEY and is
# injected into the environment by .devcontainer/devcontainer.json:
#     "CLAUDE_API_KEY":    "${localEnv:CLAUDE_API_KEY}"
#     "ANTHROPIC_API_KEY": "${localEnv:CLAUDE_API_KEY}"
# so both names are available in the environment (RAM), not on disk. Tools that
# read the key from the environment (Claude Code CLI, the mcp-agent — which
# accepts ANTHROPIC_API_KEY or CLAUDE_API_KEY) need no per-tool config file.

LOG_FILE="/workspaces/setup.log"

echo "=== AI tool setup starting at $(date) ===" >> "$LOG_FILE"

# 1. Claude Code — reads ANTHROPIC_API_KEY from the environment.
# No file writes: devcontainer.json injects ANTHROPIC_API_KEY (and CLAUDE_API_KEY)
# from the CLAUDE_API_KEY Ona secret. If a shell does not see the value, rebuild
# the environment so containerEnv is re-applied — do NOT persist it to dotfiles.
if command -v claude &> /dev/null; then
    if [ -n "$CLAUDE_API_KEY" ] || [ -n "$ANTHROPIC_API_KEY" ]; then
        echo "Claude Code: key present in environment (no file written)" >> "$LOG_FILE"
    else
        echo "Claude Code: no key in environment; check the CLAUDE_API_KEY Ona secret" >> "$LOG_FILE"
    fi
else
    echo "Claude Code: binary not found" >> "$LOG_FILE"
fi

# 2. Continue.dev / Roo Code — GUI extensions.
# We deliberately do NOT write the key into any config file (previously this
# wrote it into the tracked .vscode/settings.json and ~/.roo-cline/settings.json).
# Configure these once via their in-editor UI, or point them at the
# ANTHROPIC_API_KEY environment variable. No secret is persisted to disk here.
echo "Continue.dev / Roo Code: skipping on-disk key write (configure via UI / env)" >> "$LOG_FILE"

# 3. GitHub CLI auth (repo access)
# GITHUB_TOKEN_REPO is a classic PAT with repo scope, used for gh CLI commands
# (gh pr, gh issue, etc.) and git operations. Kept separate from GH_TOKEN to
# avoid interfering with Copilot's fine-grained PAT requirements. The token is
# handed to gh's own credential store, not written to the repo or dotfiles.
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

# 4. GitHub Copilot CLI extension
# GH_TOKEN (fine-grained PAT with Copilot read permission) is scoped to the
# extension install command only — never passed to 'gh auth login', so it
# cannot overwrite the repo credentials configured in step 3 above.
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
