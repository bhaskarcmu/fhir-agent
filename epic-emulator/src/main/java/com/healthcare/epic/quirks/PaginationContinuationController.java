package com.healthcare.epic.quirks;

import com.healthcare.epic.extensions.ExtensionBackfillInterceptor;
import com.healthcare.epic.proxy.FhirProxyClient;
import com.healthcare.epic.proxy.ProxyHeaders;
import jakarta.servlet.http.HttpServletRequest;
import java.io.IOException;
import java.util.Optional;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

/**
 * Resolves an opaque continuation token issued by {@link PaginationRewriter} back to
 * fhir-service's real next-page URL and forwards to it — the caller only ever sees this opaque
 * path, never fhir-service's own pagination URL shape (quirk A, design.md §6). More specific than
 * {@code FhirProxyController}'s catch-all, so Spring routes {@code /fhir/_page/{token}} here
 * rather than forwarding it upstream verbatim — same precedent as the actuator/token endpoints.
 */
@RestController
public class PaginationContinuationController {

    private final PaginationRewriter pagination;
    private final FhirProxyClient client;
    private final ExtensionBackfillInterceptor extensionBackfill;

    public PaginationContinuationController(
            PaginationRewriter pagination,
            FhirProxyClient client,
            ExtensionBackfillInterceptor extensionBackfill) {
        this.pagination = pagination;
        this.client = client;
        this.extensionBackfill = extensionBackfill;
    }

    @GetMapping("/fhir/_page/{token}")
    public ResponseEntity<byte[]> continuePage(
            @PathVariable String token, HttpServletRequest request)
            throws IOException, InterruptedException {
        Optional<String> realUrl = pagination.resolve(token);
        if (realUrl.isEmpty()) {
            return ResponseEntity.status(404)
                    .contentType(MediaType.valueOf("application/fhir+json"))
                    .body(
                            EpicOperationOutcome.json(
                                    "unknown-page-token",
                                    "This continuation token is unknown or has expired"));
        }

        HttpHeaders requestHeaders = ProxyHeaders.copyRequestHeaders(request);
        FhirProxyClient.ProxiedResponse upstream =
                client.forwardAbsolute("GET", realUrl.get(), requestHeaders);

        HttpHeaders responseHeaders = ProxyHeaders.copyResponseHeaders(upstream.headers());
        String contentType = responseHeaders.getFirst(HttpHeaders.CONTENT_TYPE);

        byte[] responseBody = extensionBackfill.applyIfNeeded("GET", contentType, upstream.body());
        // A third page is still possible — re-issue an opaque token for whatever next link this
        // page itself carries, same as the first hop.
        responseBody = pagination.rewriteNextLinkIfPresent(contentType, responseBody);

        return ResponseEntity.status(upstream.status()).headers(responseHeaders).body(responseBody);
    }
}
