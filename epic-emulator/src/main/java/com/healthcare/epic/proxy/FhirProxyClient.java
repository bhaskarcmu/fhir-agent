package com.healthcare.epic.proxy;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;

/**
 * The one class that knows how to reach {@code fhir-service}. Forwards a request byte-for-byte
 * and returns the upstream status/headers/body unchanged — the M1 pass-through core that later
 * milestones (auth, extensions, quirks) layer interceptors around, per design.md &sect;1/&sect;9.
 *
 * <p>{@code fhir.base-url} is the server root (no {@code /fhir} suffix) — the incoming request's
 * own path (e.g. {@code /fhir/Patient}) is forwarded verbatim, so pointing a consumer's FHIR base
 * URL at this service instead of {@code fhir-service} directly needs no path rewriting (PRD UC1).
 */
@Component
public class FhirProxyClient {

    /**
     * Headers that are connection-specific and must never be copied verbatim in either
     * direction: {@link java.net.http.HttpClient} refuses to set these as request headers
     * (they are "restricted"), and blindly copying them from the upstream response would
     * corrupt framing (a stale Content-Length/Transfer-Encoding for a body we've already read
     * into memory).
     */
    private static final Set<String> HOP_BY_HOP =
            Set.of("host", "content-length", "connection", "transfer-encoding");

    private final HttpClient http =
            HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(5))
                    .build();
    private final String baseUrl;

    public FhirProxyClient(@Value("${fhir.base-url:http://localhost:8080}") String baseUrl) {
        this.baseUrl = baseUrl.replaceAll("/+$", "");
    }

    /** The upstream's response, unmodified: status, headers (minus hop-by-hop), and raw body. */
    public record ProxiedResponse(int status, Map<String, List<String>> headers, byte[] body) {}

    public ProxiedResponse forward(
            String method, String pathAndQuery, HttpHeaders requestHeaders, byte[] body)
            throws IOException, InterruptedException {
        HttpRequest.Builder builder =
                HttpRequest.newBuilder(URI.create(baseUrl + pathAndQuery))
                        .timeout(Duration.ofSeconds(30));
        for (Map.Entry<String, List<String>> entry : requestHeaders.entrySet()) {
            String name = entry.getKey();
            if (HOP_BY_HOP.contains(name.toLowerCase(Locale.ROOT))) {
                continue;
            }
            for (String value : entry.getValue()) {
                try {
                    builder.header(name, value);
                } catch (IllegalArgumentException restrictedByHttpClient) {
                    // java.net.http.HttpClient refuses a broader, undocumented-as-a-fixed-list
                    // set of connection-management headers beyond HOP_BY_HOP (e.g. "Upgrade"
                    // from an HTTP/2-upgrade-capable caller) — skip rather than enumerate every
                    // JDK-restricted name ourselves and risk drifting from it on a JDK upgrade.
                }
            }
        }

        HttpRequest.BodyPublisher publisher =
                (body == null || body.length == 0)
                        ? HttpRequest.BodyPublishers.noBody()
                        : HttpRequest.BodyPublishers.ofByteArray(body);
        builder.method(method, publisher);

        HttpResponse<byte[]> resp =
                http.send(builder.build(), HttpResponse.BodyHandlers.ofByteArray());

        Map<String, List<String>> responseHeaders = new LinkedHashMap<>();
        resp.headers()
                .map()
                .forEach(
                        (name, values) -> {
                            if (!HOP_BY_HOP.contains(name.toLowerCase(Locale.ROOT))) {
                                responseHeaders.put(name, values);
                            }
                        });

        return new ProxiedResponse(resp.statusCode(), responseHeaders, resp.body());
    }
}
