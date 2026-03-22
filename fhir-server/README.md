# FHIR R4 Server

A standards-compliant, multi-database FHIR R4 server built on
[HAPI FHIR JPA 8.8.0](https://hapifhir.io). This is the **shared FHIR data layer**
for the agentic healthcare platform.

## Purpose

This module provides:
- **Generic FHIR R4 endpoints** for all resources (Patient, MedicationRequest, AllergyIntolerance, etc.)
- **Zero-config local development** with H2 in-memory database
- **Cloud deployment** with Neon serverless PostgreSQL
- **MCP tool targets** for the agentic orchestration layer (`mcp-agent`)

It is intentionally generic — **not EHR-specific**. Epic and Athena customizations
live in separate emulator modules (`epic-emulator/`, `athena-emulator/`).

## Integration with Platform

```
┌─────────────────┐
│   MCP Agent     │  ← Uses FHIR tools (get_patient, get_medications, etc.)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  FHIR Server    │  ← This module
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
   H2       Neon    (selectable via SPRING_PROFILES_ACTIVE)
```

## Database Profiles

| Profile | Database | Use Case | How to start |
|---------|----------|----------|--------------|
| default | H2 in-memory | Local development | `./mvnw spring-boot:run` |
| neon | Neon serverless PostgreSQL | Production / staging | `SPRING_PROFILES_ACTIVE=neon ./mvnw spring-boot:run` |

## Key Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /fhir/metadata` | FHIR CapabilityStatement (R4) |
| `POST /fhir/Patient` | Create a Patient resource |
| `GET /fhir/Patient/{id}` | Read a Patient resource |
| `GET /fhir/Patient?family=Smith` | Search patients by family name |
| `GET /actuator/health` | Health check (`{"status":"UP"}`) |

## Key Features

- **Optimistic locking** via `ETag` and `If-Match` headers (FHIR version-aware updates)
- **FHIR CapabilityStatement** at `GET /fhir/metadata`
- **Versioned profile URL fallback** (e.g., `Patient|4.0.1` → `Patient`)
- **Binary storage** — database (default) or filesystem
- **Master Data Management (MDM)** for patient matching (opt-in via `hapi.fhir.mdm_enabled=true`)
- **Custom interceptors and operations** via `hapi.fhir.custom-interceptor-classes` and `hapi.fhir.custom-provider-classes`

## Running Locally (H2)

```bash
cd fhir-server
./mvnw spring-boot:run
```

Server starts on `http://localhost:8080`. Verify with:

```bash
curl http://localhost:8080/actuator/health
curl http://localhost:8080/fhir/metadata
```

## Running with Neon (PostgreSQL)

Set the following environment variables (or store them as Ona project secrets):

```bash
export SPRING_DATASOURCE_URL="jdbc:postgresql://host/db?user=USER&password=PASS&sslmode=require"
export SPRING_DATASOURCE_DRIVER_CLASS_NAME="org.postgresql.Driver"
export SPRING_JPA_PROPERTIES_HIBERNATE_DIALECT="ca.uhn.fhir.jpa.model.dialect.HapiFhirPostgresDialect"
export HIBERNATE_DIALECT="ca.uhn.fhir.jpa.model.dialect.HapiFhirPostgresDialect"

SPRING_PROFILES_ACTIVE=neon ./mvnw spring-boot:run
```

Get your Neon connection string from the [Neon Dashboard](https://console.neon.tech) →
select your project → **Connection string** → choose **JDBC** format.

## Custom Extensions

### Custom Spring Beans

To auto-wire custom Spring beans (interceptors, operations, etc.) into the server:

1. Create your bean class in a custom package:

```java
package com.yourcompany.fhir.custom;

@Component
public class MyAuditInterceptor implements IServerInterceptor { ... }
```

2. Register the package in `application.yaml`:

```yaml
hapi:
  fhir:
    custom-bean-packages:
      - com.yourcompany.fhir.custom
```

3. Your beans are auto-discovered and wired by Spring on startup.

You can also register interceptors and operation providers by class name without
making them Spring beans:

```yaml
hapi:
  fhir:
    custom-interceptor-classes: com.yourcompany.fhir.custom.MyInterceptor
    custom-provider-classes: com.yourcompany.fhir.custom.MyOperation
```

See `CustomBeanTest`, `CustomInterceptorTest`, and `CustomOperationTest` for working examples.

## Relationship to Other Modules

| Module | Role |
|--------|------|
| `fhir-server` (this) | Generic FHIR R4 data layer — no EHR-specific behaviour |
| `epic-emulator` | Future: Epic-specific auth stubs, custom profiles, proprietary extensions |
| `athena-emulator` | Future: Athena-specific customizations |
| `triage-service` | Future: Drug-allergy risk evaluation business logic |
| `mcp-agent` | Future: LLM-powered orchestration using FHIR tools |

## Building and Testing

```bash
cd fhir-server
./mvnw clean verify        # build + all tests
./mvnw test                # tests only
./mvnw package -DskipTests # build only
```

Requires Java 21 and Maven 3.8+ (or use the included `./mvnw` wrapper).
