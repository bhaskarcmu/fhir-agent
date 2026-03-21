FROM mcr.microsoft.com/devcontainers/base:ubuntu

USER root

# Create log directory
RUN mkdir -p /var/log/devcontainer

# System dependencies (Java, Maven, Python, etc.)
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
    wget \
    && rm -rf /var/lib/apt/lists/* \
    || { echo "System dependencies failed" >> /var/log/devcontainer/errors.log; exit 0; }

# Node.js (for Claude Code and other tooling)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/* \
    || echo "Node.js installation failed" >> /var/log/devcontainer/errors.log

# Google Cloud CLI
RUN curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
    | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" > /etc/apt/sources.list.d/google-cloud-sdk.list \
    && apt-get update \
    && apt-get install -y google-cloud-cli google-cloud-sdk-gke-gcloud-auth-plugin \
    && rm -rf /var/lib/apt/lists/* \
    || echo "Google Cloud CLI installation failed" >> /var/log/devcontainer/errors.log

# kubectl
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && chmod +x kubectl \
    && mv kubectl /usr/local/bin/ \
    || echo "kubectl installation failed" >> /var/log/devcontainer/errors.log

# Terraform
RUN wget -O- https://apt.releases.hashicorp.com/gpg \
    | gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" > /etc/apt/sources.list.d/hashicorp.list \
    && apt-get update \
    && apt-get install -y terraform \
    && rm -rf /var/lib/apt/lists/* \
    || echo "Terraform installation failed" >> /var/log/devcontainer/errors.log

# Install GitHub CLI (needed for Copilot CLI extension)
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/* \
    || echo "GitHub CLI installation failed" >> /var/log/devcontainer/errors.log

# Install Claude Code (official CLI via npm)
RUN npm install -g @anthropic-ai/claude-code \
    && cp /usr/local/bin/claude /opt/pyenv/bin/ \
    && chmod +x /opt/pyenv/bin/claude \
    || echo "Claude Code installation failed" >> /var/log/devcontainer/errors.log

# Python virtual environment for MCP work
RUN python3 -m venv /opt/pyenv \
    && /opt/pyenv/bin/pip install --upgrade pip setuptools wheel \
    && /opt/pyenv/bin/pip install fastapi uvicorn httpx pydantic \
    || echo "Python venv creation failed" >> /var/log/devcontainer/errors.log

# Install pipx as fallback (optional)
RUN apt-get update && apt-get install -y pipx \
    && pipx ensurepath \
    && rm -rf /var/lib/apt/lists/* \
    || echo "pipx installation failed" >> /var/log/devcontainer/errors.log

# Set environment variables
ENV VIRTUAL_ENV=/opt/pyenv
ENV PATH="/opt/pyenv/bin:${PATH}"
ENV NODE_OPTIONS="--max-old-space-size=4096"

# Create scripts directory for post‑create script
RUN mkdir -p /workspaces/.devcontainer/scripts

WORKDIR /workspaces
