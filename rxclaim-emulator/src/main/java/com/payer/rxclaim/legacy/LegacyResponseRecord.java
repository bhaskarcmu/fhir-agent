package com.payer.rxclaim.legacy;

import java.math.BigDecimal;
import java.math.RoundingMode;

/**
 * Fixed-width (DDS-style) outbound response record — the legacy response contract.
 *
 * <p>Amounts use implied 2-decimal packing (e.g., 000001250 = 12.50), right-justified and
 * zero-padded, as legacy numeric fields typically are. Reject codes are NCPDP values.
 *
 * <pre>
 *   Field   Type/Len  Cols     Description
 *   RSPSTS  A(1)      1        Response status: P=paid, R=rejected
 *   RJCCDE  A(3)      2-4      NCPDP reject code ('000' when paid)
 *   INGCST  S(9,2)    5-13     Ingredient cost (implied 2 dp)
 *   DSPFEE  S(7,2)    14-20    Dispensing fee (implied 2 dp)
 *   TOTAMT  S(9,2)    21-29    Total amount (implied 2 dp)
 *   PATPAY  S(9,2)    30-38    Patient pay amount (implied 2 dp)
 *   PLNPAY  S(9,2)    39-47    Plan pay amount (implied 2 dp)
 *   AUTHNBR A(12)     48-59    Authorization / reference number
 * </pre>
 */
public record LegacyResponseRecord(
        char status,            // 'P' or 'R'
        String rejectCode,      // NCPDP reject code, "000" when paid
        BigDecimal ingredientCost,
        BigDecimal dispensingFee,
        BigDecimal totalAmount,
        BigDecimal patientPay,
        BigDecimal planPay,
        String authNumber) {

    public static final char PAID = 'P';
    public static final char REJECTED = 'R';

    /** NCPDP reject codes used by this legacy core. */
    public static final String RJ_NONE = "000";
    public static final String RJ_PATIENT_NOT_COVERED = "065"; // NCPDP 65
    public static final String RJ_PRODUCT_NOT_COVERED = "070"; // NCPDP 70

    private static final BigDecimal ZERO = BigDecimal.ZERO.setScale(2, RoundingMode.HALF_UP);

    public static LegacyResponseRecord rejected(String ncpdpRejectCode) {
        return new LegacyResponseRecord(REJECTED, ncpdpRejectCode,
                ZERO, ZERO, ZERO, ZERO, ZERO, "");
    }

    public static LegacyResponseRecord paid(BigDecimal ingredient, BigDecimal dispensing,
                                            BigDecimal total, BigDecimal patient, BigDecimal plan,
                                            String authNumber) {
        return new LegacyResponseRecord(PAID, RJ_NONE, ingredient, dispensing, total,
                patient, plan, authNumber);
    }

    public boolean isPaid() {
        return status == PAID;
    }

    /** Render to the 59-char fixed-width response record. */
    public String format() {
        return String.valueOf(status)
                + rpad(rejectCode, 3)
                + money(ingredientCost, 9)
                + money(dispensingFee, 7)
                + money(totalAmount, 9)
                + money(patientPay, 9)
                + money(planPay, 9)
                + rpad(authNumber, 12);
    }

    private static String money(BigDecimal amount, int width) {
        long cents = amount.setScale(2, RoundingMode.HALF_UP).movePointRight(2).longValueExact();
        return String.format("%0" + width + "d", cents);
    }

    private static String rpad(String s, int n) {
        String v = s == null ? "" : s;
        if (v.length() > n) return v.substring(0, n);
        return v + " ".repeat(n - v.length());
    }
}
