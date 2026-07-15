package com.payer.claims;

import static org.assertj.core.api.Assertions.assertThat;

import com.payer.claims.acl.LegacyAdapter;
import com.payer.claims.client.LegacyClient;
import com.payer.claims.client.TriageClient;
import com.payer.claims.domain.AdjudicationDecision;
import com.payer.claims.domain.CanonicalClaim;
import com.payer.claims.domain.FormularyEntry;
import com.payer.claims.domain.Outcome;
import com.payer.claims.domain.RiskLevel;
import com.payer.claims.kb.PayerKb;
import com.payer.claims.pipeline.AdjudicationPipeline;
import com.payer.claims.rules.RulesEngine;
import java.time.LocalDate;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

/**
 * Drives the whole decisioning flow end-to-end with in-memory fakes for the two downstream
 * services — exercising the R8 golden-path scenarios at the decision level.
 */
class AdjudicationPipelineTest {

    // A legacy PAID response (59 chars) the fake legacy core returns.
    private static final String PAID_RESPONSE =
            "P0000000240000000150000024150000004830000019320RX1707784510";

    private final LegacyAdapter acl = new LegacyAdapter();
    private final RulesEngine rules = new RulesEngine();

    private AdjudicationPipeline pipeline(FormularyEntry formulary, RiskLevel risk) {
        return pipeline(formulary, (claim, patientId) -> risk, new StubFhir(Optional.of("P1")));
    }

    private AdjudicationPipeline pipeline(FormularyEntry formulary, TriageClient triage,
                                          StubFhir fhir) {
        PayerKb kb = (planId, rxcui) -> Optional.ofNullable(formulary);
        LegacyClient legacy = record -> PAID_RESPONSE;
        return new AdjudicationPipeline(kb, rules, triage, legacy, acl, fhir);
    }

    /** Minimal FHIR stub: resolves a member to the given patient id; other ops unused here. */
    private record StubFhir(Optional<String> patientId) implements com.payer.claims.fhir.FhirClient {
        public void submit(org.hl7.fhir.r4.model.Bundle tx) { }
        public Optional<AdjudicationDecision> existingDecision(String id) { return Optional.empty(); }
        public Optional<String> resolvePatientId(String memberId) { return patientId; }
    }

    private static CanonicalClaim claim(String rxcui, int qty, LocalDate dos, boolean paOnFile) {
        return new CanonicalClaim("C1", "000000001", "COM-SILVER", rxcui, "63552-200", "drug",
                qty, 30, dos, "1234567890",
                LocalDate.of(2026, 1, 1), LocalDate.of(2026, 12, 31), paOnFile, false);
    }

    private static FormularyEntry fe(boolean covered, boolean pa, boolean ql, Integer qlq) {
        return new FormularyEntry("COM-SILVER", "1991302", "drug", covered ? "GENERIC" : "NON-FORMULARY",
                pa, false, ql, qlq, covered);
    }

    private static final LocalDate DOS = LocalDate.of(2026, 6, 1);

    @Test
    void approvedScenario_pricesFromLegacy() {
        AdjudicationDecision d = pipeline(fe(true, false, false, null), RiskLevel.LOW)
                .adjudicate(claim("29046", 30, DOS, false));
        assertThat(d.outcome()).isEqualTo(Outcome.APPROVED);
        assertThat(d.decisionId()).isEqualTo("DEC-C1");
        assertThat(d.pricing()).isNotNull();
        assertThat(d.pricing().totalAmount()).isEqualByComparingTo("241.50"); // ACL parsed legacy pricing
    }

    @Test
    void pendedScenario_priorAuthRequired() {
        AdjudicationDecision d = pipeline(fe(true, true, false, null), RiskLevel.LOW)
                .adjudicate(claim("1991302", 1, DOS, false));
        assertThat(d.outcome()).isEqualTo(Outcome.PENDED);
    }

    @Test
    void deniedScenario_nonFormulary_skipsLegacyPricing() {
        AdjudicationDecision d = pipeline(null, RiskLevel.LOW)
                .adjudicate(claim("1991302", 1, DOS, false));
        assertThat(d.outcome()).isEqualTo(Outcome.DENIED);
        assertThat(d.pricing()).isNull(); // hard denial → legacy core not called
    }

    @Test
    void safetyScenario_highRiskDenies() {
        AdjudicationDecision d = pipeline(fe(true, false, false, null), RiskLevel.HIGH)
                .adjudicate(claim("723", 30, DOS, false));
        assertThat(d.outcome()).isEqualTo(Outcome.DENIED);
        assertThat(d.reasons()).extracting(f -> f.code()).containsExactly("clinical-safety-high");
    }

    @Test
    void resolvedPatientId_isHandedToTriage() {
        // Regression guard: triage was once called with no patient context, so the safety check
        // silently evaluated nothing and every claim approved. Assert the id actually flows.
        AtomicReference<String> seen = new AtomicReference<>();
        pipeline(fe(true, false, false, null),
                (claim, patientId) -> { seen.set(patientId); return RiskLevel.LOW; },
                new StubFhir(Optional.of("P1")))
                .adjudicate(claim("29046", 30, DOS, false));
        assertThat(seen.get()).isEqualTo("P1");
    }

    @Test
    void unresolvedMember_reachesTriageAsNull_soItCanFailClosed() {
        // The pipeline does not invent a patient id; it hands null to triage, which maps it to
        // UNKNOWN (see HttpTriageClientTest) — together these make an unresolvable member pend.
        AtomicReference<String> seen = new AtomicReference<>("unset");
        pipeline(fe(true, false, false, null),
                (claim, patientId) -> { seen.set(patientId); return RiskLevel.UNKNOWN; },
                new StubFhir(Optional.empty()))
                .adjudicate(claim("29046", 30, DOS, false));
        assertThat(seen.get()).isNull();
    }

    @Test
    void safetyCheckUnavailable_pendsInsteadOfApproving() {
        // The whole point of failing closed: an otherwise-clean claim must not approve when the
        // clinical-safety check could not run.
        AdjudicationDecision d = pipeline(fe(true, false, false, null), RiskLevel.UNKNOWN)
                .adjudicate(claim("29046", 30, DOS, false));
        assertThat(d.outcome()).isEqualTo(Outcome.PENDED);
        assertThat(d.reasons()).extracting(f -> f.code())
                .containsExactly("clinical-safety-unavailable");
    }

    @Test
    void multiReasonScenario_nonFormularyPlusQuantity() {
        AdjudicationDecision d = pipeline(fe(false, false, true, 4), RiskLevel.LOW)
                .adjudicate(claim("1991302", 8, DOS, false));
        assertThat(d.outcome()).isEqualTo(Outcome.DENIED);
        assertThat(d.allFindings()).extracting(f -> f.code())
                .contains("non-formulary", "quantity-limit-exceeded");
    }
}
