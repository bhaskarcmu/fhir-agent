package com.payer.claims;

import static org.assertj.core.api.Assertions.assertThat;

import com.payer.claims.acl.LegacyAdapter;
import com.payer.claims.domain.AdjudicationDecision;
import com.payer.claims.domain.CanonicalClaim;
import com.payer.claims.domain.FormularyEntry;
import com.payer.claims.domain.Outcome;
import com.payer.claims.domain.RiskLevel;
import com.payer.claims.fhir.FhirArtifactBuilder;
import com.payer.claims.fhir.FhirClient;
import com.payer.claims.kb.PayerKb;
import com.payer.claims.pipeline.AdjudicationPipeline;
import com.payer.claims.pipeline.AdjudicationService;
import com.payer.claims.rules.RulesEngine;
import java.time.LocalDate;
import java.util.List;
import java.util.Optional;
import org.hl7.fhir.r4.model.Bundle;
import org.junit.jupiter.api.Test;

/** Intake idempotency: a re-submitted claim returns the prior decision and is not re-persisted. */
class AdjudicationServiceTest {

    private static final String PAID = "P0000000240000000150000024150000004830000019320RX1707784510";

    /** In-memory FHIR client: remembers whether a decision was persisted; counts submits. */
    static final class FakeFhir implements FhirClient {
        int submits = 0;
        boolean persisted = false;

        @Override public void submit(Bundle tx) {
            submits++;
            persisted = true;
        }
        @Override public Optional<AdjudicationDecision> existingDecision(String decisionId) {
            return persisted
                    ? Optional.of(new AdjudicationDecision(decisionId, Outcome.APPROVED,
                            List.of(), List.of(), null))
                    : Optional.empty();
        }
        @Override public Optional<String> resolvePatientId(String memberId) {
            return Optional.empty();
        }
    }

    private static CanonicalClaim claim() {
        return new CanonicalClaim("C1", "000000001", "COM-SILVER", "29046", "51655-999",
                "lisinopril", 30, 30, LocalDate.of(2026, 6, 1), "1234567890",
                LocalDate.of(2026, 1, 1), LocalDate.of(2026, 12, 31), false, false);
    }

    @Test
    void resubmittingSameClaim_returnsPriorDecision_andDoesNotPersistTwice() {
        FormularyEntry covered = new FormularyEntry("COM-SILVER", "29046", "lisinopril",
                "PREFERRED-GENERIC", false, false, false, null, true);
        PayerKb kb = (planId, rxcui) -> Optional.of(covered);
        FakeFhir fhir = new FakeFhir();
        AdjudicationPipeline pipeline = new AdjudicationPipeline(
                kb, new RulesEngine(), (c, p) -> RiskLevel.LOW, record -> PAID, new LegacyAdapter(), fhir);
        AdjudicationService service =
                new AdjudicationService(pipeline, new FhirArtifactBuilder(), fhir);

        AdjudicationDecision first = service.adjudicateAndPersist(claim());
        AdjudicationDecision second = service.adjudicateAndPersist(claim()); // retry

        assertThat(first.outcome()).isEqualTo(Outcome.APPROVED);
        assertThat(second.decisionId()).isEqualTo(first.decisionId());
        assertThat(fhir.submits).isEqualTo(1); // persisted once; retry short-circuited
    }
}
