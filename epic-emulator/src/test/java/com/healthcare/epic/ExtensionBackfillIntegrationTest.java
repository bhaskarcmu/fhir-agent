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
 * Verifies the M3 definition of done (PRD FR3, design.md §12): a read returns the expected Epic
 * extension even on unmodified seeded data, and a write containing the extension round-trips
 * correctly. Also proves the backfill is idempotent (never duplicated) and scoped only to
 * {@code MedicationRequest}/{@code AllergyIntolerance} (design.md §5, decision E12) — an
 * unrelated resource type (Patient here) is returned untouched, byte-for-byte.
 *
 * <p>The stub "fhir-service" is configurable per test via a request-path-keyed response map,
 * rather than one fixed body like M1/M2's stubs — extension tests need several different shapes
 * (bare resource, Bundle, out-of-scope resource, pre-extended resource) from the same server.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ExtensionBackfillIntegrationTest {

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
    private static final Map<String, String> stubResponsesByPath = new java.util.concurrent.ConcurrentHashMap<>();

    @BeforeAll
    static void startStubFhirService() throws IOException {
        stubFhir = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        stubFhir.createContext(
                "/",
                ex -> {
                    String path = ex.getRequestURI().getPath();
                    String body = stubResponsesByPath.get(path);
                    byte[] out =
                            (body != null ? body : "{\"resourceType\":\"OperationOutcome\"}")
                                    .getBytes(StandardCharsets.UTF_8);
                    ex.getResponseHeaders().add("Content-Type", "application/fhir+json");
                    ex.sendResponseHeaders(body != null ? 200 : 404, out.length);
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

    private String getWithToken(String path) throws Exception {
        String token = fetchAccessToken();
        ResponseEntity<String> resp =
                client.get()
                        .uri(baseUrl() + path)
                        .header("Authorization", "Bearer " + token)
                        .retrieve()
                        .toEntity(String.class);
        return resp.getBody();
    }

    @Test
    void bareMedicationRequest_missingExtension_getsBackfilled() throws Exception {
        stubResponsesByPath.put(
                "/fhir/MedicationRequest/1",
                "{\"resourceType\":\"MedicationRequest\",\"id\":\"1\"}");

        JsonNode result = MAPPER.readTree(getWithToken("/fhir/MedicationRequest/1"));

        assertThat(result.path("extension")).hasSize(1);
        assertThat(result.path("extension").get(0).path("url").asText())
                .isEqualTo("http://epic-emulator.local/fhir/extensions/medication-therapy-class");
        assertThat(result.path("extension").get(0).path("valueString").asText())
                .isEqualTo("synthetic-epic-emulator-backfill");
    }

    @Test
    void bareAllergyIntolerance_missingExtension_getsBackfilled() throws Exception {
        stubResponsesByPath.put(
                "/fhir/AllergyIntolerance/2",
                "{\"resourceType\":\"AllergyIntolerance\",\"id\":\"2\"}");

        JsonNode result = MAPPER.readTree(getWithToken("/fhir/AllergyIntolerance/2"));

        assertThat(result.path("extension")).hasSize(1);
        assertThat(result.path("extension").get(0).path("url").asText())
                .isEqualTo("http://epic-emulator.local/fhir/extensions/allergy-source-system");
    }

    @Test
    void alreadyExtendedResource_isNotDuplicated() throws Exception {
        stubResponsesByPath.put(
                "/fhir/MedicationRequest/3",
                "{\"resourceType\":\"MedicationRequest\",\"id\":\"3\",\"extension\":"
                        + "[{\"url\":\"http://epic-emulator.local/fhir/extensions/medication-therapy-class\","
                        + "\"valueString\":\"already-here\"}]}");

        JsonNode result = MAPPER.readTree(getWithToken("/fhir/MedicationRequest/3"));

        assertThat(result.path("extension")).hasSize(1);
        assertThat(result.path("extension").get(0).path("valueString").asText())
                .isEqualTo("already-here"); // untouched, not overwritten
    }

    @Test
    void outOfScopeResourceType_isReturnedByteForByte_untouched() throws Exception {
        String original = "{\"resourceType\":\"Patient\",\"id\":\"4\"}";
        stubResponsesByPath.put("/fhir/Patient/4", original);

        String result = getWithToken("/fhir/Patient/4");

        assertThat(result).isEqualTo(original); // no extension array added, no reformatting
    }

    @Test
    void searchBundle_backfillsOnlyInScopeEntries() throws Exception {
        stubResponsesByPath.put(
                "/fhir/MedicationRequest",
                "{\"resourceType\":\"Bundle\",\"type\":\"searchset\",\"entry\":["
                        + "{\"resource\":{\"resourceType\":\"MedicationRequest\",\"id\":\"5\"}},"
                        + "{\"resource\":{\"resourceType\":\"AllergyIntolerance\",\"id\":\"6\"}},"
                        + "{\"resource\":{\"resourceType\":\"Patient\",\"id\":\"7\"}}"
                        + "]}");

        JsonNode bundle = MAPPER.readTree(getWithToken("/fhir/MedicationRequest"));
        JsonNode entries = bundle.path("entry");

        assertThat(entries.get(0).path("resource").path("extension")).hasSize(1);
        assertThat(entries.get(1).path("resource").path("extension")).hasSize(1);
        assertThat(entries.get(2).path("resource").has("extension")).isFalse(); // Patient untouched
    }

    @Test
    void writtenExtension_roundTripsUnchanged_proxyDoesNotTouchWrites() throws Exception {
        // The write path is unmodified pass-through (design.md §5) -- the proxy forwards a POST
        // body byte-for-byte regardless of resource type or extension content; fhir-service (the
        // stub, here) is solely responsible for what gets stored and returned on a later read.
        String token = fetchAccessToken();
        String written =
                "{\"resourceType\":\"MedicationRequest\",\"extension\":"
                        + "[{\"url\":\"http://epic-emulator.local/fhir/extensions/medication-therapy-class\","
                        + "\"valueString\":\"client-supplied\"}]}";
        AtomicReference<String> receivedByStub = new AtomicReference<>();
        stubFhir.createContext(
                "/fhir/MedicationRequestWrite",
                ex -> {
                    receivedByStub.set(
                            new String(ex.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
                    byte[] out = written.getBytes(StandardCharsets.UTF_8);
                    ex.getResponseHeaders().add("Content-Type", "application/fhir+json");
                    ex.sendResponseHeaders(201, out.length);
                    ex.getResponseBody().write(out);
                    ex.close();
                });

        client.post()
                .uri(baseUrl() + "/fhir/MedicationRequestWrite")
                .header("Authorization", "Bearer " + token)
                .contentType(MediaType.valueOf("application/fhir+json"))
                .body(written)
                .retrieve()
                .toBodilessEntity();

        assertThat(receivedByStub.get()).isEqualTo(written); // exactly what was sent, no rewrite
    }
}
