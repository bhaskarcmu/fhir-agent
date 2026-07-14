package com.payer.claims.domain;

/**
 * A single rule outcome (Decision Contract, R17.2). Rules emit zero or more of these; the
 * engine aggregates and resolves them.
 *
 * @param ruleId   stable rule id (e.g. "PA-REQUIRED")
 * @param domain   pipeline domain (drives deterministic ordering, R17.4)
 * @param severity DENY / PEND / REVIEW / INFO
 * @param code     coded reason (e.g. "prior-auth-required")
 * @param message  human-readable explanation
 */
public record Finding(String ruleId, String domain, Severity severity, String code, String message) {
    public static Finding of(String ruleId, String domain, Severity severity, String code, String message) {
        return new Finding(ruleId, domain, severity, code, message);
    }
}
