package com.healthcare.epic.proxy;

import jakarta.servlet.http.HttpServletRequest;
import java.io.IOException;
import java.util.Collections;
import java.util.Locale;
import java.util.Set;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RestController;

/**
 * M1 pass-through core (PRD FR1): forwards every request to {@code fhir-service} unchanged and
 * returns its response unchanged. Later milestones add auth/extension/quirk interceptors around
 * this same entry point (design.md &sect;1) — this class stays the one that knows nothing special
 * about Epic.
 *
 * <p>Deliberately does not claim {@code /actuator/**}: Spring Boot's actuator handler mapping is
 * registered ahead of ordinary {@code @RestController} mappings, so health/info stay served
 * locally rather than being forwarded upstream (verified by
 * {@code FhirProxyIntegrationTest#actuatorHealthEndpoint_isHandledLocally_notProxied}).
 */
@RestController
public class FhirProxyController {

    private static final Set<String> HOP_BY_HOP =
            Set.of("host", "content-length", "connection", "transfer-encoding");

    private final FhirProxyClient client;

    public FhirProxyController(FhirProxyClient client) {
        this.client = client;
    }

    @RequestMapping(
            value = "/**",
            method = {
                RequestMethod.GET,
                RequestMethod.POST,
                RequestMethod.PUT,
                RequestMethod.DELETE,
                RequestMethod.PATCH,
                RequestMethod.HEAD
            })
    public ResponseEntity<byte[]> proxy(
            HttpServletRequest request, @RequestBody(required = false) byte[] body)
            throws IOException, InterruptedException {
        String pathAndQuery =
                request.getRequestURI()
                        + (request.getQueryString() != null ? "?" + request.getQueryString() : "");

        HttpHeaders requestHeaders = new HttpHeaders();
        Collections.list(request.getHeaderNames())
                .forEach(
                        name -> {
                            if (!HOP_BY_HOP.contains(name.toLowerCase(Locale.ROOT))) {
                                Collections.list(request.getHeaders(name))
                                        .forEach(v -> requestHeaders.add(name, v));
                            }
                        });

        FhirProxyClient.ProxiedResponse upstream =
                client.forward(request.getMethod(), pathAndQuery, requestHeaders, body);

        HttpHeaders responseHeaders = new HttpHeaders();
        upstream
                .headers()
                .forEach(
                        (name, values) -> {
                            if (!HOP_BY_HOP.contains(name.toLowerCase(Locale.ROOT))) {
                                values.forEach(v -> responseHeaders.add(name, v));
                            }
                        });

        return ResponseEntity.status(upstream.status())
                .headers(responseHeaders)
                .body(upstream.body());
    }
}
