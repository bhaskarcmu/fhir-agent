package com.payer.claims.domain;

/**
 * Finding severity (Decision Contract, R17). Ordinal is the precedence rank used both to
 * resolve the outcome (first non-empty tier wins) and to sort the reason list deterministically.
 */
public enum Severity {
    DENY,    // hard denial
    PEND,    // needs PA / more info
    REVIEW,  // route to manual review
    INFO     // annotation only; never changes the outcome
}
