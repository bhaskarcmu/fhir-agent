package com.payer.claims.domain;

/** Clinical-safety risk level returned by the reused triage service. */
public enum RiskLevel {
    HIGH,
    MODERATE,
    LOW,
    /**
     * The clinical-safety check could not be completed (member unresolved, triage down or
     * erroring, or an unrecognised response). Distinct from {@link #LOW}: it means "we do not
     * know", not "we checked and it is safe" — so it must never approve a claim on its own
     * (R17.5 maps it to PEND for human review).
     */
    UNKNOWN
}
