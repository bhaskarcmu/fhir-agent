FROM python:3.12-slim

WORKDIR /app

# Install fhir-clinical-client first (editable install from repo mount).
# In docker-compose the repo root is mounted at /workspace.
# For standalone builds, copy the client source.
COPY client/clinical /app/client/clinical
RUN pip install --no-cache-dir -e /app/client/clinical

# Install triage service dependencies
COPY triage-service/pyproject.toml /app/triage-service/pyproject.toml
COPY triage-service/src /app/triage-service/src
RUN pip install --no-cache-dir -e /app/triage-service

WORKDIR /app/triage-service

EXPOSE 8001

CMD ["uvicorn", "triage.main:app", "--host", "0.0.0.0", "--port", "8001"]
