FROM mcr.microsoft.com/devcontainers/base:ubuntu

USER root

# Minimal build: Java 21, Maven, Python 3, and MCP service dependencies.
# This is a diagnostic build to confirm the base image + apt install works
# on this Ona environment before adding devcontainer features back.
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

RUN python3 -m venv /opt/pyenv \
    && /opt/pyenv/bin/pip install --upgrade pip setuptools wheel \
    && /opt/pyenv/bin/pip install fastapi uvicorn httpx pydantic

ENV VIRTUAL_ENV=/opt/pyenv
ENV PATH="/opt/pyenv/bin:${PATH}"

WORKDIR /workspaces
