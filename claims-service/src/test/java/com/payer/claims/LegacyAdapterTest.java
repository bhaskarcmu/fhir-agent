package com.payer.claims;

import static org.assertj.core.api.Assertions.assertThat;

import com.payer.claims.acl.LegacyAdapter;
import com.payer.claims.domain.CanonicalClaim;
import com.payer.claims.domain.LegacyPricing;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;

class LegacyAdapterTest {

    private final LegacyAdapter acl = new LegacyAdapter();

    @Test
    void buildsExactFixedWidthClaimRecordTheEmulatorAccepts() {
        CanonicalClaim claim = new CanonicalClaim("C1", "000000001", "COM-SILVER", "29046",
                "51655-999", "lisinopril", 30, 30, LocalDate.of(2026, 6, 1), "1234567890",
                LocalDate.of(2026, 1, 1), LocalDate.of(2026, 12, 31), false, false);

        String record = acl.toLegacyRecord(claim);
        // Matches the 46-char record verified end-to-end against the emulator in M2.
        assertThat(record).hasSize(46)
                .isEqualTo("00000000151655-999  00030030202606011234567890");
    }

    @Test
    void parsesLegacyPaidResponseIntoCanonicalPricing() {
        // The exact 59-char paid response the emulator returned for lisinopril in M2.
        String response = "P0000000240000000150000024150000004830000019320RX1707784510";

        LegacyPricing p = acl.parseResponse(response);
        assertThat(p.paid()).isTrue();
        assertThat(p.rejectCode()).isEqualTo("000");
        assertThat(p.ingredientCost()).isEqualByComparingTo("240.00");
        assertThat(p.dispensingFee()).isEqualByComparingTo("1.50");
        assertThat(p.totalAmount()).isEqualByComparingTo("241.50");
        assertThat(p.patientPay()).isEqualByComparingTo("48.30");
        assertThat(p.planPay()).isEqualByComparingTo("193.20");
        assertThat(p.authNumber()).isEqualTo("RX1707784510");
    }

    @Test
    void parsesLegacyRejectResponse() {
        String response = "R065" + "0".repeat(43) + " ".repeat(12); // status R, code 065
        LegacyPricing p = acl.parseResponse(response);
        assertThat(p.paid()).isFalse();
        assertThat(p.rejectCode()).isEqualTo("065");
        assertThat(p.totalAmount()).isEqualByComparingTo("0.00");
    }
}
