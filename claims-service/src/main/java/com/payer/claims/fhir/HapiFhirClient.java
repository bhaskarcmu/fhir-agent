package com.payer.claims.fhir;

import ca.uhn.fhir.context.FhirContext;
import ca.uhn.fhir.rest.client.api.IGenericClient;
import com.payer.claims.domain.AdjudicationDecision;
import com.payer.claims.domain.Finding;
import com.payer.claims.domain.Outcome;
import com.payer.claims.domain.Severity;
import java.util.List;
import java.util.Optional;
import org.hl7.fhir.r4.model.Bundle;
import org.hl7.fhir.r4.model.ClaimResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** HAPI FHIR R4 implementation — writes the transaction bundle to the platform FHIR server. */
@Component
public class HapiFhirClient implements FhirClient {

    private final FhirContext ctx = FhirContext.forR4();
    private final IGenericClient client;

    public HapiFhirClient(@Value("${fhir.base-url:http://localhost:8080/fhir}") String baseUrl) {
        this.ctx.getRestfulClientFactory().setSocketTimeout(20_000);
        this.client = ctx.newRestfulGenericClient(baseUrl);
    }

    @Override
    public void submit(Bundle transaction) {
        client.transaction().withBundle(transaction).execute();
    }

    @Override
    public Optional<AdjudicationDecision> existingDecision(String decisionId) {
        Bundle b = client.search().forResource(ClaimResponse.class)
                .where(ClaimResponse.IDENTIFIER.exactly()
                        .systemAndCode(FhirArtifactBuilder.DECISION_SYSTEM, decisionId))
                .returnBundle(Bundle.class).execute();

        Optional<ClaimResponse> cr = b.getEntry().stream()
                .map(Bundle.BundleEntryComponent::getResource)
                .filter(ClaimResponse.class::isInstance).map(ClaimResponse.class::cast)
                .findFirst();
        if (cr.isEmpty()) return Optional.empty();

        ClaimResponse r = cr.get();
        Outcome outcome = Outcome.valueOf(r.getDisposition());
        List<Finding> reasons = r.getProcessNote().stream()
                .map(n -> parseNote(n.getText())).toList();
        return Optional.of(new AdjudicationDecision(decisionId, outcome, reasons, reasons, null));
    }

    private static Finding parseNote(String text) {
        int i = text.indexOf(": ");
        String code = i > 0 ? text.substring(0, i) : text;
        String msg = i > 0 ? text.substring(i + 2) : text;
        return Finding.of("REPLAY", "replay", Severity.INFO, code, msg);
    }
}
