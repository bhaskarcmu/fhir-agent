package com.healthcare.epic.quirks;

import org.springframework.stereotype.Component;

/**
 * Quirk B (design.md §6): Epic requires a {@code MedicationRequest} search to include both
 * {@code patient} and {@code status} — a request with {@code patient} alone, which
 * fhir-service/base R4 would happily answer, is rejected. Read-by-id
 * ({@code /fhir/MedicationRequest/{id}}) is a different path and unaffected; this only applies to
 * the bare search path.
 */
@Component
public class RequiredSearchParameterInterceptor {

    private static final String SEARCH_PATH = "/fhir/MedicationRequest";

    public sealed interface Check {
        record Allowed() implements Check {}

        record Rejected(String epicErrorCode, String diagnostics) implements Check {}
    }

    public Check check(String method, String path, String queryString) {
        if (!"GET".equalsIgnoreCase(method) || !SEARCH_PATH.equals(path)) {
            return new Check.Allowed();
        }
        if (!hasParam(queryString, "patient") || !hasParam(queryString, "status")) {
            return new Check.Rejected(
                    "missing-required-search-parameter",
                    "Epic requires MedicationRequest search to include both 'patient' and "
                            + "'status'");
        }
        return new Check.Allowed();
    }

    private static boolean hasParam(String queryString, String name) {
        if (queryString == null || queryString.isBlank()) {
            return false;
        }
        for (String pair : queryString.split("&")) {
            String key = pair.contains("=") ? pair.substring(0, pair.indexOf('=')) : pair;
            if (key.equals(name)) {
                return true;
            }
        }
        return false;
    }
}
