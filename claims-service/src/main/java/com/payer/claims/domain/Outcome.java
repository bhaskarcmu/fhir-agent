package com.payer.claims.domain;

/** Adjudication outcome (Decision Contract, R17.1). */
public enum Outcome {
    APPROVED,
    DENIED,
    PENDED,
    ROUTED_FOR_REVIEW
}
