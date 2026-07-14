package com.payer.claims.kb;

import com.payer.claims.domain.FormularyEntry;
import java.util.Optional;

/**
 * Payer knowledge-base lookup — the C3 repository seam. File-backed today; a Postgres or
 * NoSQL (Bigtable/Firestore) implementation is a drop-in swap behind this interface, never a
 * rewrite. The access pattern is the high-cardinality key-value lookup {@code (planId, rxcui)}.
 */
public interface PayerKb {
    Optional<FormularyEntry> formularyEntry(String planId, String rxcui);
}
