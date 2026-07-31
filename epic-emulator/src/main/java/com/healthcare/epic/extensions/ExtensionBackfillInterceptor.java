package com.healthcare.epic.extensions;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.IOException;
import org.springframework.stereotype.Component;

/**
 * Read-time backfill for {@code MedicationRequest}/{@code AllergyIntolerance} responses
 * (design.md §5): if a proxied {@code GET} response for one of these resource types — bare, or
 * inside a search-result {@code Bundle} — doesn't already carry the expected Epic-style
 * extension, add it before returning to the caller.
 *
 * <p>Writes are untouched by this class entirely — {@code fhir-service} already stores whatever
 * extensions a client sent, so once a caller writes one it round-trips on its own (PRD FR3).
 */
@Component
public class ExtensionBackfillInterceptor {

    private final ObjectMapper mapper = new ObjectMapper();

    /**
     * Returns {@code body} unchanged unless this is a JSON GET response containing an in-scope
     * resource (bare or in a Bundle) missing its Epic extension — in which case it returns a new
     * byte array with the extension added. Never throws: any parse failure is treated as "nothing
     * to backfill," not an error, since a broken body here would otherwise turn a successful
     * proxied response into a failed one.
     */
    public byte[] applyIfNeeded(String method, String contentType, byte[] body) {
        if (!"GET".equalsIgnoreCase(method)
                || contentType == null
                || !contentType.toLowerCase(java.util.Locale.ROOT).contains("json")
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
        if (root == null || !root.isObject()) {
            return body;
        }

        boolean changed = backfillIfInScope((ObjectNode) root);

        if ("Bundle".equals(root.path("resourceType").asText(""))) {
            JsonNode entries = root.path("entry");
            if (entries.isArray()) {
                for (JsonNode entry : entries) {
                    JsonNode resource = entry.path("resource");
                    if (resource.isObject() && backfillIfInScope((ObjectNode) resource)) {
                        changed = true;
                    }
                }
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

    /** Adds the resource type's Epic extension if it's in scope and not already present. */
    private boolean backfillIfInScope(ObjectNode resource) {
        String extensionUrl = EpicExtensions.extensionUrlFor(resource.path("resourceType").asText(""));
        if (extensionUrl == null) {
            return false;
        }

        ArrayNode extensions =
                resource.has("extension") && resource.get("extension").isArray()
                        ? (ArrayNode) resource.get("extension")
                        : resource.putArray("extension");
        for (JsonNode existing : extensions) {
            if (extensionUrl.equals(existing.path("url").asText(null))) {
                return false; // already present — idempotent, never duplicated
            }
        }

        ObjectNode newExtension = mapper.createObjectNode();
        newExtension.put("url", extensionUrl);
        newExtension.put("valueString", EpicExtensions.BACKFILL_VALUE);
        extensions.add(newExtension);
        return true;
    }
}
