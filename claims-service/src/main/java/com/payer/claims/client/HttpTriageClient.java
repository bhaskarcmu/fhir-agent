package com.payer.claims.client;

import com.fasterxml.jackson.databind.JsonNode;
import com.payer.claims.domain.CanonicalClaim;
import com.payer.claims.domain.RiskLevel;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/**
 * HTTP transport to the reused triage service (Phase 1), which returns a FHIR RiskAssessment.
 * Resilient by design: any failure degrades to {@link RiskLevel#LOW} (logged) so triage being
 * down never hard-blocks adjudication — a production build would put a circuit breaker here and
 * consider pending instead (see plan §5). Full member→FHIR-patient resolution lands in M4.
 */
@Component
public class HttpTriageClient implements TriageClient {

    private static final Logger log = LoggerFactory.getLogger(HttpTriageClient.class);

    private final RestClient http;

    public HttpTriageClient(@Value("${triage.base-url:http://localhost:8001}") String baseUrl) {
        this.http = RestClient.builder().baseUrl(baseUrl).build();
    }

    @Override
    public RiskLevel assess(CanonicalClaim claim) {
        try {
            JsonNode body = http.post()
                    .uri("/triage/refill-risk")
                    .body(Map.of("patient_id", claim.memberId(), "medication_id", claim.rxcui()))
                    .retrieve()
                    .body(JsonNode.class);
            String code = body.path("prediction").path(0)
                    .path("qualitativeRisk").path("coding").path(0).path("code").asText("LOW");
            return switch (code.toUpperCase()) {
                case "HIGH" -> RiskLevel.HIGH;
                case "MODERATE" -> RiskLevel.MODERATE;
                default -> RiskLevel.LOW;
            };
        } catch (RuntimeException e) {
            log.warn("triage unavailable ({}); defaulting clinical risk to LOW", e.toString());
            return RiskLevel.LOW;
        }
    }
}
