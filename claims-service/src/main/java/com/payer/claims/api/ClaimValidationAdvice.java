package com.payer.claims.api;

import ca.uhn.fhir.context.FhirContext;
import java.util.Comparator;
import java.util.List;
import org.hl7.fhir.r4.model.OperationOutcome;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.support.DefaultMessageSourceResolvable;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * Renders the R17.6 <b>validation-error</b> class: a malformed claim is rejected at the edge with
 * {@code 400} and a FHIR {@link OperationOutcome}, before the pipeline runs — so nothing is
 * adjudicated and nothing is persisted.
 *
 * <p>The distinction this enforces is the point: a <b>denial</b> is a decision about a valid
 * claim and belongs in the audit trail; a <b>malformed request</b> is not a claim at all and must
 * leave no trace. Collapsing the two lets a submission that was never valid acquire a decision.
 *
 * <p>Issues are sorted by {@code (field, message)} so the same bad request always produces a
 * byte-identical response — bean-validation reports violations in an unspecified order, which
 * would otherwise leak non-determinism into the API (R17.4's determinism rationale).
 */
@RestControllerAdvice
public class ClaimValidationAdvice {

    private static final Logger log = LoggerFactory.getLogger(ClaimValidationAdvice.class);

    /** Expensive to build (~seconds) and thread-safe once created, so built once per JVM. */
    private static final FhirContext FHIR = FhirContext.forR4();

    /** Constraint violations on an otherwise well-formed JSON body. */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<String> onInvalidClaim(MethodArgumentNotValidException e) {
        List<String> problems = e.getBindingResult().getFieldErrors().stream()
                .sorted(Comparator.comparing(org.springframework.validation.FieldError::getField)
                        .thenComparing(DefaultMessageSourceResolvable::getDefaultMessage,
                                Comparator.nullsFirst(Comparator.naturalOrder())))
                .map(f -> f.getField() + ": " + f.getDefaultMessage())
                .toList();
        log.info("rejected malformed claim ({} problem(s)): {}", problems.size(), problems);
        return badRequest(problems);
    }

    /**
     * The body could not be parsed at all — unreadable JSON, or a value of the wrong shape (an
     * unparseable date, a string where a number belongs). Field-level detail is deliberately not
     * echoed: the parser's message can quote the payload, and claims are treated as PHI (R14).
     */
    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<String> onUnreadableBody(HttpMessageNotReadableException e) {
        log.info("rejected unparseable claim body: {}", e.getMostSpecificCause().getClass().getSimpleName());
        return badRequest(List.of(
                "Request body is not a readable claim: malformed JSON, or a field of the wrong "
                        + "type (dates must be ISO-8601, e.g. 2026-06-01)."));
    }

    private static ResponseEntity<String> badRequest(List<String> problems) {
        OperationOutcome oo = new OperationOutcome();
        for (String p : problems) {
            oo.addIssue()
                    .setSeverity(OperationOutcome.IssueSeverity.ERROR)
                    .setCode(OperationOutcome.IssueType.INVALID)
                    .setDiagnostics(p);
        }
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .contentType(MediaType.valueOf("application/fhir+json"))
                .body(FHIR.newJsonParser().encodeResourceToString(oo));
    }
}
