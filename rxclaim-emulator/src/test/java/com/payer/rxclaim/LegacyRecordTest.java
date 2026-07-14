package com.payer.rxclaim;

import static org.assertj.core.api.Assertions.assertThat;

import com.payer.rxclaim.legacy.LegacyClaimRecord;
import com.payer.rxclaim.legacy.LegacyResponseRecord;
import java.math.BigDecimal;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;

class LegacyRecordTest {

    @Test
    void claimRecord_formatsToFixedWidthAndRoundTrips() {
        LegacyClaimRecord claim = new LegacyClaimRecord(
                "000000001", "51655-999", 30, 30, LocalDate.of(2026, 6, 1), "1234567890");

        String record = claim.format();
        assertThat(record).hasSize(LegacyClaimRecord.RECORD_LENGTH); // 46

        LegacyClaimRecord parsed = LegacyClaimRecord.parse(record);
        assertThat(parsed).isEqualTo(claim);
    }

    @Test
    void responseRecord_packsAmountsWithImpliedDecimals() {
        LegacyResponseRecord paid = LegacyResponseRecord.paid(
                new BigDecimal("240.00"), new BigDecimal("1.50"), new BigDecimal("241.50"),
                new BigDecimal("48.30"), new BigDecimal("193.20"), "RX0000000001");

        String record = paid.format();
        assertThat(record).hasSize(59);
        assertThat(record.charAt(0)).isEqualTo('P');
        assertThat(record.substring(1, 4)).isEqualTo("000");            // reject code
        assertThat(record.substring(4, 13)).isEqualTo("000024000");     // ingredient 240.00
        assertThat(record.substring(13, 20)).isEqualTo("0000150");      // dispensing 1.50
        assertThat(record.substring(20, 29)).isEqualTo("000024150");    // total 241.50
    }

    @Test
    void rejectedResponse_hasZeroAmountsAndCode() {
        LegacyResponseRecord r = LegacyResponseRecord.rejected(
                LegacyResponseRecord.RJ_PATIENT_NOT_COVERED);
        assertThat(r.isPaid()).isFalse();
        assertThat(r.rejectCode()).isEqualTo("065");
        assertThat(r.format()).hasSize(59).startsWith("R065");
    }
}
