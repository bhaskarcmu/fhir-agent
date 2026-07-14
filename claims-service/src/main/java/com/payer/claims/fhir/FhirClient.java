package com.payer.claims.fhir;

import com.payer.claims.domain.AdjudicationDecision;
import java.util.Optional;
import org.hl7.fhir.r4.model.Bundle;

/** Persistence boundary for the decision artefact graph. */
public interface FhirClient {

    /** Submit the transaction bundle (atomic; ifNoneExist makes it idempotent). */
    void submit(Bundle transaction);

    /** Intake idempotency (R18.3): a prior decision for this id, if already persisted. */
    Optional<AdjudicationDecision> existingDecision(String decisionId);
}
