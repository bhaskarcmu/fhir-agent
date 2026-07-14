# Multi-stage build for the claims-service (edge-facing façade, fronted by Kong).
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /app
COPY pom.xml .
RUN mvn -q -B dependency:go-offline
COPY src ./src
RUN mvn -q -B -DskipTests package

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /app/target/claims-service-*.jar app.jar
EXPOSE 8090
# payer-kb.dir must point at the mounted payer knowledge base in the target environment.
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
