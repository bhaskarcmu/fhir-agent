package com.payer.claims;

import static org.assertj.core.api.Assertions.assertThat;

import com.payer.claims.domain.AdjudicationDecision;
import com.payer.claims.domain.CanonicalClaim;
import com.payer.claims.domain.Finding;
import com.payer.claims.domain.Outcome;
import com.payer.claims.domain.Severity;
import com.payer.claims.fhir.FhirArtifactBuilder;
import java.time.LocalDate;
import java.util.List;
import org.hl7.fhir.r4.model.Bundle;
import org.hl7.fhir.r4.model.Claim;
import org.hl7.fhir.r4.model.ClaimResponse;
import org.hl7.fhir.r4.model.Provenance;
import org.hl7.fhir.r4.model.Resource;
import org.hl7.fhir.r4.model.RiskAssessment;
import org.hl7.fhir.r4.model.Task;
import org.junit.jupiter.api.Test;

class FhirArtifactBuilderTest {

    private final FhirArtifactBuilder builder = new FhirArtifactBuilder();

    private static final CanonicalClaim CLAIM = new CanonicalClaim(
            "C1", "000000001", "COM-SILVER", "29046", "51655-999", "lisinopril",
            30, 30, LocalDate.of(2026, 6, 1), "1234567890",
            LocalDate.of(2026, 1, 1), LocalDate.of(2026, 12, 31), false, false);

    private static <T extends Resource> T first(Bundle b, Class<T> type) {
        return b.getEntry().stream().map(Bundle.BundleEntryComponent::getResource)
                .filter(type::isInstance).map(type::cast).findFirst().orElse(null);
    }

    private static String fullUrlOf(Bundle b, Class<? extends Resource> type) {
        return b.getEntry().stream().filter(e -> type.isInstance(e.getResource()))
                .map(Bundle.BundleEntryComponent::getFullUrl).findFirst().orElse(null);
    }

    @Test
    void approved_buildsLinkedClaimResponseProvenance_idempotentAndTagged() {
        Bundle tx = builder.buildTransaction(CLAIM,
                new AdjudicationDecision("DEC-C1", Outcome.APPROVED, List.of(), List.of(), null));

        assertThat(tx.getType()).isEqualTo(Bundle.BundleType.TRANSACTION);
        assertThat(first(tx, Claim.class)).isNotNull();
        assertThat(first(tx, Task.class)).isNull();          // not routed
        assertThat(first(tx, RiskAssessment.class)).isNull(); // no clinical finding

        ClaimResponse cr = first(tx, ClaimResponse.class);
        assertThat(cr.getOutcome()).isEqualTo(ClaimResponse.RemittanceOutcome.COMPLETE);
        assertThat(cr.getDisposition()).isEqualTo("APPROVED");
        // ClaimResponse.request -> the Claim entry's fullUrl (mandatory link, R18.2)
        assertThat(cr.getRequest().getReference()).isEqualTo(fullUrlOf(tx, Claim.class));

        // Provenance targets Claim + ClaimResponse.
        Provenance p = first(tx, Provenance.class);
        assertThat(p.getTarget()).hasSize(2);

        // Every entry is an idempotent conditional create keyed on the decisionId (R18.3),
        // and every resource carries the decisionId tag (R18.1).
        for (Bundle.BundleEntryComponent e : tx.getEntry()) {
            assertThat(e.getRequest().getIfNoneExist()).contains("DEC-C1");
            assertThat(e.getResource().getMeta()
                    .getTag(FhirArtifactBuilder.DECISION_SYSTEM, "DEC-C1")).isNotNull();
        }
    }

    @Test
    void routedForReview_addsTask_andProvenanceTargetsIt() {
        Finding review = Finding.of("QUANTITY-LIMIT", "quantity", Severity.REVIEW,
                "quantity-limit-exceeded", "over limit");
        Bundle tx = builder.buildTransaction(CLAIM, new AdjudicationDecision(
                "DEC-C1", Outcome.ROUTED_FOR_REVIEW, List.of(review), List.of(review), null));

        Task t = first(tx, Task.class);
        assertThat(t).isNotNull();
        assertThat(t.getFocus().getReference()).isEqualTo(fullUrlOf(tx, ClaimResponse.class));
        assertThat(first(tx, Provenance.class).getTarget()).hasSize(3); // Claim + CR + Task
    }

    @Test
    void clinicalFinding_addsRiskAssessment() {
        Finding high = Finding.of("CLINICAL-SAFETY", "clinical", Severity.DENY,
                "clinical-safety-high", "drug-allergy conflict");
        Bundle tx = builder.buildTransaction(CLAIM, new AdjudicationDecision(
                "DEC-C1", Outcome.DENIED, List.of(high), List.of(high), null));

        RiskAssessment ra = first(tx, RiskAssessment.class);
        assertThat(ra).isNotNull();
        assertThat(ra.getPredictionFirstRep().getQualitativeRisk().getText()).isEqualTo("HIGH");
    }
}
