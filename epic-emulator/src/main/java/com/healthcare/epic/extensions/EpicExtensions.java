package com.healthcare.epic.extensions;

/**
 * Placeholder Epic-style extensions for {@code MedicationRequest}/{@code AllergyIntolerance}
 * (PRD §1/§3, design.md §5, decision E12). These URLs and the backfill value are <b>not</b>
 * verified against Epic's real documentation (decision E10 remains partial) — they are
 * structurally representative stand-ins, clearly namespaced under a same-repo placeholder domain,
 * not a claim about what real Epic extensions look like.
 */
public final class EpicExtensions {

    public static final String MEDICATION_REQUEST_EXTENSION_URL =
            "http://epic-emulator.local/fhir/extensions/medication-therapy-class";

    public static final String ALLERGY_INTOLERANCE_EXTENSION_URL =
            "http://epic-emulator.local/fhir/extensions/allergy-source-system";

    /** Deliberately a synthetic marker, not invented clinical content — see design.md §5. */
    public static final String BACKFILL_VALUE = "synthetic-epic-emulator-backfill";

    private EpicExtensions() {}

    /** The extension URL to backfill for a resource type, or null if this type isn't in scope. */
    public static String extensionUrlFor(String resourceType) {
        return switch (resourceType) {
            case "MedicationRequest" -> MEDICATION_REQUEST_EXTENSION_URL;
            case "AllergyIntolerance" -> ALLERGY_INTOLERANCE_EXTENSION_URL;
            default -> null;
        };
    }
}
