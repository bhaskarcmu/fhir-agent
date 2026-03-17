FROM mcr.microsoft.com/devcontainers/base:ubuntu

USER root

RUN apt-get update && apt-get install -y \
    openjdk-21-jdk \
    maven \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    jq \
    unzip \
    ca-certificates \
    apt-transport-https \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Google Cloud CLI
RUN curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
    | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] http://packages.cloud.google.com/apt cloud-sdk main" \
    > /etc/apt/sources.list.d/google-cloud-sdk.list && \
    apt-get update && apt-get install -y google-cloud-cli && \
    rm -rf /var/lib/apt/lists/*

# Create Python venv for MCP / agent work
RUN python3 -m venv /opt/pyenv && \
    /opt/pyenv/bin/pip install --upgrade pip setuptools wheel && \
    /opt/pyenv/bin/pip install fastapi uvicorn httpx pydantic

ENV VIRTUAL_ENV=/opt/pyenv
ENV PATH="/opt/pyenv/bin:${PATH}"

WORKDIR /workspaces
