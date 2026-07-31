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
import java.util.concurrent.atomic.AtomicReference;
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
import org.springframework.web.client.RestClient;

/**
 * Verifies the M1 definition of done (PRD FR1): an unmodified FHIR client gets byte-identical
 * behavior through {@code epic-emulator} as it would calling {@code fhir-service} directly.
 *
 * <p>Stands up a stub "fhir-service" with the JDK's own {@link HttpServer} — same
 * dependency-free pattern as {@code claims-service}'s {@code HttpTriageClientTest} — rather than
 * pulling in a mocking library for one proxy target.
 *
 * <p>Since M2, every proxied call is gated behind a bearer token (see
 * {@code AuthFlowIntegrationTest} for the auth flow itself) — the GET/POST tests here fetch a
 * real token first so this class keeps proving pass-through fidelity, not auth. The actuator
 * test deliberately sends no token, confirming health/info stayed exempt.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FhirProxyIntegrationTest {

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
    private static final AtomicReference<String> lastMethod = new AtomicReference<>();
    private static final AtomicReference<String> lastPath = new AtomicReference<>();
    private static final AtomicReference<String> lastBody = new AtomicReference<>();
    private static final AtomicReference<String> lastContentType = new AtomicReference<>();

    @BeforeAll
    static void startStubFhirService() throws IOException {
        stubFhir = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        stubFhir.createContext(
                "/",
                ex -> {
                    lastMethod.set(ex.getRequestMethod());
                    lastPath.set(ex.getRequestURI().toString());
                    lastContentType.set(ex.getRequestHeaders().getFirst("Content-Type"));
                    lastBody.set(
                            new String(ex.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
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

    /** Completes the JWT client-assertion flow once and returns a usable bearer token. */
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

    @Test
    void getRequest_forwardsPathAndQuery_andReturnsUpstreamResponseUnchanged() throws Exception {
        String token = fetchAccessToken();

        ResponseEntity<String> resp =
                client.get()
                        .uri(baseUrl() + "/fhir/Patient/123?_format=json")
                        .header("Authorization", "Bearer " + token)
                        .retrieve()
                        .toEntity(String.class);

        assertThat(resp.getStatusCode().value()).isEqualTo(200);
        assertThat(resp.getBody()).isEqualTo("{\"resourceType\":\"Patient\",\"id\":\"123\"}");
        assertThat(resp.getHeaders().getFirst("Content-Type")).contains("application/fhir+json");
        assertThat(lastMethod.get()).isEqualTo("GET");
        assertThat(lastPath.get()).isEqualTo("/fhir/Patient/123?_format=json");
    }

    @Test
    void postRequest_forwardsBodyAndContentType_unchanged() throws Exception {
        String token = fetchAccessToken();
        String body = "{\"resourceType\":\"Patient\"}";

        ResponseEntity<String> resp =
                client.post()
                        .uri(baseUrl() + "/fhir/Patient")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.valueOf("application/fhir+json"))
                        .body(body)
                        .retrieve()
                        .toEntity(String.class);

        assertThat(resp.getStatusCode().value()).isEqualTo(200);
        assertThat(lastMethod.get()).isEqualTo("POST");
        assertThat(lastPath.get()).isEqualTo("/fhir/Patient");
        assertThat(lastBody.get()).isEqualTo(body);
        assertThat(lastContentType.get()).isEqualTo("application/fhir+json");
    }

    @Test
    void actuatorHealthEndpoint_isHandledLocally_notProxied_andNeedsNoToken() {
        ResponseEntity<String> resp =
                client.get()
                        .uri(baseUrl() + "/actuator/health")
                        .retrieve()
                        .toEntity(String.class);

        assertThat(resp.getStatusCode().value()).isEqualTo(200);
        assertThat(resp.getBody()).contains("\"status\":\"UP\"");
        // If this had been forwarded to the stub instead, we'd see the stub's Patient JSON.
        assertThat(resp.getBody()).doesNotContain("resourceType");
    }
}
