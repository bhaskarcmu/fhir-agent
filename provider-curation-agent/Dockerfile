# Provider curation agent (run-once CLI). Build context: repo root -- this agent shells out
# to data/scripts/provider_ingest/*.py, which need to be present alongside it (mirrors
# data/scripts/provider_ingest/Dockerfile's repo-root-context pattern).
FROM python:3.12-slim

WORKDIR /app

COPY provider-curation-agent/pyproject.toml /app/provider-curation-agent/pyproject.toml
COPY provider-curation-agent/src /app/provider-curation-agent/src
RUN pip install --no-cache-dir -e /app/provider-curation-agent

# run_ingestion.py needs its own copy of psycopg + schema.sql; reuse provider-registry-service's
# install rather than duplicating the dependency declaration a third time.
COPY provider-registry-service/pyproject.toml /app/provider-registry-service/pyproject.toml
COPY provider-registry-service/src /app/provider-registry-service/src
COPY provider-registry-service/schema.sql /app/provider-registry-service/schema.sql
RUN pip install --no-cache-dir -e /app/provider-registry-service

COPY data/scripts/provider_ingest /app/data/scripts/provider_ingest
COPY data/reference/providers /app/data/reference/providers

WORKDIR /app

# ANTHROPIC_API_KEY/CLAUDE_API_KEY optional -- without one the agent uses the deterministic
# summary. DATABASE_URL required -- see provider_curation_agent/tools.py.
ENTRYPOINT ["python", "-m", "provider_curation_agent"]
