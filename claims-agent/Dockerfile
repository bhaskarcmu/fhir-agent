# Claims explanation agent (run-once CLI). Build context: claims-agent/
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .
# ANTHROPIC_API_KEY/CLAUDE_API_KEY optional — without it the agent uses the deterministic
# explanation. CLAIMS_GATEWAY_URL points at the claims-service (or Kong proxy).
ENTRYPOINT ["python", "-m", "claims_agent"]
