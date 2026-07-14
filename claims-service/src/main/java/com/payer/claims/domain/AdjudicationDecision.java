package com.payer.claims.domain;

import java.util.List;

/**
 * The deterministic adjudication decision (Decision Contract, R17). Reasons are the findings of
 * the winning severity tier, in deterministic order. {@code pricing} is present when the legacy
 * core priced the claim (typically for approved/pended outcomes).
 *
 * @param decisionId one id stamped across all artefacts (R18.1)
 * @param outcome    approved / denied / pended / routed-for-review
 * @param reasons    winning-tier findings (multi-reason aggregation, R17.3)
 * @param allFindings every finding emitted (audit/trace)
 * @param pricing    legacy pricing, or null
 */
public record AdjudicationDecision(
        String decisionId,
        Outcome outcome,
        List<Finding> reasons,
        List<Finding> allFindings,
        LegacyPricing pricing) {
}
