package com.payer.claims.domain;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.time.LocalDate;

/**
 * The platform's canonical claim — what the modern services reason about, produced by
 * validating the inbound request. Legacy record shapes never appear above the ACL.
 *
 * <p><b>Why these constraints (R17.6).</b> A claim that fails them is <i>malformed</i>, not
 * <i>denied</i>: it is rejected at intake with `400` + `OperationOutcome` and nothing is
 * adjudicated or persisted. Two rules shaped the bounds:
 * <ul>
 *   <li><b>Anything a decision depends on is mandatory.</b> A missing value must never be read
 *       as a decision input. Absent coverage dates, for example, would otherwise make
 *       {@link #coverageActiveOnDos()} false and produce a <i>denial</i> for what is actually a
 *       data gap — a wrong answer wearing a correct answer's clothes.</li>
 *   <li><b>Sizes mirror the legacy fixed-width record</b> ({@code acl/LegacyAdapter}). That
 *       record right-pads and <i>truncates</i>: a 10-character member id would silently price
 *       the wrong member, and an over-wide quantity would shift every field after it. The ACL
 *       cannot defend itself, so the boundary does.</li>
 * </ul>
 * Fields no decision reads ({@code drugName}) stay optional — rejecting a valid claim over a
 * display string would be its own bug. The two booleans default to {@code false} when absent,
 * which is the conservative reading: no PA on file pends, step therapy unmet routes to review.
 *
 * @param claimId          business/idempotency id for this submission
 * @param memberId         member identifier (legacy MBRID form)
 * @param planId           benefit plan id (references the payer KB)
 * @param rxcui            RxNorm ingredient id (clinical rules key)
 * @param ndc              National Drug Code (legacy/formulary key)
 * @param drugName         display name — optional, no rule reads it
 * @param quantity         quantity dispensed
 * @param daysSupply       days supply
 * @param dateOfService    date of service
 * @param prescriberNpi    prescriber NPI (10 digits)
 * @param coverageEffective member coverage effective date (resolved upstream)
 * @param coverageTermination member coverage termination date
 * @param priorAuthOnFile  whether an approved PA is already on file
 * @param stepTherapyMet   whether step therapy has been satisfied
 */
public record CanonicalClaim(
        @NotBlank(message = "claimId is required (it is the decision/idempotency key)")
        String claimId,

        @NotBlank(message = "memberId is required")
        @Size(max = 9, message = "memberId must be at most 9 characters (legacy MBRID width)")
        String memberId,

        @NotBlank(message = "planId is required to resolve the benefit plan")
        String planId,

        @NotBlank(message = "rxcui is required to resolve formulary and clinical rules")
        String rxcui,

        @NotBlank(message = "ndc is required")
        @Size(max = 11, message = "ndc must be at most 11 characters (legacy NDC width)")
        String ndc,

        String drugName,

        @Positive(message = "quantity must be greater than zero")
        @Max(value = 99_999, message = "quantity must be at most 99999 (legacy 5-digit field)")
        int quantity,

        @Positive(message = "daysSupply must be greater than zero")
        @Max(value = 999, message = "daysSupply must be at most 999 (legacy 3-digit field)")
        int daysSupply,

        @NotNull(message = "dateOfService is required")
        LocalDate dateOfService,

        @NotBlank(message = "prescriberNpi is required")
        @Pattern(regexp = "\\d{10}", message = "prescriberNpi must be exactly 10 digits")
        String prescriberNpi,

        @NotNull(message = "coverageEffective is required (its absence is a data gap, not a denial)")
        LocalDate coverageEffective,

        @NotNull(message = "coverageTermination is required (its absence is a data gap, not a denial)")
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
