# Client Code

This directory contains two categories of client code for the fhir-agent platform,
written for two distinct audiences. Understanding which one you are determines which
folder is yours.

---

## The Two Hats

### Hat 1 — Platform Engineer (`client/platform/`)

You work at a health IT company, an EHR vendor, or a FHIR middleware provider.
You build and maintain the FHIR data layer itself. You care about schema migrations,
Spring profiles, Neon connection strings, Kubernetes manifests, and FHIR conformance.

Your code in `client/platform/` runs directly against the FHIR server — no Kong
gateway, no API key, no GCP. It assumes the service is running locally and tests
the server's behaviour at the FHIR protocol level.

**Go to `client/platform/` if you are:**
- Developing or modifying `fhir-service`
- Writing integration tests that validate FHIR server behaviour
- Testing schema migrations or profile conformance
- Debugging the server before deploying to GCP

---

### Hat 2 — Clinical Application Developer (`client/clinical/`)

You work at a healthcare provider, a digital health startup, or a care delivery
organisation. You build workflows and experiences on top of the FHIR data layer.
You do not know or care how the server is implemented — you have a URL and an API
key, and you need to fetch patients, medications, and clinical data.

Your code in `client/clinical/` is intentionally blind to `fhir-service` internals.
It speaks in clinical domain terms: patients, medications, conditions — not FHIR
bundles, search parameters, or HTTP verbs. This is also the foundation that the
MCP agent will be built on.

**Go to `client/clinical/` if you are:**
- Building a clinical application or workflow on top of the deployed service
- Developing or extending the MCP agent
- Running end-to-end tests against the GCP-deployed stack
- Integrating with the FHIR platform as an external consumer

---

## Decision Table

| I want to...                                      | Use                    |
|---------------------------------------------------|------------------------|
| Test the FHIR server locally before deploying     | `client/platform/`     |
| Validate a schema migration or profile change     | `client/platform/`     |
| Build a clinical workflow or agent                | `client/clinical/`     |
| Run smoke tests against the deployed GCP stack    | `client/clinical/`     |
| Fetch patient data from the deployed service      | `client/clinical/`     |
| Debug the FHIR server itself                      | `client/platform/`     |

---

## Shared Infrastructure

Both categories use the **existing devcontainer** — no separate environments needed.
The devcontainer already provides Python 3, Java 21, Maven, curl, and jq, which is
sufficient for both audiences.

Neither category should be modified by the other's audience. Platform engineers do
not touch `client/clinical/`. Clinical developers do not touch `client/platform/`
or anything in `fhir-service/`.
