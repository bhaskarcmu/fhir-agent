package com.payer.claims.rules;

import com.payer.claims.domain.CanonicalClaim;
import com.payer.claims.domain.Finding;
import com.payer.claims.domain.FormularyEntry;
import com.payer.claims.domain.Outcome;
import com.payer.claims.domain.RiskLevel;
import com.payer.claims.domain.Severity;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import org.springframework.stereotype.Component;

/**
 * Deterministic adjudication rules engine (Decision Contract, R17).
 *
 * <p><b>Accumulate-then-resolve</b>, not first-match: every applicable rule runs and emits
 * findings; the outcome is resolved by precedence (DENY &gt; PEND &gt; REVIEW &gt; approved),
 * and findings are sorted by a total order {@code (severity, domain, ruleId)} so the reason
 * list is stable across runs/implementations.
 */
@Component
public class RulesEngine {

    /** Fixed pipeline order used as the deterministic domain tie-break (R17.4). */
    private static final List<String> DOMAIN_ORDER = List.of(
            "eligibility", "provider", "formulary", "prior-auth",
            "clinical", "coding", "medical-necessity", "quantity", "step-therapy");

    public Resolution evaluate(CanonicalClaim claim, FormularyEntry formulary, RiskLevel risk) {
        List<Finding> f = new ArrayList<>();

        // Eligibility — coverage active on the date of service.
        if (!claim.coverageActiveOnDos()) {
            f.add(Finding.of("ELIGIBILITY", "eligibility", Severity.DENY, "coverage-inactive",
                    "Member coverage is not active on the date of service."));
        }

        // Formulary presence.
        if (formulary == null || !formulary.covered()) {
            f.add(Finding.of("NON-FORMULARY", "formulary", Severity.DENY, "non-formulary",
                    "Drug is not on the plan formulary and no exception is on file."));
        }

        // Attribute-based rules run whenever a formulary row exists — even if the drug is
        // non-formulary — so multiple reasons aggregate (accumulate-then-resolve, PRD §9.4).
        if (formulary != null) {
            // Prior authorization.
            if (formulary.priorAuth() && !claim.priorAuthOnFile()) {
                f.add(Finding.of("PA-REQUIRED", "prior-auth", Severity.PEND, "prior-auth-required",
                        "Prior authorization is required and none is on file."));
            }
            // Step therapy.
            if (formulary.stepTherapy() && !claim.stepTherapyMet()) {
                f.add(Finding.of("STEP-THERAPY", "step-therapy", Severity.REVIEW, "step-therapy-required",
                        "Step therapy required; documented try/fail of a first-line agent is missing."));
            }
            // Quantity limit.
            if (formulary.quantityLimit() && formulary.quantityLimitQty() != null
                    && claim.quantity() > formulary.quantityLimitQty()) {
                f.add(Finding.of("QUANTITY-LIMIT", "quantity", Severity.REVIEW, "quantity-limit-exceeded",
                        "Requested quantity exceeds the plan quantity limit."));
            }
        }

        // Clinical safety (reused triage), mapped per R17.5.
        if (risk == RiskLevel.HIGH) {
            f.add(Finding.of("CLINICAL-SAFETY", "clinical", Severity.DENY, "clinical-safety-high",
                    "High clinical-safety risk (e.g., drug-allergy conflict)."));
        } else if (risk == RiskLevel.MODERATE) {
            f.add(Finding.of("CLINICAL-SAFETY", "clinical", Severity.REVIEW, "clinical-safety-moderate",
                    "Moderate clinical-safety concern; pharmacist review recommended."));
        } else if (risk == RiskLevel.UNKNOWN) {
            // Fail closed: an incomplete safety check must not silently approve. A human decides.
            f.add(Finding.of("CLINICAL-SAFETY-UNAVAILABLE", "clinical", Severity.PEND,
                    "clinical-safety-unavailable",
                    "Clinical-safety check could not be completed; pharmacist review required."));
        }

        // Deterministic total order: severity, then pipeline domain, then rule id.
        f.sort(Comparator.comparingInt((Finding x) -> x.severity().ordinal())
                .thenComparingInt(x -> domainRank(x.domain()))
                .thenComparing(Finding::ruleId));

        Outcome outcome = resolve(f);
        return new Resolution(outcome, winningTier(f, outcome), List.copyOf(f));
    }

    private static Outcome resolve(List<Finding> f) {
        if (f.stream().anyMatch(x -> x.severity() == Severity.DENY)) return Outcome.DENIED;
        if (f.stream().anyMatch(x -> x.severity() == Severity.PEND)) return Outcome.PENDED;
        if (f.stream().anyMatch(x -> x.severity() == Severity.REVIEW)) return Outcome.ROUTED_FOR_REVIEW;
        return Outcome.APPROVED;
    }

    private static List<Finding> winningTier(List<Finding> f, Outcome outcome) {
        Severity tier = switch (outcome) {
            case DENIED -> Severity.DENY;
            case PENDED -> Severity.PEND;
            case ROUTED_FOR_REVIEW -> Severity.REVIEW;
            case APPROVED -> null;
        };
        if (tier == null) return List.of();
        return f.stream().filter(x -> x.severity() == tier).toList();
    }

    private static int domainRank(String domain) {
        int i = DOMAIN_ORDER.indexOf(domain);
        return i < 0 ? 99 : i;
    }

    /** Engine result: the outcome, the winning-tier reasons, and every finding (for audit/trace). */
    public record Resolution(Outcome outcome, List<Finding> reasons, List<Finding> allFindings) {}
}
