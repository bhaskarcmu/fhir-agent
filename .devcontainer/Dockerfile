FROM mcr.microsoft.com/devcontainers/base:ubuntu

USER root

# Create a log directory for defensive failures
RUN mkdir -p /var/log/devcontainer

# System dependencies (always succeeds)
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

# Node.js (try with standard method, log failure but continue)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/* \
    || echo "Node.js installation failed" >> /var/log/devcontainer/errors.log

# Google Cloud CLI (try, log failure)
RUN curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
    | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" > /etc/apt/sources.list.d/google-cloud-sdk.list \
    && apt-get update \
    && apt-get install -y google-cloud-cli google-cloud-sdk-gke-gcloud-auth-plugin \
    && rm -rf /var/lib/apt/lists/* \
    || echo "Google Cloud CLI installation failed" >> /var/log/devcontainer/errors.log

# kubectl (simple, log failure)
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && chmod +x kubectl \
    && mv kubectl /usr/local/bin/ \
    || echo "kubectl installation failed" >> /var/log/devcontainer/errors.log

# Terraform (log failure)
RUN wget -O- https://apt.releases.hashicorp.com/gpg \
    | gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" > /etc/apt/sources.list.d/hashicorp.list \
    && apt-get update \
    && apt-get install -y terraform \
    && rm -rf /var/lib/apt/lists/* \
    || echo "Terraform installation failed" >> /var/log/devcontainer/errors.log

# GitHub Copilot CLI – try multiple methods, log all attempts
RUN echo "=== Attempting GitHub Copilot CLI installation ===" > /var/log/devcontainer/copilot.log \
    && ( \
        # Method 1: install GitHub CLI and then the extension (recommended)
        ( curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
          && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
          && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
          && apt-get update \
          && apt-get install -y gh \
          && gh extension install github/gh-copilot \
          && echo "Method 1 succeeded" >> /var/log/devcontainer/copilot.log ) \
        || echo "Method 1 failed" >> /var/log/devcontainer/copilot.log \
    ) \
    && ( \
        # Method 2: try npm install (original, but known to fail; we'll just log)
        ( npm install -g @github/copilot-cli 2>&1 && echo "Method 2 succeeded" >> /var/log/devcontainer/copilot.log ) \
        || echo "Method 2 failed" >> /var/log/devcontainer/copilot.log \
    ) \
    && ( \
        # Method 3: try using the GitHub Copilot CLI binary directly (if available)
        ( curl -L https://github.com/github/copilot.vim/releases/latest/download/copilot-cli -o /usr/local/bin/copilot-cli \
          && chmod +x /usr/local/bin/copilot-cli \
          && echo "Method 3 succeeded" >> /var/log/devcontainer/copilot.log ) \
        || echo "Method 3 failed" >> /var/log/devcontainer/copilot.log \
    ) \
    || true

# Create Python virtual environment for MCP work (always succeeds)
RUN python3 -m venv /opt/pyenv \
    && /opt/pyenv/bin/pip install --upgrade pip setuptools wheel \
    && /opt/pyenv/bin/pip install fastapi uvicorn httpx pydantic \
    || echo "Python venv creation failed" >> /var/log/devcontainer/errors.log

# Install Claude Code in virtual environment (try, log failure)
RUN /opt/pyenv/bin/pip install claude-code \
    || echo "Claude Code installation failed" >> /var/log/devcontainer/errors.log

# (Optional) Install pipx as fallback for user-level tools
RUN apt-get update && apt-get install -y pipx \
    && pipx ensurepath \
    && rm -rf /var/lib/apt/lists/* \
    || echo "pipx installation failed" >> /var/log/devcontainer/errors.log

# Set environment variables (safe)
ENV VIRTUAL_ENV=/opt/pyenv
ENV PATH="/opt/pyenv/bin:${PATH}"
ENV NODE_OPTIONS="--max-old-space-size=4096"

# Create scripts directory (safe)
RUN mkdir -p /workspaces/.devcontainer/scripts

WORKDIR /workspaces
