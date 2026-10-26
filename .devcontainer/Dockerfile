FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

USER root

# Base toolchain: Java 21, Maven, Python 3 (venv at /opt/pyenv) and inotify-tools (AI chat
# archive watcher). Docker-in-Docker, Node, gh, Terraform and kubectl/Helm come from the
# devcontainer features in devcontainer.json.
RUN apt-get update && apt-get install -y \
    openjdk-21-jdk \
    maven \
    python3 \
    python3-pip \
    python3-venv \
    jq \
    unzip \
    inotify-tools \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/pyenv \
    && /opt/pyenv/bin/pip install --upgrade pip setuptools wheel \
    && /opt/pyenv/bin/pip install fastapi uvicorn httpx pydantic \
    # Make the venv writable by the vscode user so postCreateCommand
    # can register editable installs without sudo.
    && chmod -R a+w /opt/pyenv/lib /opt/pyenv/bin

# Codespaces: each interactive terminal restarts any background service the
# lifecycle commands could not keep alive (no-op when all are running).
RUN printf '%s\n' \
    '[ "${CODESPACES:-}" = true ] && [ -f /workspaces/fhir-agent/.devcontainer/scripts/post-start.sh ] \' \
    '  && bash /workspaces/fhir-agent/.devcontainer/scripts/post-start.sh terminal' \
    >> /etc/bash.bashrc

ENV VIRTUAL_ENV=/opt/pyenv
ENV PATH="/opt/pyenv/bin:${PATH}"

WORKDIR /workspaces
