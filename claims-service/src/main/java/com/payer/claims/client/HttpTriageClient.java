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
 *
 * <p><b>Fails closed.</b> Every path that does not produce a risk level we understand — member
 * unresolved, triage down or erroring, unrecognised response — returns {@link RiskLevel#UNKNOWN},
 * never {@link RiskLevel#LOW}. Approving a claim because a safety check was unavailable is a
 * clinical-safety hazard, so the rules engine maps UNKNOWN to PEND for human review (R17.5).
 * Adding a circuit breaker here is follow-up work; it changes latency, not this policy.
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
            log.warn("no FHIR patient for member {}; clinical safety UNKNOWN", claim.memberId());
            return RiskLevel.UNKNOWN;
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
                log.warn("triage returned {} for patient {}; clinical safety UNKNOWN",
                        resp.statusCode(), fhirPatientId);
                return RiskLevel.UNKNOWN;
            }
            JsonNode code = mapper.readTree(resp.body()).path("prediction").path(0)
                    .path("qualitativeRisk").path("coding").path(0).path("code");
            // A missing/unrecognised code means the contract drifted — we did not get an answer
            // we understand, so treat it as UNKNOWN rather than reading it as "safe".
            return switch (code.asText("").toUpperCase()) {
                case "HIGH" -> RiskLevel.HIGH;
                case "MODERATE" -> RiskLevel.MODERATE;
                case "LOW" -> RiskLevel.LOW;
                default -> {
                    log.warn("triage response had no recognised risk code for patient {}; "
                            + "clinical safety UNKNOWN", fhirPatientId);
                    yield RiskLevel.UNKNOWN;
                }
            };
        } catch (Exception e) {
            log.warn("triage unavailable ({}); clinical safety UNKNOWN", e.toString());
            return RiskLevel.UNKNOWN;
        }
    }
}
