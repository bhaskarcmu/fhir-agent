FROM python:3.12-slim

WORKDIR /app

# provider_ingest scripts only need psycopg + the stdlib -- reuse
# provider-registry-service's install rather than duplicating the dependency.
COPY provider-registry-service/pyproject.toml /app/provider-registry-service/pyproject.toml
COPY provider-registry-service/src /app/provider-registry-service/src
COPY provider-registry-service/schema.sql /app/provider-registry-service/schema.sql
RUN pip install --no-cache-dir -e /app/provider-registry-service

COPY data/scripts/provider_ingest /app/data/scripts/provider_ingest
COPY data/reference/providers /app/data/reference/providers

WORKDIR /app

ENTRYPOINT ["python3", "data/scripts/provider_ingest/run_ingestion.py"]
CMD ["--states", "NC"]
