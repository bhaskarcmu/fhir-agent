package com.healthcare.epic.proxy;

import jakarta.servlet.http.HttpServletRequest;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import org.springframework.http.HttpHeaders;

/**
 * Shared hop-by-hop header filtering for anything that proxies a request/response — used by both
 * {@link FhirProxyController} and quirk A's pagination continuation controller.
 */
public final class ProxyHeaders {

    private static final Set<String> HOP_BY_HOP =
            Set.of("host", "content-length", "connection", "transfer-encoding");

    private ProxyHeaders() {}

    public static HttpHeaders copyRequestHeaders(HttpServletRequest request) {
        HttpHeaders headers = new HttpHeaders();
        Collections.list(request.getHeaderNames())
                .forEach(
                        name -> {
                            if (!HOP_BY_HOP.contains(name.toLowerCase(Locale.ROOT))) {
                                Collections.list(request.getHeaders(name))
                                        .forEach(v -> headers.add(name, v));
                            }
                        });
        return headers;
    }

    public static HttpHeaders copyResponseHeaders(Map<String, List<String>> upstreamHeaders) {
        HttpHeaders headers = new HttpHeaders();
        upstreamHeaders.forEach(
                (name, values) -> {
                    if (!HOP_BY_HOP.contains(name.toLowerCase(Locale.ROOT))) {
                        values.forEach(v -> headers.add(name, v));
                    }
                });
        return headers;
    }
}
