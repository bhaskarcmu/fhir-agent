package com.healthcare.epic;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Epic-flavored proxy in front of {@code fhir-service} (Phase 4).
 *
 * <p>M1 scope: a pass-through core only — every request is forwarded to fhir-service and its
 * response returned unchanged (PRD FR1). Auth emulation (M2), Medication/AllergyIntolerance
 * extension handling (M3), and the three named quirks (M4) are added as interceptors around this
 * same entry point in later milestones — see {@code docs/phase4/design.md}.
 */
@SpringBootApplication
public class EpicEmulatorApplication {
    public static void main(String[] args) {
        SpringApplication.run(EpicEmulatorApplication.class, args);
    }
}
