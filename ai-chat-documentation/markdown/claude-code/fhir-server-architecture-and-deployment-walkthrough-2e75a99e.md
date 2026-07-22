# FHIR server architecture and deployment walkthrough

## Turn 1

### Prompt

I want a conceptual walkthrough of the FHIR server. Starting with what Java code was downloaded, to the containerized deployable SpringBoot solution (if it can be called a "solution" correct this please) that has multiple DB profiles to enable fast development and robust performance in production. Tell me first, (1) what was downloaded and its capabilities, and (2) whether what I said here is correct, with explanation and expansion for missing concepts and enhancements.

Keep your analysis read only.

### Claude response

I'll explore the fhir-service directory to build an accurate picture before explaining.

This confirms it's the **hapi-fhir-jpaserver-starter** codebase. Let me confirm via the pom.xml, then check the Dockerfile and the profile-specific config files (application.yaml, application-neon.yaml, application-cds.yaml, application-elastic.yaml) and the test config to understand the H2/Postgres/Neon split.

<details>
<summary>Execution details — 8 tool events</summary>

### Turn 1 activity

- **Bash** `find /workspaces/fhir-agent/fhir-service -maxdepth 3 -type f | grep -v '/target/' | sort`
- **Bash** `find /workspaces/fhir-agent/fhir-service/src -type f 2>/dev/null | grep -v '/test/' | sort; echo "---TEST---"; find /workspaces/fhir-agent/fhir-service/src -type f 2>/dev/null | grep '/test/' | sort`
- **Read** `/workspaces/fhir-agent/fhir-service/pom.xml`
- **Read** `/workspaces/fhir-agent/fhir-service/Dockerfile`
- **Read** `/workspaces/fhir-agent/fhir-service/src/main/resources/application.yaml`
- **Read** `/workspaces/fhir-agent/fhir-service/src/main/resources/application-neon.yaml`
- **Read** `/workspaces/fhir-agent/fhir-service/README.md`
- **Read** `/workspaces/fhir-agent/fhir-service/k8s/deployment.yaml`

</details>

---

## Archive metadata

- **Source:** Claude Code
- **Session ID:** `2e75a99e-6530-4b28-82f9-b3b5ee1df979`
- **Created:** 22 July 2026, 14:25 UTC
- **Last updated:** 22 July 2026, 14:25 UTC
- **Turns:** 1
- **Status:** Complete
