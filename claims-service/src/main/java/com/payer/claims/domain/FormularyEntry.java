package com.payer.claims.domain;

/** A formulary row from the payer KB, keyed by (planId, rxcui). Mirrors formulary.csv. */
public record FormularyEntry(
        String planId,
        String rxcui,
        String drug,
        String tier,
        boolean priorAuth,
        boolean stepTherapy,
        boolean quantityLimit,
        Integer quantityLimitQty,   // parsed cap (e.g. 30); null if none/unparseable
        boolean covered) {
}
