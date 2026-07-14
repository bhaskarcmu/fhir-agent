package com.payer.claims.pipeline;

import com.payer.claims.acl.LegacyAdapter;
import com.payer.claims.client.LegacyClient;
import com.payer.claims.client.TriageClient;
import com.payer.claims.domain.AdjudicationDecision;
import com.payer.claims.domain.CanonicalClaim;
import com.payer.claims.domain.FormularyEntry;
import com.payer.claims.domain.LegacyPricing;
import com.payer.claims.domain.Outcome;
import com.payer.claims.domain.RiskLevel;
import com.payer.claims.kb.PayerKb;
import com.payer.claims.rules.RulesEngine;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * Orchestrates one adjudication: modern rule checks (eligibility → formulary → PA → step →
 * quantity), clinical safety (triage), then the authoritative legacy pricing call (through the
 * ACL). Findings accumulate and the outcome resolves by the Decision Contract (R17). The legacy
 * core is only priced when the modern decision is not already a hard denial.
 *
 * <p>M3 scope: produces the deterministic {@link AdjudicationDecision}. Emitting the FHIR
 * artefact graph (Claim/ClaimResponse/Task/Provenance) + idempotency persistence is M4.
 */
@Component
public class AdjudicationPipeline {

    private static final Logger log = LoggerFactory.getLogger(AdjudicationPipeline.class);

    private final PayerKb payerKb;
    private final RulesEngine rules;
    private final TriageClient triage;
    private final LegacyClient legacy;
    private final LegacyAdapter acl;

    public AdjudicationPipeline(PayerKb payerKb, RulesEngine rules, TriageClient triage,
                                LegacyClient legacy, LegacyAdapter acl) {
        this.payerKb = payerKb;
        this.rules = rules;
        this.triage = triage;
        this.legacy = legacy;
        this.acl = acl;
    }

    public AdjudicationDecision adjudicate(CanonicalClaim claim) {
        FormularyEntry formulary = payerKb.formularyEntry(claim.planId(), claim.rxcui()).orElse(null);
        RiskLevel risk = triage.assess(claim);                       // clinical safety (reused)
        RulesEngine.Resolution res = rules.evaluate(claim, formulary, risk);

        LegacyPricing pricing = null;
        if (res.outcome() != Outcome.DENIED) {
            try {
                String response = legacy.send(acl.toLegacyRecord(claim)); // legacy core, via ACL
                pricing = acl.parseResponse(response);
            } catch (RuntimeException e) {
                log.warn("legacy core unavailable for claim {}: {}", claim.claimId(), e.toString());
            }
        }
        return new AdjudicationDecision("DEC-" + claim.claimId(),
                res.outcome(), res.reasons(), res.allFindings(), pricing);
    }
}
