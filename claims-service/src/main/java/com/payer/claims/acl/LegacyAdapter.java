package com.payer.claims.acl;

import com.payer.claims.domain.CanonicalClaim;
import com.payer.claims.domain.LegacyPricing;
import java.math.BigDecimal;
import java.time.format.DateTimeFormatter;
import org.springframework.stereotype.Component;

/**
 * Anti-corruption layer (ACL). The single boundary that knows the legacy RxClaim wire format:
 * it builds the fixed-width (DDS-style) claim record the legacy core expects and parses the
 * fixed-width response back into the canonical {@link LegacyPricing}. Legacy field shapes and
 * quirks never leak above this class.
 *
 * <p>The layouts here MUST match the rxclaim-emulator contract (claim = 46 chars, response =
 * 59 chars, amounts implied 2-decimal, dates CCYYMMDD).
 */
@Component
public class LegacyAdapter {

    private static final DateTimeFormatter CCYYMMDD = DateTimeFormatter.ofPattern("yyyyMMdd");

    // ---- Canonical claim -> legacy 46-char claim record ------------------------------------
    public String toLegacyRecord(CanonicalClaim c) {
        return rpad(c.memberId(), 9)
                + rpad(c.ndc(), 11)
                + lpadNum(c.quantity(), 5)
                + lpadNum(c.daysSupply(), 3)
                + c.dateOfService().format(CCYYMMDD)
                + rpad(c.prescriberNpi(), 10);
    }

    // ---- Legacy 59-char response record -> canonical pricing --------------------------------
    public LegacyPricing parseResponse(String r) {
        if (r == null || r.length() < 59) {
            throw new IllegalArgumentException("Legacy response must be 59 chars, got "
                    + (r == null ? "null" : r.length()));
        }
        char status = r.charAt(0);
        String reject = r.substring(1, 4);
        BigDecimal ingredient = money(r.substring(4, 13));
        BigDecimal dispensing = money(r.substring(13, 20));
        BigDecimal total = money(r.substring(20, 29));
        BigDecimal patient = money(r.substring(29, 38));
        BigDecimal plan = money(r.substring(38, 47));
        String auth = r.substring(47, 59).trim();
        return new LegacyPricing(status == 'P', reject, ingredient, dispensing, total,
                patient, plan, auth);
    }

    // ---- helpers ---------------------------------------------------------------------------
    private static BigDecimal money(String cents) {
        return new BigDecimal(cents.trim()).movePointLeft(2); // implied 2 decimals
    }

    private static String rpad(String s, int n) {
        String v = s == null ? "" : s;
        return v.length() > n ? v.substring(0, n) : v + " ".repeat(n - v.length());
    }

    private static String lpadNum(int v, int n) {
        return String.format("%0" + n + "d", v);
    }
}
