package com.healthcare.epic.quirks;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.charset.StandardCharsets;

/**
 * Epic-shaped {@code OperationOutcome} error body for rejections {@code epic-emulator} itself
 * generates on the FHIR API surface (design.md §6, quirk C; PRD FR6) — the required-search-
 * parameter rejection (quirk B) and the bearer-auth gate's rejection (M2). The error-code system
 * is a same-repo placeholder, not a real Epic URI — decision E10 remains partial.
 *
 * <p>Deliberately <b>not</b> used for the OAuth token endpoint's own errors ({@code
 * TokenController}) — those are a different protocol layer with their own standard OAuth2
 * error shape (`error`/`error_description`); wrapping an OAuth response in a FHIR resource would
 * be a category mismatch, not a faithful Epic emulation.
 */
public final class EpicOperationOutcome {

    public static final String ERROR_CODE_SYSTEM = "http://epic-emulator.local/fhir/error-codes";

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private EpicOperationOutcome() {}

    public static byte[] json(String epicErrorCode, String diagnostics) {
        ObjectNode root = MAPPER.createObjectNode();
        root.put("resourceType", "OperationOutcome");
        ObjectNode issue = root.putArray("issue").addObject();
        issue.put("severity", "error");
        issue.put("code", "processing");
        ObjectNode coding = issue.putObject("details").putArray("coding").addObject();
        coding.put("system", ERROR_CODE_SYSTEM);
        coding.put("code", epicErrorCode);
        issue.put("diagnostics", diagnostics);
        try {
            return MAPPER.writeValueAsBytes(root);
        } catch (Exception e) {
            // This fixed, small shape cannot realistically fail to serialize; fall back to a
            // minimal valid OperationOutcome rather than let a rejection response 500 instead.
            return "{\"resourceType\":\"OperationOutcome\"}".getBytes(StandardCharsets.UTF_8);
        }
    }
}
