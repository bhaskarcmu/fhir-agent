# Multi-stage build for fhir-service (HAPI FHIR JPA R4, Spring Boot 3.x)
#
# Stage 1 — build:  Maven + JDK 21, produces ROOT.war
# Stage 2 — runtime: Eclipse Temurin 21 JRE (slim), runs ROOT.war
#
# The WAR is executable via Spring Boot's repackage goal (loaderImplementation=CLASSIC).
# It embeds Tomcat — no external servlet container needed.
#
# Build:
#   docker build -t fhir-service:latest fhir-service/
#
# Run locally (H2, no env vars needed):
#   docker run -p 8080:8080 fhir-service:latest
#
# Run with Neon (production profile):
#   docker run -p 8080:8080 \
#     -e SPRING_PROFILES_ACTIVE=neon \
#     -e SPRING_DATASOURCE_URL="jdbc:postgresql://HOST/DB?user=USER&password=PASS&sslmode=require" \
#     -e SPRING_DATASOURCE_DRIVER_CLASS_NAME="org.postgresql.Driver" \
#     -e SPRING_JPA_PROPERTIES_HIBERNATE_DIALECT="ca.uhn.fhir.jpa.model.dialect.HapiFhirPostgresDialect" \
#     -e HIBERNATE_DIALECT="ca.uhn.fhir.jpa.model.dialect.HapiFhirPostgresDialect" \
#     fhir-service:latest

# ---------------------------------------------------------------------------
# Stage 1: Build
# ---------------------------------------------------------------------------
FROM eclipse-temurin:21-jdk-jammy AS build

WORKDIR /build

# Copy Maven wrapper and POM first — Docker caches this layer until pom.xml changes.
# On subsequent builds with only source changes, dependency download is skipped.
COPY mvnw ./
COPY .mvn/ .mvn/
COPY pom.xml ./

# Download all dependencies into the image layer cache.
# -B: batch mode (no progress bars), -q: quiet, --no-transfer-progress: cleaner logs.
# This layer is invalidated only when pom.xml changes.
RUN chmod +x mvnw && ./mvnw -B -q dependency:go-offline --no-transfer-progress

# Copy source and build. Tests are skipped here — they run in CI, not in the image build.
COPY src/ src/
RUN ./mvnw -B -q package -DskipTests --no-transfer-progress

# ---------------------------------------------------------------------------
# Stage 2: Runtime
# ---------------------------------------------------------------------------
# Eclipse Temurin 21 JRE (jammy = Ubuntu 22.04 LTS).
# JRE only — no compiler, no jshell, smaller attack surface than JDK.
FROM eclipse-temurin:21-jre-jammy AS runtime

# Run as a non-root user. GKE and most container runtimes require this.
RUN groupadd --system fhir && useradd --system --gid fhir fhir

WORKDIR /app

# Copy the executable WAR from the build stage.
COPY --from=build /build/target/ROOT.war app.war

# Give the non-root user ownership.
RUN chown fhir:fhir app.war

USER fhir

# Spring Boot listens on 8080 by default (configured in application.yaml).
EXPOSE 8080

# Health check for local docker run / Docker Compose usage.
# Kubernetes ignores this and uses the liveness/readiness probes in deployment.yaml instead.
# start-period=90s matches initialDelaySeconds=90 in the Deployment — HAPI FHIR runs
# Hibernate schema migrations on first boot which takes 60-90 seconds.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD curl -sf http://localhost:8080/actuator/health/readiness || exit 1

# JVM tuning for containers:
#   -XX:+UseContainerSupport        — respect cgroup CPU/memory limits (default in JDK 11+, explicit here for clarity)
#   -XX:MaxRAMPercentage=75.0       — use up to 75% of container memory for heap
#   -XX:+ExitOnOutOfMemoryError     — crash fast on OOM rather than limping along
#   -Djava.security.egd=...         — faster startup: use /dev/urandom for SecureRandom seeding
ENTRYPOINT ["java", \
  "-XX:+UseContainerSupport", \
  "-XX:MaxRAMPercentage=75.0", \
  "-XX:+ExitOnOutOfMemoryError", \
  "-Djava.security.egd=file:/dev/./urandom", \
  "-jar", "app.war"]
