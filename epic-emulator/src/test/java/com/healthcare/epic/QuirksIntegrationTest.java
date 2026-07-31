package com.healthcare.epic;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;

/**
 * Verifies the M4 definition of done (PRD FR4–FR6, design.md §12): each of the three quirks is
 * independently demonstrable against a real request.
 *
 * <ul>
 *   <li>Quirk A (pagination) — {@code _count} is capped/injected on the outgoing request, and a
 *       response {@code Bundle}'s next link is replaced with an opaque, resolvable token.
 *   <li>Quirk B (required search params) — {@code MedicationRequest} search without both
 *       {@code patient} and {@code status} is rejected before fhir-service is ever called.
 *   <li>Quirk C (error shape) — every rejection this module generates (quirk B, the auth gate)
 *       uses the Epic-style {@code OperationOutcome} shape, not a generic error body.
 * </ul>
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class QuirksIntegrationTest {

    private static final String CLIENT_ID = "test-client";
    private static final String TOKEN_ENDPOINT = "http://localhost:8092/oauth2/token";
    private static final RSAKey CLIENT_KEY_PAIR = generateKeyPair();
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private static RSAKey generateKeyPair() {
        try {
            return new RSAKeyGenerator(2048).keyID(CLIENT_ID).generate();
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    private static HttpServer stubFhir;
    private static final Map<String, String> stubResponsesByPath = new ConcurrentHashMap<>();
    private static final Map<String, String> lastQueryByPath = new ConcurrentHashMap<>();

    @BeforeAll
    static void startStubFhirService() throws IOException {
        stubFhir = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        stubFhir.createContext(
                "/",
                ex -> {
                    String path = ex.getRequestURI().getPath();
                    // ConcurrentHashMap rejects null values -- a query-less request (e.g. the
                    // pagination continuation's real next-page URL) would otherwise throw an NPE
                    // inside this handler, which the client sees as a bare connection drop
                    // ("no bytes received"), not a clean error response.
                    lastQueryByPath.put(path, ex.getRequestURI().getQuery() == null ? "" : ex.getRequestURI().getQuery());
                    String responseBody = stubResponsesByPath.get(path);
                    byte[] out =
                            (responseBody != null
                                            ? responseBody
                                            : "{\"resourceType\":\"OperationOutcome\"}")
                                    .getBytes(StandardCharsets.UTF_8);
                    ex.getResponseHeaders().add("Content-Type", "application/fhir+json");
                    ex.sendResponseHeaders(responseBody != null ? 200 : 404, out.length);
                    ex.getResponseBody().write(out);
                    ex.close();
                });
        stubFhir.start();
    }

    @AfterAll
    static void stopStubFhirService() {
        stubFhir.stop(0);
    }

    @DynamicPropertySource
    static void props(DynamicPropertyRegistry registry) {
        registry.add(
                "fhir.base-url", () -> "http://127.0.0.1:" + stubFhir.getAddress().getPort());
        registry.add("epic.auth.token-endpoint", () -> TOKEN_ENDPOINT);
        registry.add("epic.auth.clients[0].client-id", () -> CLIENT_ID);
        registry.add(
                "epic.auth.clients[0].jwk", () -> CLIENT_KEY_PAIR.toPublicJWK().toJSONString());
        registry.add("epic.quirks.pagination.max-count", () -> "20");
    }

    private static String stubBaseUrl() {
        return "http://127.0.0.1:" + stubFhir.getAddress().getPort();
    }

    @LocalServerPort private int port;

    private final RestClient client = RestClient.create();

    private String baseUrl() {
        return "http://localhost:" + port;
    }

    private String fetchAccessToken() throws Exception {
        JWTClaimsSet claims =
                new JWTClaimsSet.Builder()
                        .issuer(CLIENT_ID)
                        .subject(CLIENT_ID)
                        .audience(TOKEN_ENDPOINT)
                        .jwtID(UUID.randomUUID().toString())
                        .issueTime(Date.from(Instant.now()))
                        .expirationTime(Date.from(Instant.now().plusSeconds(120)))
                        .build();
        SignedJWT jwt =
                new SignedJWT(
                        new JWSHeader.Builder(JWSAlgorithm.RS384).keyID(CLIENT_ID).build(), claims);
        jwt.sign(new RSASSASigner(CLIENT_KEY_PAIR));

        MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
        form.add("grant_type", "client_credentials");
        form.add(
                "client_assertion_type",
                "urn:ietf:params:oauth:client-assertion-type:jwt-bearer");
        form.add("client_assertion", jwt.serialize());

        Map<String, Object> resp =
                client.post()
                        .uri(baseUrl() + "/oauth2/token")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .body(form)
                        .retrieve()
                        .body(Map.class);
        return (String) resp.get("access_token");
    }

    // ---- Quirk B: required search-parameter combination ----

    @Test
    void medicationRequestSearch_missingStatus_isRejected_beforeReachingFhirService() throws Exception {
        String token = fetchAccessToken();

        HttpClientErrorException ex =
                org.junit.jupiter.api.Assertions.assertThrows(
                        HttpClientErrorException.class,
                        () ->
                                client.get()
                                        .uri(baseUrl() + "/fhir/MedicationRequest?patient=1")
                                        .header("Authorization", "Bearer " + token)
                                        .retrieve()
                                        .toEntity(String.class));

        assertThat(ex.getStatusCode().value()).isEqualTo(400);
        JsonNode body = MAPPER.readTree(ex.getResponseBodyAsString());
        assertThat(body.path("resourceType").asText()).isEqualTo("OperationOutcome");
        assertThat(body.path("issue").get(0).path("details").path("coding").get(0).path("code").asText())
                .isEqualTo("missing-required-search-parameter");
        assertThat(body.path("issue").get(0).path("details").path("coding").get(0).path("system").asText())
                .isEqualTo("http://epic-emulator.local/fhir/error-codes");
    }

    @Test
    void medicationRequestSearch_patientAndStatus_isAllowedThrough() throws Exception {
        stubResponsesByPath.put(
                "/fhir/MedicationRequest",
                "{\"resourceType\":\"Bundle\",\"type\":\"searchset\",\"entry\":[]}");
        String token = fetchAccessToken();

        ResponseEntity<String> resp =
                client.get()
                        .uri(baseUrl() + "/fhir/MedicationRequest?patient=1&status=active")
                        .header("Authorization", "Bearer " + token)
                        .retrieve()
                        .toEntity(String.class);

        assertThat(resp.getStatusCode().value()).isEqualTo(200);
    }

    // ---- Quirk A: pagination cap + opaque next-link ----

    @Test
    void countAbovecap_isClampedOnTheOutgoingRequest() throws Exception {
        stubResponsesByPath.put(
                "/fhir/MedicationRequest",
                "{\"resourceType\":\"Bundle\",\"type\":\"searchset\",\"entry\":[]}");
        String token = fetchAccessToken();

        client.get()
                .uri(baseUrl() + "/fhir/MedicationRequest?patient=1&status=active&_count=500")
                .header("Authorization", "Bearer " + token)
                .retrieve()
                .toEntity(String.class);

        assertThat(lastQueryByPath.get("/fhir/MedicationRequest")).contains("_count=20");
        assertThat(lastQueryByPath.get("/fhir/MedicationRequest")).doesNotContain("_count=500");
    }

    @Test
    void missingCount_isInjectedOnTheOutgoingRequest() throws Exception {
        stubResponsesByPath.put(
                "/fhir/AllergyIntolerance",
                "{\"resourceType\":\"Bundle\",\"type\":\"searchset\",\"entry\":[]}");
        String token = fetchAccessToken();

        client.get()
                .uri(baseUrl() + "/fhir/AllergyIntolerance")
                .header("Authorization", "Bearer " + token)
                .retrieve()
                .toEntity(String.class);

        assertThat(lastQueryByPath.get("/fhir/AllergyIntolerance")).isEqualTo("_count=20");
    }

    @Test
    void nextLink_isReplacedWithAnOpaqueToken_andResolvesOnFollowUp() throws Exception {
        String realNextUrl = stubBaseUrl() + "/fhir/MedicationRequest/_realnext";
        stubResponsesByPath.put(
                "/fhir/MedicationRequest",
                "{\"resourceType\":\"Bundle\",\"type\":\"searchset\","
                        + "\"link\":[{\"relation\":\"next\",\"url\":\""
                        + realNextUrl
                        + "\"}],\"entry\":[]}");
        stubResponsesByPath.put(
                "/fhir/MedicationRequest/_realnext",
                "{\"resourceType\":\"Bundle\",\"type\":\"searchset\",\"entry\":[]}");
        String token = fetchAccessToken();

        JsonNode firstPage =
                MAPPER.readTree(
                        client.get()
                                .uri(baseUrl() + "/fhir/MedicationRequest?patient=1&status=active")
                                .header("Authorization", "Bearer " + token)
                                .retrieve()
                                .body(String.class));

        String opaqueNextUrl = firstPage.path("link").get(0).path("url").asText();
        assertThat(opaqueNextUrl).doesNotContain("_realnext"); // caller never sees the real URL
        assertThat(opaqueNextUrl).matches("/fhir/_page/[A-Za-z0-9_-]+");

        // Follow it verbatim — should resolve to the stub's real next-page content.
        ResponseEntity<String> continued =
                client.get()
                        .uri(baseUrl() + opaqueNextUrl)
                        .header("Authorization", "Bearer " + token)
                        .retrieve()
                        .toEntity(String.class);

        assertThat(continued.getStatusCode().value()).isEqualTo(200);
        assertThat(lastQueryByPath).containsKey("/fhir/MedicationRequest/_realnext");
    }

    @Test
    void continuationEndpoint_stillRequiresAuth() {
        HttpClientErrorException ex =
                org.junit.jupiter.api.Assertions.assertThrows(
                        HttpClientErrorException.class,
                        () ->
                                client.get()
                                        .uri(baseUrl() + "/fhir/_page/whatever-token")
                                        .retrieve()
                                        .toEntity(String.class));
        assertThat(ex.getStatusCode().value()).isEqualTo(401);
    }

    @Test
    void unknownContinuationToken_isRejectedWithEpicShapedError() throws Exception {
        String token = fetchAccessToken();

        HttpClientErrorException ex =
                org.junit.jupiter.api.Assertions.assertThrows(
                        HttpClientErrorException.class,
                        () ->
                                client.get()
                                        .uri(baseUrl() + "/fhir/_page/nonexistent-token")
                                        .header("Authorization", "Bearer " + token)
                                        .retrieve()
                                        .toEntity(String.class));

        assertThat(ex.getStatusCode().value()).isEqualTo(404);
        JsonNode body = MAPPER.readTree(ex.getResponseBodyAsString());
        assertThat(body.path("resourceType").asText()).isEqualTo("OperationOutcome");
        assertThat(body.path("issue").get(0).path("details").path("coding").get(0).path("code").asText())
                .isEqualTo("unknown-page-token");
    }

    // ---- Quirk C: Epic-shaped OperationOutcome on the auth gate's own rejection ----

    @Test
    void authGateRejection_usesEpicShapedOperationOutcome_notPlainOAuthJson() throws Exception {
        HttpClientErrorException ex =
                org.junit.jupiter.api.Assertions.assertThrows(
                        HttpClientErrorException.class,
                        () ->
                                client.get()
                                        .uri(baseUrl() + "/fhir/Patient/1")
                                        .retrieve()
                                        .toEntity(String.class));

        assertThat(ex.getStatusCode().value()).isEqualTo(401);
        JsonNode body = MAPPER.readTree(ex.getResponseBodyAsString());
        assertThat(body.path("resourceType").asText()).isEqualTo("OperationOutcome");
        assertThat(body.path("issue").get(0).path("details").path("coding").get(0).path("code").asText())
                .isEqualTo("invalid-token");
    }
}
