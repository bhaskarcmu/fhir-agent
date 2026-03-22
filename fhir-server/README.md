# FHIR R4 Server

A standards-compliant FHIR R4 server built on [HAPI FHIR JPA 8.8.0](https://hapifhir.io). Serves as the shared FHIR data source for the healthcare agent platform.

## Profiles

| Profile | Database | How to run |
|---|---|---|
| default | H2 in-memory | `./mvnw spring-boot:run` |
| neon | Neon serverless PostgreSQL | See below |

## Running with Neon (cloud PostgreSQL)

```bash
SPRING_DATASOURCE_URL="jdbc:postgresql://host/db?user=x&password=y&sslmode=require" \
SPRING_DATASOURCE_DRIVER_CLASS_NAME="org.postgresql.Driver" \
HIBERNATE_DIALECT="ca.uhn.fhir.jpa.model.dialect.HapiFhirPostgresDialect" \
./mvnw spring-boot:run -Dspring-boot.run.profiles=neon -Dmaven.test.skip=true
```

## Key endpoints

| Endpoint | Description |
|---|---|
| `GET /fhir/metadata` | FHIR CapabilityStatement |
| `POST /fhir/Patient` | Create a Patient resource |
| `GET /fhir/Patient/{id}` | Read a Patient resource |
| `GET /actuator/health` | Health check |

## Relationship to other modules

This module is a generic FHIR R4 server with no EHR-specific behaviour.
EHR-specific customisations (auth stubs, custom profiles, proprietary extensions) live in:

- `../epic-emulator/` — Epic-specific adapter (future)
- `../athena-emulator/` — Athena-specific adapter (future)
