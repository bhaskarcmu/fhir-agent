package com.payer.claims;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Claims Adjudication Modernisation Layer — the modern façade (Phase 2, M3).
 *
 * <p>Wraps the legacy RxClaim core behind an API façade + anti-corruption layer, runs the
 * layered benefit/prior-auth rules engine and the Decision Contract, and reuses the triage
 * service for clinical safety. Edge-facing (fronted by Kong); the legacy core is internal-only.
 */
@SpringBootApplication
public class ClaimsServiceApplication {
    public static void main(String[] args) {
        SpringApplication.run(ClaimsServiceApplication.class, args);
    }
}
