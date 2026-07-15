package com.payer.claims;

import static org.assertj.core.api.Assertions.assertThat;

import com.payer.claims.client.HttpTriageClient;
import com.payer.claims.domain.CanonicalClaim;
import com.payer.claims.domain.RiskLevel;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

/**
 * Contract test for the reused triage service, over a real HTTP round-trip against a stub server.
 *
 * <p>Two things are pinned here. First, the request really does carry {@code patient_id} — a
 * mocked client cannot catch a transport that silently sends an empty body, which is exactly how
 * the safety check once failed. Second, every path that does not yield a risk level we understand
 * maps to {@link RiskLevel#UNKNOWN}, never {@link RiskLevel#LOW}: "we could not check" must not be
 * indistinguishable from "we checked and it is safe", or claims approve on a check that never ran.
 */
class HttpTriageClientTest {

    private HttpServer server;
    private final AtomicReference<String> lastBody = new AtomicReference<>();
    private final AtomicInteger calls = new AtomicInteger();

    /** Starts a stub triage on a free port; returns its base URL. */
    private String startStub(int status, String responseBody) throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/triage/refill-risk", ex -> {
            calls.incrementAndGet();
            lastBody.set(new String(ex.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            byte[] out = responseBody.getBytes(StandardCharsets.UTF_8);
            ex.getResponseHeaders().add("Content-Type", "application/json");
            ex.sendResponseHeaders(status, out.length);
            ex.getResponseBody().write(out);
            ex.close();
        });
        server.start();
        return "http://127.0.0.1:" + server.getAddress().getPort();
    }

    @AfterEach
    void stopStub() {
        if (server != null) {
            server.stop(0);
        }
    }

    private static String riskJson(String code) {
        return """
                {"resourceType":"RiskAssessment",
                 "prediction":[{"qualitativeRisk":{"coding":[{"code":"%s"}]}}]}""".formatted(code);
    }

    private static CanonicalClaim claim() {
        return new CanonicalClaim("C1", "000000009", "COM-SILVER", "723", "0093-8675",
                "amoxicillin", 30, 30, LocalDate.of(2026, 6, 1), "1234567890",
                LocalDate.of(2026, 1, 1), LocalDate.of(2026, 12, 31), false, false);
    }

    @Test
    void sendsPatientIdInTheRequestBody_andMapsHighRisk() throws IOException {
        String url = startStub(200, riskJson("high"));

        RiskLevel risk = new HttpTriageClient(url).assess(claim(), "member-000000009");

        assertThat(risk).isEqualTo(RiskLevel.HIGH);
        // The body must actually arrive — an empty body is the failure this test exists to catch.
        assertThat(lastBody.get()).contains("\"patient_id\"").contains("member-000000009");
    }

    @Test
    void mapsLowRisk_whenTriageChecksAndFindsNothing() throws IOException {
        String url = startStub(200, riskJson("low"));
        assertThat(new HttpTriageClient(url).assess(claim(), "member-000000001"))
                .isEqualTo(RiskLevel.LOW);
    }

    @Test
    void mapsModerateRisk() throws IOException {
        String url = startStub(200, riskJson("moderate"));
        assertThat(new HttpTriageClient(url).assess(claim(), "member-000000001"))
                .isEqualTo(RiskLevel.MODERATE);
    }

    @Test
    void unresolvedMember_isUnknown_andTriageIsNotCalled() throws IOException {
        String url = startStub(200, riskJson("low"));

        assertThat(new HttpTriageClient(url).assess(claim(), null)).isEqualTo(RiskLevel.UNKNOWN);

        assertThat(calls.get()).isZero(); // no patient to ask about — do not guess, do not approve
    }

    @Test
    void patientNotFoundAtTriage_isUnknown_notLow() throws IOException {
        String url = startStub(404, "{\"detail\":\"Patient x not found.\"}");
        assertThat(new HttpTriageClient(url).assess(claim(), "member-000000009"))
                .isEqualTo(RiskLevel.UNKNOWN);
    }

    @Test
    void triageServerError_isUnknown_notLow() throws IOException {
        String url = startStub(502, "{\"detail\":\"FHIR server error\"}");
        assertThat(new HttpTriageClient(url).assess(claim(), "member-000000009"))
                .isEqualTo(RiskLevel.UNKNOWN);
    }

    @Test
    void unrecognisedRiskCode_isUnknown_notLow() throws IOException {
        String url = startStub(200, riskJson("catastrophic"));
        assertThat(new HttpTriageClient(url).assess(claim(), "member-000000009"))
                .isEqualTo(RiskLevel.UNKNOWN);
    }

    @Test
    void responseMissingTheRiskCode_isUnknown_notLow() throws IOException {
        String url = startStub(200, "{\"resourceType\":\"RiskAssessment\"}");
        assertThat(new HttpTriageClient(url).assess(claim(), "member-000000009"))
                .isEqualTo(RiskLevel.UNKNOWN);
    }

    @Test
    void triageDown_isUnknown_notLow() throws IOException {
        String url = startStub(200, riskJson("low"));
        server.stop(0);   // nothing is listening now
        server = null;

        assertThat(new HttpTriageClient(url).assess(claim(), "member-000000009"))
                .isEqualTo(RiskLevel.UNKNOWN);
    }
}
