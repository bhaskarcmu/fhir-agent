package com.payer.rxclaim.core;

import com.payer.rxclaim.legacy.LegacyClaimRecord;
import com.payer.rxclaim.legacy.LegacyResponseRecord;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/**
 * The legacy adjudication routine, modelled on an RPG/CL program named {@code ADJRXCLM}
 * ("Adjudicate Rx Claim"). It reads the Db2 for i master files (MBRMST / DRGMST / ACCMST),
 * performs member eligibility, computes pricing, updates accumulators, and returns a legacy
 * response record.
 *
 * <p>Scope note: per the modernization snapshot, this legacy core owns the <b>member
 * system-of-record, pricing, and accumulators</b>. Formulary, prior-authorization, and
 * clinical-safety rules live in the modern layer (claims-service / triage), NOT here — so this
 * core only rejects for member-eligibility (NCPDP 65) and unknown product (NCPDP 70).
 */
@Component
public class RxClaimCore {

    /** Legacy coinsurance applied by the pricing engine (20%). */
    private static final BigDecimal COINSURANCE = new BigDecimal("0.20");

    private final JdbcTemplate jdbc;

    public RxClaimCore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /** ADJRXCLM — adjudicate one prescription claim record. */
    public LegacyResponseRecord adjRxClm(LegacyClaimRecord claim) {
        // 1. Member eligibility — MBRMST is the system-of-record.
        Member member;
        try {
            member = jdbc.queryForObject(
                    "SELECT EFFDTE, TRMDTE, MBRSTS FROM MBRMST WHERE MBRID = ?",
                    (rs, i) -> new Member(
                            rs.getDate("EFFDTE").toLocalDate(),
                            rs.getDate("TRMDTE").toLocalDate(),
                            rs.getString("MBRSTS").trim()),
                    claim.memberId());
        } catch (EmptyResultDataAccessException e) {
            return LegacyResponseRecord.rejected(LegacyResponseRecord.RJ_PATIENT_NOT_COVERED);
        }
        LocalDate dos = claim.dateOfService();
        boolean active = "A".equals(member.status())
                && !dos.isBefore(member.effective())
                && !dos.isAfter(member.termination());
        if (!active) {
            return LegacyResponseRecord.rejected(LegacyResponseRecord.RJ_PATIENT_NOT_COVERED);
        }

        // 2. Product pricing — DRGMST holds AWP + dispensing fee.
        Drug drug;
        try {
            drug = jdbc.queryForObject(
                    "SELECT AWPAMT, DSPFEE FROM DRGMST WHERE NDCCDE = ?",
                    (rs, i) -> new Drug(rs.getBigDecimal("AWPAMT"), rs.getBigDecimal("DSPFEE")),
                    claim.ndc());
        } catch (EmptyResultDataAccessException e) {
            return LegacyResponseRecord.rejected(LegacyResponseRecord.RJ_PRODUCT_NOT_COVERED);
        }

        // 3. Pricing calculation.
        BigDecimal ingredient = drug.awp()
                .multiply(BigDecimal.valueOf(claim.quantityDispensed()))
                .setScale(2, RoundingMode.HALF_UP);
        BigDecimal dispensing = drug.dispensingFee().setScale(2, RoundingMode.HALF_UP);
        BigDecimal total = ingredient.add(dispensing).setScale(2, RoundingMode.HALF_UP);
        BigDecimal patientPay = total.multiply(COINSURANCE).setScale(2, RoundingMode.HALF_UP);
        BigDecimal planPay = total.subtract(patientPay).setScale(2, RoundingMode.HALF_UP);

        // 4. Update accumulators (ACCMST) — running out-of-pocket total.
        int planYear = dos.getYear();
        int rows = jdbc.update(
                "UPDATE ACCMST SET OOPMET = OOPMET + ? WHERE MBRID = ? AND PLANYR = ?",
                patientPay, claim.memberId(), planYear);
        if (rows == 0) {
            jdbc.update("INSERT INTO ACCMST (MBRID, PLANYR, DEDMET, OOPMET) VALUES (?, ?, ?, ?)",
                    claim.memberId(), planYear, BigDecimal.ZERO, patientPay);
        }

        // 5. Deterministic authorization/reference number (stable for a given claim).
        return LegacyResponseRecord.paid(ingredient, dispensing, total, patientPay, planPay,
                authNumber(claim));
    }

    private static String authNumber(LegacyClaimRecord c) {
        String key = c.memberId() + "|" + c.ndc() + "|" + c.dateOfService();
        long h = ((long) key.hashCode()) & 0x7fffffffL;
        return String.format("RX%010d", h % 10_000_000_000L);
    }

    private record Member(LocalDate effective, LocalDate termination, String status) {}

    private record Drug(BigDecimal awp, BigDecimal dispensingFee) {}
}
