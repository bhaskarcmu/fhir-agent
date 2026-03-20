FROM mcr.microsoft.com/devcontainers/base:ubuntu

USER root

# Install system dependencies
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
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (required for some tools)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Install Google Cloud CLI
RUN curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
    | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
    > /etc/apt/sources.list.d/google-cloud-sdk.list && \
    apt-get update && apt-get install -y google-cloud-cli google-cloud-sdk-gke-gcloud-auth-plugin && \
    rm -rf /var/lib/apt/lists/*

# Install kubectl
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && \
    chmod +x kubectl && \
    mv kubectl /usr/local/bin/

# Install Terraform
RUN wget -O- https://apt.releases.hashicorp.com/gpg | gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" \
    > /etc/apt/sources.list.d/hashicorp.list && \
    apt-get update && apt-get install -y terraform && \
    rm -rf /var/lib/apt/lists/*

# Install Claude Code (via pip - CORRECT METHOD)
RUN pip3 install claude-code

# Install GitHub Copilot CLI (optional, for terminal completions)
RUN npm install -g @github/copilot-cli

# Create Python virtual environment for MCP agent work
RUN python3 -m venv /opt/pyenv && \
    /opt/pyenv/bin/pip install --upgrade pip setuptools wheel && \
    /opt/pyenv/bin/pip install fastapi uvicorn httpx pydantic

# Set environment variables
ENV VIRTUAL_ENV=/opt/pyenv
ENV PATH="/opt/pyenv/bin:${PATH}"
ENV NODE_OPTIONS="--max-old-space-size=4096"

# Create scripts directory for helper scripts
RUN mkdir -p /workspaces/.devcontainer/scripts

WORKDIR /workspaces
