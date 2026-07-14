package com.payer.claims;

import static org.assertj.core.api.Assertions.assertThat;

import com.payer.claims.domain.CanonicalClaim;
import com.payer.claims.domain.Finding;
import com.payer.claims.domain.FormularyEntry;
import com.payer.claims.domain.Outcome;
import com.payer.claims.domain.RiskLevel;
import com.payer.claims.rules.RulesEngine;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;

class RulesEngineTest {

    private final RulesEngine engine = new RulesEngine();

    private static CanonicalClaim claim(LocalDate dos, int qty, boolean paOnFile, boolean stepMet) {
        return new CanonicalClaim("C1", "000000001", "COM-SILVER", "1991302", "63552-200",
                "semaglutide", qty, 30, dos, "1234567890",
                LocalDate.of(2026, 1, 1), LocalDate.of(2026, 12, 31), paOnFile, stepMet);
    }

    private static FormularyEntry fe(boolean covered, boolean pa, boolean st, boolean ql, Integer qlq) {
        return new FormularyEntry("COM-SILVER", "1991302", "semaglutide", "SPECIALTY",
                pa, st, ql, qlq, covered);
    }

    private static final LocalDate DOS = LocalDate.of(2026, 6, 1);

    @Test
    void approved_whenCoveredNoFlagsAndLowRisk() {
        var r = engine.evaluate(claim(DOS, 30, false, false),
                fe(true, false, false, false, null), RiskLevel.LOW);
        assertThat(r.outcome()).isEqualTo(Outcome.APPROVED);
        assertThat(r.reasons()).isEmpty();
    }

    @Test
    void pended_whenPriorAuthRequiredAndNotOnFile() {
        var r = engine.evaluate(claim(DOS, 1, false, false),
                fe(true, true, false, false, null), RiskLevel.LOW);
        assertThat(r.outcome()).isEqualTo(Outcome.PENDED);
        assertThat(r.reasons()).extracting(Finding::code).containsExactly("prior-auth-required");
    }

    @Test
    void denied_whenNonFormulary() {
        var r = engine.evaluate(claim(DOS, 1, false, false), null, RiskLevel.LOW);
        assertThat(r.outcome()).isEqualTo(Outcome.DENIED);
        assertThat(r.reasons()).extracting(Finding::code).containsExactly("non-formulary");
    }

    @Test
    void denied_whenCoverageInactive() {
        var r = engine.evaluate(claim(LocalDate.of(2025, 12, 1), 1, false, false),
                fe(true, false, false, false, null), RiskLevel.LOW);
        assertThat(r.outcome()).isEqualTo(Outcome.DENIED);
        assertThat(r.reasons()).extracting(Finding::code).containsExactly("coverage-inactive");
    }

    @Test
    void denied_whenClinicalRiskHigh() {
        var r = engine.evaluate(claim(DOS, 1, false, false),
                fe(true, false, false, false, null), RiskLevel.HIGH);
        assertThat(r.outcome()).isEqualTo(Outcome.DENIED);
        assertThat(r.reasons()).extracting(Finding::code).containsExactly("clinical-safety-high");
    }

    @Test
    void routedForReview_whenModerateRiskOnly() {
        var r = engine.evaluate(claim(DOS, 1, false, false),
                fe(true, false, false, false, null), RiskLevel.MODERATE);
        assertThat(r.outcome()).isEqualTo(Outcome.ROUTED_FOR_REVIEW);
    }

    @Test
    void routedForReview_whenQuantityExceedsLimit() {
        var r = engine.evaluate(claim(DOS, 8, false, false),
                fe(true, false, false, true, 4), RiskLevel.LOW);
        assertThat(r.outcome()).isEqualTo(Outcome.ROUTED_FOR_REVIEW);
        assertThat(r.reasons()).extracting(Finding::code).containsExactly("quantity-limit-exceeded");
    }

    @Test
    void routedForReview_whenStepTherapyNotMet() {
        var r = engine.evaluate(claim(DOS, 1, false, false),
                fe(true, false, true, false, null), RiskLevel.LOW);
        assertThat(r.outcome()).isEqualTo(Outcome.ROUTED_FOR_REVIEW);
        assertThat(r.reasons()).extracting(Finding::code).containsExactly("step-therapy-required");
    }

    @Test
    void precedence_denyWinsAndReasonsAreWinningTier_butAllFindingsAggregate() {
        // Non-formulary (DENY) + quantity-limit (REVIEW) → DENIED; reason = the DENY;
        // allFindings still carries both (multi-reason explanation input).
        var r = engine.evaluate(claim(DOS, 8, false, false),
                fe(false, false, false, true, 4), RiskLevel.LOW);
        assertThat(r.outcome()).isEqualTo(Outcome.DENIED);
        assertThat(r.reasons()).extracting(Finding::code).containsExactly("non-formulary");
        assertThat(r.allFindings()).extracting(Finding::code)
                .contains("non-formulary", "quantity-limit-exceeded");
    }

    @Test
    void deterministicOrder_byDomain_whenTwoDenies() {
        // coverage-inactive (eligibility) + non-formulary (formulary), both DENY:
        // eligibility must sort before formulary (fixed pipeline order, R17.4).
        var r = engine.evaluate(claim(LocalDate.of(2025, 12, 1), 1, false, false),
                null, RiskLevel.LOW);
        assertThat(r.reasons()).extracting(Finding::domain).containsExactly("eligibility", "formulary");
    }
}
