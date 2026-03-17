FROM mcr.microsoft.com/devcontainers/base:ubuntu

# Install gcloud CLI
RUN apt-get update && apt-get install -y curl apt-transport-https ca-certificates gnupg

RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] http://packages.cloud.google.com/apt cloud-sdk main" \
    | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list

RUN curl https://packages.cloud.google.com/apt/doc/apt-key.gpg \
    | apt-key --keyring /usr/share/keyrings/cloud.google.gpg add -

RUN apt-get update && apt-get install -y google-cloud-cli

# Install Maven
RUN apt-get install -y maven

# Clean up
RUN apt-get clean
