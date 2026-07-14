package com.payer.claims.domain;

import java.math.BigDecimal;

/**
 * Pricing/authoritative-adjudication result returned by the legacy core (rxclaim-emulator),
 * after the anti-corruption layer parses the legacy response record into canonical form.
 */
public record LegacyPricing(
        boolean paid,
        String rejectCode,          // NCPDP reject code ("000" when paid)
        BigDecimal ingredientCost,
        BigDecimal dispensingFee,
        BigDecimal totalAmount,
        BigDecimal patientPay,
        BigDecimal planPay,
        String authNumber) {
}
