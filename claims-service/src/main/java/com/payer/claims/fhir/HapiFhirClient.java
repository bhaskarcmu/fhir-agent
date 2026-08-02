package com.payer.claims.fhir;

import ca.uhn.fhir.context.FhirContext;
import ca.uhn.fhir.rest.client.api.IClientInterceptor;
import ca.uhn.fhir.rest.client.api.IGenericClient;
import ca.uhn.fhir.rest.client.api.IHttpRequest;
import ca.uhn.fhir.rest.client.api.IHttpResponse;
import com.payer.claims.domain.AdjudicationDecision;
import com.payer.claims.domain.Finding;
import com.payer.claims.domain.Outcome;
import com.payer.claims.domain.Severity;
import com.payer.claims.observability.TracePropagation;
import java.util.List;
import java.util.Optional;
import org.hl7.fhir.r4.model.Bundle;
import org.hl7.fhir.r4.model.ClaimResponse;
import org.hl7.fhir.r4.model.Patient;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** HAPI FHIR R4 implementation — writes the transaction bundle to the platform FHIR server. */
@Component
public class HapiFhirClient implements FhirClient {

    private final FhirContext ctx = FhirContext.forR4();
    private final IGenericClient client;

    public HapiFhirClient(
            @Value("${fhir.base-url:http://localhost:8080/fhir}") String baseUrl,
            TracePropagation tracePropagation) {
        this.ctx.getRestfulClientFactory().setSocketTimeout(20_000);
        this.client = ctx.newRestfulGenericClient(baseUrl);
        // Manual propagation (docs/phase6/decisions.md H16): HAPI's IGenericClient has its
        // own internal HTTP transport, not Spring's RestClient, so it isn't auto-instrumented
        // either -- a no-op when tracing isn't configured.
        this.client.registerInterceptor(new IClientInterceptor() {
            @Override
            public void interceptRequest(IHttpRequest request) {
                tracePropagation.headers().forEach(request::addHeader);
            }

            @Override
            public void interceptResponse(IHttpResponse response) {
                // no-op
            }
        });
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

    @Override
    public Optional<String> resolvePatientId(String memberId) {
        // Read Patient/member-{memberId} directly (reads are immediately consistent, unlike an
        // identifier search which depends on search-index timing; the "member-" prefix keeps the
        // logical id non-numeric, which HAPI requires for client-assigned ids). In production a
        // member→Patient index would back this resolution.
        try {
            Patient p = client.read().resource(Patient.class)
                    .withId("member-" + memberId).execute();
            return Optional.ofNullable(p.getIdElement().getIdPart());
        } catch (ca.uhn.fhir.rest.server.exceptions.ResourceNotFoundException e) {
            return Optional.empty();
        }
    }

    private static Finding parseNote(String text) {
        int i = text.indexOf(": ");
        String code = i > 0 ? text.substring(0, i) : text;
        String msg = i > 0 ? text.substring(i + 2) : text;
        return Finding.of("REPLAY", "replay", Severity.INFO, code, msg);
    }
}
