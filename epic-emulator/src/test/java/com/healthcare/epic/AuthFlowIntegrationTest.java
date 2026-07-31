package com.healthcare.epic;

import static org.assertj.core.api.Assertions.assertThat;

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
import java.util.concurrent.atomic.AtomicInteger;
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
 * Verifies the M2 definition of done (PRD FR2/FR8, design.md §12): a registered test client can
 * complete the JWT client-assertion flow and use the resulting token for a gated proxied call;
 * an unauthenticated (or invalid-token) call is rejected before it ever reaches fhir-service.
 *
 * <p>Generates its own throwaway RSA key pair rather than committing a fixed "known" one — the
 * public half is registered via {@code @DynamicPropertySource} (same mechanism M1's
 * {@code fhir.base-url} test override used), the private half never leaves this test.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class AuthFlowIntegrationTest {

    private static final String CLIENT_ID = "test-client";
    private static final String TOKEN_ENDPOINT = "http://localhost:8092/oauth2/token";
    private static final RSAKey CLIENT_KEY_PAIR = generateKeyPair();

    private static RSAKey generateKeyPair() {
        try {
            return new RSAKeyGenerator(2048).keyID(CLIENT_ID).generate();
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    private static HttpServer stubFhir;
    private static final AtomicInteger stubCalls = new AtomicInteger();

    @BeforeAll
    static void startStubFhirService() throws IOException {
        stubFhir = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        stubFhir.createContext(
                "/",
                ex -> {
                    stubCalls.incrementAndGet();
                    byte[] out =
                            "{\"resourceType\":\"Patient\",\"id\":\"123\"}"
                                    .getBytes(StandardCharsets.UTF_8);
                    ex.getResponseHeaders().add("Content-Type", "application/fhir+json");
                    ex.sendResponseHeaders(200, out.length);
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
    }

    @LocalServerPort private int port;

    private final RestClient client = RestClient.create();

    private String baseUrl() {
        return "http://localhost:" + port;
    }

    private static String signedAssertion(RSAKey signingKey, String issuer, String audience, Instant expiry)
            throws Exception {
        JWTClaimsSet claims =
                new JWTClaimsSet.Builder()
                        .issuer(issuer)
                        .subject(issuer)
                        .audience(audience)
                        .jwtID(UUID.randomUUID().toString())
                        .issueTime(Date.from(Instant.now()))
                        .expirationTime(Date.from(expiry))
                        .build();
        SignedJWT jwt =
                new SignedJWT(
                        new JWSHeader.Builder(JWSAlgorithm.RS384).keyID(CLIENT_ID).build(), claims);
        jwt.sign(new RSASSASigner(signingKey));
        return jwt.serialize();
    }

    private MultiValueMap<String, String> tokenRequestBody(String assertion) {
        MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
        form.add("grant_type", "client_credentials");
        form.add(
                "client_assertion_type",
                "urn:ietf:params:oauth:client-assertion-type:jwt-bearer");
        form.add("client_assertion", assertion);
        return form;
    }

    @Test
    void validClientAssertion_getsAnAccessToken_usableForAGatedProxiedCall() throws Exception {
        int before = stubCalls.get();
        String assertion =
                signedAssertion(
                        CLIENT_KEY_PAIR, CLIENT_ID, TOKEN_ENDPOINT, Instant.now().plusSeconds(120));

        ResponseEntity<Map> tokenResp =
                client.post()
                        .uri(baseUrl() + "/oauth2/token")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .body(tokenRequestBody(assertion))
                        .retrieve()
                        .toEntity(Map.class);

        assertThat(tokenResp.getStatusCode().value()).isEqualTo(200);
        String accessToken = (String) tokenResp.getBody().get("access_token");
        assertThat(accessToken).isNotBlank();
        assertThat(tokenResp.getBody().get("token_type")).isEqualTo("bearer");

        ResponseEntity<String> proxied =
                client.get()
                        .uri(baseUrl() + "/fhir/Patient/123")
                        .header("Authorization", "Bearer " + accessToken)
                        .retrieve()
                        .toEntity(String.class);

        assertThat(proxied.getStatusCode().value()).isEqualTo(200);
        assertThat(proxied.getBody()).contains("Patient");
        assertThat(stubCalls.get()).isEqualTo(before + 1); // stubCalls is shared across test methods
    }

    @Test
    void tokenViaApikeyHeader_isAcceptedAsAFallbackToAuthorizationBearer() throws Exception {
        // Decision E15: triage-service's FHIR client can only ever send an `apikey` header (Kong
        // convention), never an arbitrary `Authorization` header -- this is what makes the M5
        // acceptance case possible without editing triage-service at all.
        String assertion =
                signedAssertion(
                        CLIENT_KEY_PAIR, CLIENT_ID, TOKEN_ENDPOINT, Instant.now().plusSeconds(120));
        String accessToken =
                (String)
                        client.post()
                                .uri(baseUrl() + "/oauth2/token")
                                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                                .body(tokenRequestBody(assertion))
                                .retrieve()
                                .body(Map.class)
                                .get("access_token");

        ResponseEntity<String> proxied =
                client.get()
                        .uri(baseUrl() + "/fhir/Patient/123")
                        .header("apikey", accessToken)
                        .retrieve()
                        .toEntity(String.class);

        assertThat(proxied.getStatusCode().value()).isEqualTo(200);
        assertThat(proxied.getBody()).contains("Patient");
    }

    @Test
    void noAuthorizationHeader_isRejected_beforeReachingFhirService() {
        int before = stubCalls.get();

        assertThat(
                        org.assertj.core.api.Assertions.catchThrowable(
                                () ->
                                        client.get()
                                                .uri(baseUrl() + "/fhir/Patient/123")
                                                .retrieve()
                                                .toEntity(String.class)))
                .isInstanceOfSatisfying(
                        HttpClientErrorException.class,
                        e -> assertThat(e.getStatusCode().value()).isEqualTo(401));

        assertThat(stubCalls.get()).isEqualTo(before); // never reached fhir-service
    }

    @Test
    void garbageBearerToken_isRejected_beforeReachingFhirService() {
        int before = stubCalls.get();

        assertThat(
                        org.assertj.core.api.Assertions.catchThrowable(
                                () ->
                                        client.get()
                                                .uri(baseUrl() + "/fhir/Patient/123")
                                                .header("Authorization", "Bearer not-a-real-token")
                                                .retrieve()
                                                .toEntity(String.class)))
                .isInstanceOfSatisfying(
                        HttpClientErrorException.class,
                        e -> assertThat(e.getStatusCode().value()).isEqualTo(401));

        assertThat(stubCalls.get()).isEqualTo(before);
    }

    @Test
    void expiredClientAssertion_isRejectedAtTheTokenEndpoint() throws Exception {
        String assertion =
                signedAssertion(
                        CLIENT_KEY_PAIR, CLIENT_ID, TOKEN_ENDPOINT, Instant.now().minusSeconds(60));

        HttpClientErrorException ex =
                org.junit.jupiter.api.Assertions.assertThrows(
                        HttpClientErrorException.class,
                        () ->
                                client.post()
                                        .uri(baseUrl() + "/oauth2/token")
                                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                                        .body(tokenRequestBody(assertion))
                                        .retrieve()
                                        .toEntity(Map.class));

        assertThat(ex.getStatusCode().value()).isEqualTo(400);
        assertThat(ex.getResponseBodyAsString()).contains("invalid_grant");
    }

    @Test
    void wrongSigningKey_isRejectedAtTheTokenEndpoint() throws Exception {
        RSAKey imposterKey = new RSAKeyGenerator(2048).keyID(CLIENT_ID).generate();
        String assertion =
                signedAssertion(
                        imposterKey, CLIENT_ID, TOKEN_ENDPOINT, Instant.now().plusSeconds(120));

        HttpClientErrorException ex =
                org.junit.jupiter.api.Assertions.assertThrows(
                        HttpClientErrorException.class,
                        () ->
                                client.post()
                                        .uri(baseUrl() + "/oauth2/token")
                                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                                        .body(tokenRequestBody(assertion))
                                        .retrieve()
                                        .toEntity(Map.class));

        assertThat(ex.getStatusCode().value()).isEqualTo(400);
        assertThat(ex.getResponseBodyAsString()).contains("invalid_client");
    }

    @Test
    void unknownClientId_isRejectedAtTheTokenEndpoint() throws Exception {
        RSAKey strangerKey = new RSAKeyGenerator(2048).keyID("nobody").generate();
        String assertion =
                signedAssertion(strangerKey, "nobody", TOKEN_ENDPOINT, Instant.now().plusSeconds(120));

        HttpClientErrorException ex =
                org.junit.jupiter.api.Assertions.assertThrows(
                        HttpClientErrorException.class,
                        () ->
                                client.post()
                                        .uri(baseUrl() + "/oauth2/token")
                                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                                        .body(tokenRequestBody(assertion))
                                        .retrieve()
                                        .toEntity(Map.class));

        assertThat(ex.getStatusCode().value()).isEqualTo(400);
        assertThat(ex.getResponseBodyAsString()).contains("invalid_client");
    }
}
