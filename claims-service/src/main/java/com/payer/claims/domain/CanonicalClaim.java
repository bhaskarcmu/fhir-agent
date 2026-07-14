package com.payer.claims.domain;

import java.time.LocalDate;

/**
 * The platform's canonical claim — what the modern services reason about, produced by
 * validating the inbound request. Legacy record shapes never appear above the ACL.
 *
 * @param claimId          business/idempotency id for this submission
 * @param memberId         member identifier (legacy MBRID form)
 * @param planId           benefit plan id (references the payer KB)
 * @param rxcui            RxNorm ingredient id (clinical rules key)
 * @param ndc              National Drug Code (legacy/formulary key)
 * @param drugName         display name
 * @param quantity         quantity dispensed
 * @param daysSupply       days supply
 * @param dateOfService    date of service
 * @param prescriberNpi    prescriber NPI
 * @param coverageEffective member coverage effective date (resolved upstream)
 * @param coverageTermination member coverage termination date
 * @param priorAuthOnFile  whether an approved PA is already on file
 * @param stepTherapyMet   whether step therapy has been satisfied
 */
public record CanonicalClaim(
        String claimId,
        String memberId,
        String planId,
        String rxcui,
        String ndc,
        String drugName,
        int quantity,
        int daysSupply,
        LocalDate dateOfService,
        String prescriberNpi,
        LocalDate coverageEffective,
        LocalDate coverageTermination,
        boolean priorAuthOnFile,
        boolean stepTherapyMet) {

    /** Coverage active on the date of service (eligibility input). */
    public boolean coverageActiveOnDos() {
        return coverageEffective != null && coverageTermination != null
                && !dateOfService.isBefore(coverageEffective)
                && !dateOfService.isAfter(coverageTermination);
    }
}
