package com.payer.rxclaim;

import static org.assertj.core.api.Assertions.assertThat;

import com.payer.rxclaim.core.RxClaimCore;
import com.payer.rxclaim.legacy.LegacyClaimRecord;
import com.payer.rxclaim.legacy.LegacyResponseRecord;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

/**
 * Exercises ADJRXCLM against the seeded Db2/SQL400-style master files (H2).
 *
 * <p>Datasource is pinned to H2 via test properties (which outrank OS environment variables)
 * so the suite is deterministic even when the shell exports SPRING_DATASOURCE_URL / NEON_* —
 * the same ambient-DB quirk documented for fhir-service tests in CLAUDE.md.
 */
@SpringBootTest(properties = {
        "spring.datasource.url=jdbc:h2:mem:rxclaimtest;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.datasource.username=sa",
        "spring.datasource.password="
})
class RxClaimCoreTest {

    @Autowired
    RxClaimCore core;

    private static LegacyClaimRecord claim(String mbr, String ndc, int qty, LocalDate dos) {
        return new LegacyClaimRecord(mbr, ndc, qty, 30, dos, "1234567890");
    }

    @Test
    void paidClaim_pricesFromDrgmstAndAppliesCoinsurance() {
        // lisinopril AWP 8.00 × 30 = 240.00 ingredient; +1.50 dispensing = 241.50 total;
        // 20% coinsurance → patient 48.30, plan 193.20.
        LegacyResponseRecord r = core.adjRxClm(
                claim("000000001", "51655-999", 30, LocalDate.of(2026, 6, 1)));

        assertThat(r.isPaid()).isTrue();
        assertThat(r.rejectCode()).isEqualTo("000");
        assertThat(r.ingredientCost()).isEqualByComparingTo("240.00");
        assertThat(r.dispensingFee()).isEqualByComparingTo("1.50");
        assertThat(r.totalAmount()).isEqualByComparingTo("241.50");
        assertThat(r.patientPay()).isEqualByComparingTo("48.30");
        assertThat(r.planPay()).isEqualByComparingTo("193.20");
        assertThat(r.authNumber()).startsWith("RX").hasSize(12);
    }

    @Test
    void highCostSpecialty_pricesCorrectly() {
        // semaglutide AWP 950.00 × 1 = 950.00; +2.00 = 952.00; patient 190.40, plan 761.60.
        LegacyResponseRecord r = core.adjRxClm(
                claim("000000001", "63552-200", 1, LocalDate.of(2026, 6, 1)));
        assertThat(r.isPaid()).isTrue();
        assertThat(r.totalAmount()).isEqualByComparingTo("952.00");
        assertThat(r.patientPay()).isEqualByComparingTo("190.40");
    }

    @Test
    void inactiveCoverage_rejects65() {
        // Member 000000002 terminated 2026-01-31; date of service 2026-03-15 is out of window.
        LegacyResponseRecord r = core.adjRxClm(
                claim("000000002", "51655-999", 30, LocalDate.of(2026, 3, 15)));
        assertThat(r.isPaid()).isFalse();
        assertThat(r.rejectCode()).isEqualTo(LegacyResponseRecord.RJ_PATIENT_NOT_COVERED); // 065
    }

    @Test
    void unknownMember_rejects65() {
        LegacyResponseRecord r = core.adjRxClm(
                claim("999999999", "51655-999", 30, LocalDate.of(2026, 6, 1)));
        assertThat(r.rejectCode()).isEqualTo(LegacyResponseRecord.RJ_PATIENT_NOT_COVERED);
    }

    @Test
    void unknownProduct_rejects70() {
        LegacyResponseRecord r = core.adjRxClm(
                claim("000000001", "00000-0000", 30, LocalDate.of(2026, 6, 1)));
        assertThat(r.isPaid()).isFalse();
        assertThat(r.rejectCode()).isEqualTo(LegacyResponseRecord.RJ_PRODUCT_NOT_COVERED); // 070
    }
}
