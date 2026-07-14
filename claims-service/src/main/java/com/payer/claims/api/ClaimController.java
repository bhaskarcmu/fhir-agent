package com.payer.claims.api;

import com.payer.claims.domain.AdjudicationDecision;
import com.payer.claims.domain.CanonicalClaim;
import com.payer.claims.pipeline.AdjudicationService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/**
 * The claims-adjudication API façade — the single edge-facing entry point (fronted by Kong).
 * Accepts a canonical claim, returns the deterministic decision, and persists the auditable
 * FHIR artefact graph. Consumers never see the legacy core behind it.
 */
@RestController
@RequestMapping("/claims")
public class ClaimController {

    private static final Logger log = LoggerFactory.getLogger(ClaimController.class);

    private final AdjudicationService service;

    public ClaimController(AdjudicationService service) {
        this.service = service;
    }

    @PostMapping("/adjudicate")
    public ResponseEntity<AdjudicationDecision> adjudicate(@RequestBody CanonicalClaim claim) {
        try {
            return ResponseEntity.ok(service.adjudicateAndPersist(claim));
        } catch (RuntimeException e) {
            // System error (e.g., FHIR store unavailable). Writes are atomic, so nothing is
            // half-persisted and the client may safely retry (R17.6 / R18.4).
            log.error("adjudication persistence failed for claim {}: {}",
                    claim.claimId(), e.toString());
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                    "Adjudication temporarily unavailable; safe to retry.", e);
        }
    }
}
