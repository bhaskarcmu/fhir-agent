# Provider MCP server. Build context: provider-mcp-server/ (self-contained — it only
# calls provider-registry-service over HTTP at runtime, no shared code needed).
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .
# PROVIDER_REGISTRY_URL points at provider-registry-service (default http://localhost:8002).
# stdio transport — this container's stdin/stdout ARE the MCP transport when run
# interactively; see design.md §13.1 for why that limits this stub to cloud-*runnable*,
# not cloud-*callable*, until Phase 3b resolves the transport question for real.
ENTRYPOINT ["python", "-m", "provider_mcp"]
