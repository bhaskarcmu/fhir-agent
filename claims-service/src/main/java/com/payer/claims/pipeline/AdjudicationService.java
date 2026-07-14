package com.payer.claims.pipeline;

import com.payer.claims.domain.AdjudicationDecision;
import com.payer.claims.domain.CanonicalClaim;
import com.payer.claims.fhir.FhirArtifactBuilder;
import com.payer.claims.fhir.FhirClient;
import java.util.Optional;
import org.springframework.stereotype.Service;

/**
 * Adjudicate + persist. Applies intake idempotency (return the prior decision if this id was
 * already adjudicated), then persists the decision as an atomic, idempotent FHIR artefact graph
 * (R18). Deterministic input ⇒ deterministic decision ⇒ stable artefacts.
 */
@Service
public class AdjudicationService {

    private final AdjudicationPipeline pipeline;
    private final FhirArtifactBuilder builder;
    private final FhirClient fhir;

    public AdjudicationService(AdjudicationPipeline pipeline, FhirArtifactBuilder builder,
                               FhirClient fhir) {
        this.pipeline = pipeline;
        this.builder = builder;
        this.fhir = fhir;
    }

    public AdjudicationDecision adjudicateAndPersist(CanonicalClaim claim) {
        String decisionId = "DEC-" + claim.claimId();

        // R18.3 intake idempotency: a retry returns the already-persisted decision, no re-work.
        Optional<AdjudicationDecision> prior = fhir.existingDecision(decisionId);
        if (prior.isPresent()) {
            return prior.get();
        }

        AdjudicationDecision decision = pipeline.adjudicate(claim);
        // Atomic (R18.4) + conditional-create idempotent (R18.3): no partial or duplicate graph.
        fhir.submit(builder.buildTransaction(claim, decision));
        return decision;
    }
}
