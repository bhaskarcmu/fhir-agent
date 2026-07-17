# Provider search agent (run-once CLI). Build context: repo root -- this agent spawns
# provider-mcp-server as a local child process over stdio (design.md §8.2), so both
# packages need to be present in the same image (mirrors provider-curation-agent's
# repo-root-context pattern for a similar cross-package dependency).
FROM python:3.12-slim

WORKDIR /app

COPY provider-mcp-server/pyproject.toml /app/provider-mcp-server/pyproject.toml
COPY provider-mcp-server/src /app/provider-mcp-server/src
RUN pip install --no-cache-dir -e /app/provider-mcp-server

COPY provider-search-agent/pyproject.toml /app/provider-search-agent/pyproject.toml
COPY provider-search-agent/src /app/provider-search-agent/src
RUN pip install --no-cache-dir -e /app/provider-search-agent

WORKDIR /app

# ANTHROPIC_API_KEY/CLAUDE_API_KEY required -- this agent's job is NL decomposition,
# which has no deterministic fallback (decisions.md P18). PROVIDER_REGISTRY_URL is
# passed through to the spawned MCP server (default http://localhost:8002).
ENTRYPOINT ["python", "-m", "provider_search_agent"]
