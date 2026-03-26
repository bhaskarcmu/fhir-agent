FROM python:3.12-slim

WORKDIR /app

COPY client/clinical /app/client/clinical
RUN pip install --no-cache-dir -e /app/client/clinical

COPY mcp-agent/pyproject.toml /app/mcp-agent/pyproject.toml
COPY mcp-agent/src /app/mcp-agent/src
RUN pip install --no-cache-dir -e /app/mcp-agent

WORKDIR /app/mcp-agent

# Interactive by default; override with --query for non-interactive
ENTRYPOINT ["python3", "-m", "agent.agent"]
