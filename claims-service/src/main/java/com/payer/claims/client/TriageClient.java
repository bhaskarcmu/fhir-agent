package com.payer.claims.client;

import com.payer.claims.domain.CanonicalClaim;
import com.payer.claims.domain.RiskLevel;

/** Clinical-safety check — delegates to the reused Phase 1 triage service (no rebuild, D1). */
public interface TriageClient {
    /**
     * @param claim         the claim (its rxcui is the medication in question)
     * @param fhirPatientId the resolved FHIR Patient logical id, or null if the member could
     *                      not be resolved (in which case clinical risk defaults to LOW)
     */
    RiskLevel assess(CanonicalClaim claim, String fhirPatientId);
}
