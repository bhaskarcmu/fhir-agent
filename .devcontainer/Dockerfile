FROM mcr.microsoft.com/devcontainers/base:ubuntu

USER root

# Create log directory for build diagnostics
RUN mkdir -p /var/log/devcontainer

# System dependencies: Java 21, Maven, Python 3, build tools
RUN apt-get update && apt-get install -y \
    openjdk-21-jdk \
    maven \
    python3 \
    python3-pip \
    python3-venv \
    pipx \
    git \
    curl \
    jq \
    unzip \
    ca-certificates \
    apt-transport-https \
    gnupg \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Node.js 20 (required for Claude Code and MCP tooling)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Google Cloud CLI + GKE auth plugin
RUN curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
    | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
    > /etc/apt/sources.list.d/google-cloud-sdk.list \
    && apt-get update \
    && apt-get install -y google-cloud-cli google-cloud-sdk-gke-gcloud-auth-plugin \
    && rm -rf /var/lib/apt/lists/*

# kubectl (latest stable)
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && chmod +x kubectl \
    && mv kubectl /usr/local/bin/

# Terraform
RUN wget -O- https://apt.releases.hashicorp.com/gpg \
    | gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" \
    > /etc/apt/sources.list.d/hashicorp.list \
    && apt-get update \
    && apt-get install -y terraform \
    && rm -rf /var/lib/apt/lists/*

# GitHub CLI (required for Copilot CLI extension)
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/*

# Python virtual environment for MCP services (FastAPI, uvicorn, etc.)
# Must be created BEFORE any step that references /opt/pyenv
RUN python3 -m venv /opt/pyenv \
    && /opt/pyenv/bin/pip install --upgrade pip setuptools wheel \
    && /opt/pyenv/bin/pip install fastapi uvicorn httpx pydantic

# Claude Code CLI — installed globally via npm, available on PATH via /usr/local/bin
RUN npm install -g @anthropic-ai/claude-code

ENV VIRTUAL_ENV=/opt/pyenv
ENV PATH="/opt/pyenv/bin:${PATH}"
ENV NODE_OPTIONS="--max-old-space-size=4096"

WORKDIR /workspaces
