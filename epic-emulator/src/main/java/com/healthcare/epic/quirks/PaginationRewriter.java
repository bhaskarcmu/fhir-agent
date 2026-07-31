package com.healthcare.epic.quirks;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.IOException;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * Quirk A (design.md §6): caps the effective {@code _count} on in-scope searches regardless of
 * what the caller requests, and replaces any {@code Bundle.link[relation=next].url} with an
 * opaque, emulator-issued continuation token — the caller must follow it verbatim rather than
 * construct its own offset. Scoped to the same two resource types as M3's extension handling
 * (`MedicationRequest`, `AllergyIntolerance`), matching "the resource type exercised by the
 * acceptance scenario" (design.md §6's original wording).
 */
@Component
public class PaginationRewriter {

    private final ObjectMapper mapper = new ObjectMapper();
    private final Map<String, String> pageTokens = new ConcurrentHashMap<>();
    private final SecureRandom random = new SecureRandom();
    private final int maxCount;

    public PaginationRewriter(@Value("${epic.quirks.pagination.max-count:20}") int maxCount) {
        this.maxCount = maxCount;
    }

    public boolean isInScopeSearch(String method, String path) {
        return "GET".equalsIgnoreCase(method)
                && ("/fhir/MedicationRequest".equals(path) || "/fhir/AllergyIntolerance".equals(path));
    }

    /**
     * Rewrites the outgoing query string so the effective {@code _count} never exceeds the cap —
     * clamped down if the caller asked for more, or injected outright if the caller didn't ask
     * for a count at all (fhir-service's own default page size is not assumed to already match
     * the cap).
     */
    public String capCount(String queryString) {
        LinkedHashMap<String, String> params = parseQuery(queryString);
        int effective = maxCount;
        String requested = params.get("_count");
        if (requested != null) {
            try {
                effective = Math.min(maxCount, Integer.parseInt(requested));
            } catch (NumberFormatException notANumber) {
                effective = maxCount;
            }
        }
        params.put("_count", String.valueOf(effective));
        return rebuildQuery(params);
    }

    /** If the response is a Bundle with a next link, replaces its url with an opaque token url. */
    public byte[] rewriteNextLinkIfPresent(String contentType, byte[] body) {
        if (contentType == null
                || !contentType.toLowerCase(Locale.ROOT).contains("json")
                || body == null
                || body.length == 0) {
            return body;
        }
        JsonNode root;
        try {
            root = mapper.readTree(body);
        } catch (IOException notJson) {
            return body;
        }
        if (root == null || !"Bundle".equals(root.path("resourceType").asText(""))) {
            return body;
        }
        JsonNode links = root.path("link");
        if (!links.isArray()) {
            return body;
        }

        boolean changed = false;
        for (JsonNode link : links) {
            if (link.isObject()
                    && "next".equals(link.path("relation").asText(""))
                    && link.has("url")) {
                String realUrl = link.path("url").asText();
                String token = issueToken(realUrl);
                ((ObjectNode) link).put("url", "/fhir/_page/" + token);
                changed = true;
            }
        }
        if (!changed) {
            return body;
        }
        try {
            return mapper.writeValueAsBytes(root);
        } catch (IOException cannotReserialize) {
            return body;
        }
    }

    public Optional<String> resolve(String token) {
        return Optional.ofNullable(pageTokens.get(token));
    }

    private String issueToken(String realUrl) {
        byte[] bytes = new byte[16];
        random.nextBytes(bytes);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        pageTokens.put(token, realUrl);
        return token;
    }

    private static LinkedHashMap<String, String> parseQuery(String queryString) {
        LinkedHashMap<String, String> params = new LinkedHashMap<>();
        if (queryString != null && !queryString.isBlank()) {
            for (String pair : queryString.split("&")) {
                int eq = pair.indexOf('=');
                if (eq >= 0) {
                    params.put(pair.substring(0, eq), pair.substring(eq + 1));
                } else {
                    params.put(pair, "");
                }
            }
        }
        return params;
    }

    private static String rebuildQuery(LinkedHashMap<String, String> params) {
        StringBuilder rebuilt = new StringBuilder();
        for (Map.Entry<String, String> entry : params.entrySet()) {
            if (rebuilt.length() > 0) {
                rebuilt.append('&');
            }
            rebuilt.append(entry.getKey()).append('=').append(entry.getValue());
        }
        return rebuilt.toString();
    }
}
