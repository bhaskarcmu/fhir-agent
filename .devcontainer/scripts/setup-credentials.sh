#!/bin/bash
# setup-credentials.sh - Runs on container start to configure AI tools

echo "🔧 Setting up AI tooling credentials..."

# Claude Code configuration
if [ -n "$CLAUDE_API_KEY" ]; then
    mkdir -p ~/.claude
    echo "{\"apiKey\": \"$CLAUDE_API_KEY\"}" > ~/.claude/config.json
    echo "✅ Claude Code configured"
else
    echo "⚠️  CLAUDE_API_KEY not set. Claude Code will prompt for key on first use."
fi

# Continue.dev configuration (uses Claude API)
mkdir -p /workspaces/fhir-agentic-risk-triage/.vscode

cat > /workspaces/fhir-agentic-risk-triage/.vscode/settings.json << EOF
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

echo "✅ Continue.dev configured (using CLAUDE_API_KEY)"

# Roo Code configuration
if [ -n "$CLAUDE_API_KEY" ]; then
    # Roo Code stores config in ~/.roo-cline
    mkdir -p ~/.roo-cline
    cat > ~/.roo-cline/settings.json << EOF
{
    "apiKey": "${CLAUDE_API_KEY}",
    "provider": "anthropic",
    "model": "claude-3-5-sonnet-20241022",
    "maxTokens": 4096,
    "temperature": 0.7
}
EOF
    echo "✅ Roo Code configured"
else
    echo "⚠️  CLAUDE_API_KEY not set. Roo Code will prompt for API key on first use."
fi

# GitHub Copilot CLI configuration
if command -v copilot &> /dev/null; then
    echo "✅ GitHub Copilot CLI available"
fi

echo ""
echo "🎉 AI tooling setup complete!"
echo ""
echo "📋 Next steps:"
echo "   1. Ensure CLAUDE_API_KEY is set in Codespace secrets"
echo "   2. Open Command Palette → 'Continue: Login' (if prompted)"
echo "   3. GitHub Copilot should activate automatically"
echo "   4. Roo Code: Open Command Palette → 'Roo Code: Open in New Tab'"
echo ""
echo "🤖 Your AI Stack:"
echo "   - GitHub Copilot: Autocomplete + Chat"
echo "   - Claude Code: Terminal-based agent"
echo "   - Continue.dev: VS Code chat with Claude"
echo "   - Roo Code: Agentic task execution (autonomous coding)"
echo ""
echo "🔥 Roo Code is your agentic assistant - perfect for this project!"
echo "   It can:"
echo "   - Execute complex multi-step tasks"
echo "   - Create and edit files autonomously"
echo "   - Run terminal commands with approval"
echo "   - Review and refactor code"
