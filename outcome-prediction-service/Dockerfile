FROM python:3.12-slim

WORKDIR /app

# client/clinical first: the patient endpoint reads FHIR through it (not on PyPI).
COPY client/clinical /app/client/clinical
RUN pip install --no-cache-dir -e /app/client/clinical

COPY outcome-prediction-service/pyproject.toml /app/outcome-prediction-service/pyproject.toml
COPY outcome-prediction-service/src /app/outcome-prediction-service/src
RUN pip install --no-cache-dir -e "/app/outcome-prediction-service[api]"

WORKDIR /app/outcome-prediction-service

# Model artifacts are never baked into the image (O17): mount the models directory read-only.
ENV OUTCOME_PREDICTION_MODELS_DIR=/models
EXPOSE 8005

CMD ["uvicorn", "outcome_prediction.api:app", "--host", "0.0.0.0", "--port", "8005"]
