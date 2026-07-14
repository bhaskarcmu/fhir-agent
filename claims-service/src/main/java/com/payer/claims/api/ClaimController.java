package com.payer.claims.api;

import com.payer.claims.domain.AdjudicationDecision;
import com.payer.claims.domain.CanonicalClaim;
import com.payer.claims.pipeline.AdjudicationPipeline;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * The claims-adjudication API façade — the single edge-facing entry point (fronted by Kong).
 * Accepts a canonical claim (JSON) and returns the deterministic adjudication decision.
 * Consumers never see the legacy core behind it.
 */
@RestController
@RequestMapping("/claims")
public class ClaimController {

    private final AdjudicationPipeline pipeline;

    public ClaimController(AdjudicationPipeline pipeline) {
        this.pipeline = pipeline;
    }

    @PostMapping("/adjudicate")
    public ResponseEntity<AdjudicationDecision> adjudicate(@RequestBody CanonicalClaim claim) {
        return ResponseEntity.ok(pipeline.adjudicate(claim));
    }
}
