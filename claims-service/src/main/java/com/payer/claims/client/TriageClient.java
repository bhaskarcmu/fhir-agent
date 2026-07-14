package com.payer.claims.client;

import com.payer.claims.domain.CanonicalClaim;
import com.payer.claims.domain.RiskLevel;

/** Clinical-safety check — delegates to the reused Phase 1 triage service (no rebuild, D1). */
public interface TriageClient {
    RiskLevel assess(CanonicalClaim claim);
}
