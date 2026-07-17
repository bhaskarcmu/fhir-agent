FROM python:3.12-slim

WORKDIR /app

# Install provider-registry-service dependencies
COPY provider-registry-service/pyproject.toml /app/provider-registry-service/pyproject.toml
COPY provider-registry-service/src /app/provider-registry-service/src
RUN pip install --no-cache-dir -e /app/provider-registry-service

COPY provider-registry-service/schema.sql /app/provider-registry-service/schema.sql

WORKDIR /app/provider-registry-service

EXPOSE 8002

CMD ["sh", "-c", "python -m provider_registry.init_db && uvicorn provider_registry.main:app --host 0.0.0.0 --port 8002"]
