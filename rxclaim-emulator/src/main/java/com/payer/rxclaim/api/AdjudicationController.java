package com.payer.rxclaim.api;

import com.payer.rxclaim.core.RxClaimCore;
import com.payer.rxclaim.legacy.LegacyClaimRecord;
import com.payer.rxclaim.legacy.LegacyResponseRecord;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * REST fa&ccedil;ade over the legacy core. Intentionally speaks the legacy contract:
 * a fixed-width claim record in ({@code text/plain}), a fixed-width response record out.
 *
 * <p>The modern claims-service (M3) owns the anti-corruption layer that builds this record
 * from a canonical claim and parses the response back into FHIR — consumers never call this
 * service directly. It is internal-only (Cloud Run {@code ingress=internal}); no edge route.
 */
@RestController
@RequestMapping("/rxclaim")
public class AdjudicationController {

    private final RxClaimCore core;

    public AdjudicationController(RxClaimCore core) {
        this.core = core;
    }

    @PostMapping(value = "/adjudicate",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> adjudicate(@RequestBody String claimRecord) {
        String rec = claimRecord == null ? "" : claimRecord.replaceAll("\\R+$", "");
        LegacyClaimRecord claim;
        try {
            claim = LegacyClaimRecord.parse(rec);
        } catch (RuntimeException e) {
            // Malformed legacy record — this is a transport/format error, not an adjudication.
            return ResponseEntity.badRequest().body("ERR " + e.getMessage());
        }
        LegacyResponseRecord response = core.adjRxClm(claim);
        return ResponseEntity.ok(response.format());
    }
}
