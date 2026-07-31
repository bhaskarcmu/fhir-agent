package com.healthcare.epic.proxy;

import com.healthcare.epic.extensions.ExtensionBackfillInterceptor;
import com.healthcare.epic.quirks.EpicOperationOutcome;
import com.healthcare.epic.quirks.PaginationRewriter;
import com.healthcare.epic.quirks.RequiredSearchParameterInterceptor;
import jakarta.servlet.http.HttpServletRequest;
import java.io.IOException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RestController;

/**
 * M1 pass-through core (PRD FR1): forwards every request to {@code fhir-service} unchanged and
 * returns its response unchanged, except where an in-scope quirk (§6) or the extension backfill
 * (§5) deliberately changes it. Each is an independent, composable step around this one entry
 * point (design.md §9) — this class coordinates them, it doesn't implement any of them itself.
 *
 * <p>Deliberately does not claim {@code /actuator/**} or {@code /oauth2/token}: Spring routes
 * more specific mappings there first, so this catch-all never sees them.
 */
@RestController
public class FhirProxyController {

    private final FhirProxyClient client;
    private final ExtensionBackfillInterceptor extensionBackfill;
    private final RequiredSearchParameterInterceptor requiredSearchParams;
    private final PaginationRewriter pagination;

    public FhirProxyController(
            FhirProxyClient client,
            ExtensionBackfillInterceptor extensionBackfill,
            RequiredSearchParameterInterceptor requiredSearchParams,
            PaginationRewriter pagination) {
        this.client = client;
        this.extensionBackfill = extensionBackfill;
        this.requiredSearchParams = requiredSearchParams;
        this.pagination = pagination;
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
        String method = request.getMethod();
        String path = request.getRequestURI();
        String queryString = request.getQueryString();

        // Quirk B: reject before ever calling fhir-service — nothing downstream needed this
        // stricter rule, Epic's search API just enforces it.
        RequiredSearchParameterInterceptor.Check paramCheck =
                requiredSearchParams.check(method, path, queryString);
        if (paramCheck instanceof RequiredSearchParameterInterceptor.Check.Rejected rejected) {
            return ResponseEntity.status(400)
                    .contentType(MediaType.valueOf("application/fhir+json"))
                    .body(EpicOperationOutcome.json(rejected.epicErrorCode(), rejected.diagnostics()));
        }

        // Quirk A (request side): cap/inject _count on in-scope searches before forwarding.
        String effectiveQuery =
                pagination.isInScopeSearch(method, path) ? pagination.capCount(queryString) : queryString;
        String pathAndQuery = path + (effectiveQuery != null && !effectiveQuery.isEmpty() ? "?" + effectiveQuery : "");

        HttpHeaders requestHeaders = ProxyHeaders.copyRequestHeaders(request);

        FhirProxyClient.ProxiedResponse upstream = client.forward(method, pathAndQuery, requestHeaders, body);

        HttpHeaders responseHeaders = ProxyHeaders.copyResponseHeaders(upstream.headers());
        String contentType = responseHeaders.getFirst(HttpHeaders.CONTENT_TYPE);

        byte[] responseBody = extensionBackfill.applyIfNeeded(method, contentType, upstream.body());
        // Quirk A (response side): opaque-token the next link, if this response has one.
        responseBody = pagination.rewriteNextLinkIfPresent(contentType, responseBody);

        return ResponseEntity.status(upstream.status()).headers(responseHeaders).body(responseBody);
    }
}
