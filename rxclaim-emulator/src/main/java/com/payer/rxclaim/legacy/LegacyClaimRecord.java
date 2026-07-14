package com.payer.rxclaim.legacy;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

/**
 * Fixed-width (DDS-style) inbound claim record — the legacy request contract.
 *
 * <p>Field layout (as it would appear in a Db2 for i / DDS physical file record format).
 * Positions are 1-based in the DDS view; this parser uses 0-based offsets. Total length 46.
 *
 * <pre>
 *   Field   Type/Len  Cols     Description
 *   MBRID   A(9)      1-9      Member id (zero-padded)
 *   NDCCDE  A(11)     10-20    National Drug Code (may contain hyphens)
 *   QTYDSP  S(5,0)    21-25    Quantity dispensed (zero-padded integer)
 *   DAYSUP  S(3,0)    26-28    Days supply (zero-padded integer)
 *   DTESVC  A(8)      29-36    Date of service, CCYYMMDD
 *   PRSNPI  A(10)     37-46    Prescriber NPI
 * </pre>
 */
public record LegacyClaimRecord(
        String memberId,
        String ndc,
        int quantityDispensed,
        int daysSupply,
        LocalDate dateOfService,
        String prescriberNpi) {

    public static final int RECORD_LENGTH = 46;
    private static final DateTimeFormatter CCYYMMDD = DateTimeFormatter.ofPattern("yyyyMMdd");

    /** Parse a 46-char fixed-width record into a typed claim. */
    public static LegacyClaimRecord parse(String record) {
        if (record == null || record.length() < RECORD_LENGTH) {
            throw new IllegalArgumentException(
                    "Claim record must be " + RECORD_LENGTH + " chars, got "
                            + (record == null ? "null" : record.length()));
        }
        String mbr = record.substring(0, 9).trim();
        String ndc = record.substring(9, 20).trim();
        int qty = Integer.parseInt(record.substring(20, 25).trim());
        int days = Integer.parseInt(record.substring(25, 28).trim());
        LocalDate dos = LocalDate.parse(record.substring(28, 36).trim(), CCYYMMDD);
        String npi = record.substring(36, 46).trim();
        return new LegacyClaimRecord(mbr, ndc, qty, days, dos, npi);
    }

    /** Render back to the 46-char fixed-width record (round-trips with {@link #parse}). */
    public String format() {
        return rpad(memberId, 9)
                + rpad(ndc, 11)
                + lpadNum(quantityDispensed, 5)
                + lpadNum(daysSupply, 3)
                + dateOfService.format(CCYYMMDD)
                + rpad(prescriberNpi, 10);
    }

    private static String rpad(String s, int n) {
        String v = s == null ? "" : s;
        if (v.length() > n) return v.substring(0, n);
        return v + " ".repeat(n - v.length());
    }

    private static String lpadNum(int v, int n) {
        return String.format("%0" + n + "d", v);
    }
}
