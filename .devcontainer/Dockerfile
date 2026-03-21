FROM mcr.microsoft.com/devcontainers/base:ubuntu

USER root

# Java 21, Maven, Python 3, and essential utilities.
# Node.js, GCloud CLI, kubectl, Terraform, GitHub CLI, and Docker access
# are all installed via devcontainer features in devcontainer.json — keeping
# this Dockerfile free of external apt repositories and network-heavy steps.
RUN apt-get update && apt-get install -y \
    openjdk-21-jdk \
    maven \
    python3 \
    python3-pip \
    python3-venv \
    jq \
    unzip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python virtual environment for MCP services.
# Installed here so the venv is baked into the image and available immediately
# on container start without any post-start installation step.
RUN python3 -m venv /opt/pyenv \
    && /opt/pyenv/bin/pip install --upgrade pip setuptools wheel \
    && /opt/pyenv/bin/pip install fastapi uvicorn httpx pydantic

ENV VIRTUAL_ENV=/opt/pyenv
ENV PATH="/opt/pyenv/bin:${PATH}"
ENV NODE_OPTIONS="--max-old-space-size=4096"

WORKDIR /workspaces
