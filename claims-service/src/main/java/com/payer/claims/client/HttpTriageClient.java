package com.payer.claims.client;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.payer.claims.domain.CanonicalClaim;
import com.payer.claims.domain.RiskLevel;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * HTTP transport to the reused triage service (Phase 1), which returns a FHIR RiskAssessment.
 * Resilient by design: any failure degrades to {@link RiskLevel#LOW} (logged) so triage being
 * down never hard-blocks adjudication — a production build would put a circuit breaker here and
 * consider pending instead (see plan §5). Full member→FHIR-patient resolution lands in M4.
 */
@Component
public class HttpTriageClient implements TriageClient {

    private static final Logger log = LoggerFactory.getLogger(HttpTriageClient.class);

    private final ObjectMapper mapper = new ObjectMapper();
    private final HttpClient http = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)  // uvicorn is HTTP/1.1-only; avoid the h2c upgrade
            .connectTimeout(Duration.ofSeconds(5)).build();
    private final String baseUrl;

    public HttpTriageClient(@Value("${triage.base-url:http://localhost:8001}") String baseUrl) {
        this.baseUrl = baseUrl.replaceAll("/+$", "");
    }

    @Override
    public RiskLevel assess(CanonicalClaim claim, String fhirPatientId) {
        if (fhirPatientId == null || fhirPatientId.isBlank()) {
            log.info("no FHIR patient for member {}; clinical risk defaults to LOW", claim.memberId());
            return RiskLevel.LOW;
        }
        try {
            // Only patient_id — triage evaluates all active meds vs. recorded allergies.
            // (Its optional medication_id is a FHIR MedicationRequest id, not an RxNorm code.)
            HttpRequest req = HttpRequest.newBuilder(URI.create(baseUrl + "/triage/refill-risk"))
                    .timeout(Duration.ofSeconds(20))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            "{\"patient_id\":\"" + fhirPatientId + "\"}"))
                    .build();
            HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() / 100 != 2) {
                log.warn("triage returned {} for patient {}; defaulting clinical risk to LOW",
                        resp.statusCode(), fhirPatientId);
                return RiskLevel.LOW;
            }
            JsonNode body = mapper.readTree(resp.body());
            String code = body.path("prediction").path(0)
                    .path("qualitativeRisk").path("coding").path(0).path("code").asText("LOW");
            return switch (code.toUpperCase()) {
                case "HIGH" -> RiskLevel.HIGH;
                case "MODERATE" -> RiskLevel.MODERATE;
                default -> RiskLevel.LOW;
            };
        } catch (Exception e) {
            log.warn("triage unavailable ({}); defaulting clinical risk to LOW", e.toString());
            return RiskLevel.LOW;
        }
    }
}
