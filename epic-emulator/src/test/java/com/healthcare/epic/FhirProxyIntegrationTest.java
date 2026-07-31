package com.healthcare.epic;

import static org.assertj.core.api.Assertions.assertThat;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
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
import org.springframework.web.client.RestClient;

/**
 * Verifies the M1 definition of done (PRD FR1): an unmodified FHIR client gets byte-identical
 * behavior through {@code epic-emulator} as it would calling {@code fhir-service} directly.
 *
 * <p>Stands up a stub "fhir-service" with the JDK's own {@link HttpServer} — same
 * dependency-free pattern as {@code claims-service}'s {@code HttpTriageClientTest} — rather than
 * pulling in a mocking library for one proxy target.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FhirProxyIntegrationTest {

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
    static void fhirBaseUrl(DynamicPropertyRegistry registry) {
        registry.add(
                "fhir.base-url", () -> "http://127.0.0.1:" + stubFhir.getAddress().getPort());
    }

    @LocalServerPort private int port;

    private final RestClient client = RestClient.create();

    @Test
    void getRequest_forwardsPathAndQuery_andReturnsUpstreamResponseUnchanged() {
        ResponseEntity<String> resp =
                client.get()
                        .uri("http://localhost:" + port + "/fhir/Patient/123?_format=json")
                        .retrieve()
                        .toEntity(String.class);

        assertThat(resp.getStatusCode().value()).isEqualTo(200);
        assertThat(resp.getBody()).isEqualTo("{\"resourceType\":\"Patient\",\"id\":\"123\"}");
        assertThat(resp.getHeaders().getFirst("Content-Type")).contains("application/fhir+json");
        assertThat(lastMethod.get()).isEqualTo("GET");
        assertThat(lastPath.get()).isEqualTo("/fhir/Patient/123?_format=json");
    }

    @Test
    void postRequest_forwardsBodyAndContentType_unchanged() {
        String body = "{\"resourceType\":\"Patient\"}";

        ResponseEntity<String> resp =
                client.post()
                        .uri("http://localhost:" + port + "/fhir/Patient")
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
    void actuatorHealthEndpoint_isHandledLocally_notProxied() {
        ResponseEntity<String> resp =
                client.get()
                        .uri("http://localhost:" + port + "/actuator/health")
                        .retrieve()
                        .toEntity(String.class);

        assertThat(resp.getStatusCode().value()).isEqualTo(200);
        assertThat(resp.getBody()).contains("\"status\":\"UP\"");
        // If this had been forwarded to the stub instead, we'd see the stub's Patient JSON.
        assertThat(resp.getBody()).doesNotContain("resourceType");
    }
}
