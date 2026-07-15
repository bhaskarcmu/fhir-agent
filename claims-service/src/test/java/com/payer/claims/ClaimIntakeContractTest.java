package com.payer.claims;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.payer.claims.api.ClaimController;
import com.payer.claims.api.ClaimValidationAdvice;
import com.payer.claims.domain.AdjudicationDecision;
import com.payer.claims.domain.CanonicalClaim;
import com.payer.claims.domain.Outcome;
import com.payer.claims.pipeline.AdjudicationService;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.server.ResponseStatusException;

/**
 * API contract test for the R17.6 error taxonomy's three <b>disjoint</b> response classes.
 *
 * <p>The invariant under test is the boundary between them, not any single status code. A
 * <b>denial</b> is a decision about a valid claim and belongs in the audit trail; a
 * <b>malformed request</b> is not a claim and must leave no trace. When those collapse, a
 * submission that was never valid acquires a decision — which is exactly what happened before
 * this was enforced: `POST {}` returned 200 with `decisionId: "DEC-null"` and persisted it.
 *
 * <p>Runs the real web layer (Jackson binding, `@Valid`, the advice) because that is where the
 * contract lives — none of it is reachable from a plain unit test.
 */
@WebMvcTest(ClaimController.class)
@Import(ClaimValidationAdvice.class)
class ClaimIntakeContractTest {

    @Autowired private MockMvc mvc;
    @MockBean private AdjudicationService service;

    private static final String VALID = """
            {"claimId":"C1","memberId":"000000001","planId":"COM-SILVER","rxcui":"29046",
             "ndc":"51655-999","drugName":"lisinopril","quantity":30,"daysSupply":30,
             "dateOfService":"2026-06-01","prescriberNpi":"1234567890",
             "coverageEffective":"2026-01-01","coverageTermination":"2026-12-31",
             "priorAuthOnFile":false,"stepTherapyMet":false}""";

    /** A claim missing everything a decision depends on. */
    private static final String EMPTY = "{}";

    private static AdjudicationDecision decision(Outcome outcome) {
        return new AdjudicationDecision("DEC-C1", outcome, List.of(), List.of(), null);
    }

    // ── Class 1: validation error → 400 + OperationOutcome, nothing adjudicated ──────────────

    @Test
    void emptyClaim_is400_withOperationOutcome_andIsNeverAdjudicated() throws Exception {
        mvc.perform(post("/claims/adjudicate").contentType(MediaType.APPLICATION_JSON).content(EMPTY))
                .andExpect(status().isBadRequest())
                .andExpect(content().contentTypeCompatibleWith("application/fhir+json"))
                .andExpect(jsonPath("$.resourceType").value("OperationOutcome"))
                .andExpect(jsonPath("$.issue[0].severity").value("error"))
                .andExpect(jsonPath("$.issue[0].code").value("invalid"));

        // The heart of it: the pipeline must never see a malformed claim, so no decision can be
        // produced and no artefact can be persisted. This assertion is the regression guard.
        verify(service, never()).adjudicateAndPersist(any());
    }

    @Test
    void missingClaimId_isRejected_soNoDecisionIdCanBeNull() throws Exception {
        String noId = VALID.replace("\"claimId\":\"C1\",", "");
        mvc.perform(post("/claims/adjudicate").contentType(MediaType.APPLICATION_JSON).content(noId))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issue[0].diagnostics").value(
                        org.hamcrest.Matchers.containsString("claimId")));
        verify(service, never()).adjudicateAndPersist(any());
    }

    @Test
    void overlongMemberId_isRejected_ratherThanSilentlyTruncatedByTheAcl() throws Exception {
        // The legacy record right-pads memberId to 9 and truncates beyond it, so a 10-character
        // id would price a different member. The boundary refuses what the ACL cannot.
        String bad = VALID.replace("\"000000001\"", "\"0000000019\"");
        mvc.perform(post("/claims/adjudicate").contentType(MediaType.APPLICATION_JSON).content(bad))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issue[0].diagnostics").value(
                        org.hamcrest.Matchers.containsString("memberId")));
        verify(service, never()).adjudicateAndPersist(any());
    }

    @Test
    void missingCoverageDates_areRejected_notReadAsAnInactiveCoverageDenial() throws Exception {
        // Absent coverage dates once made coverageActiveOnDos() false → a DENIAL for a data gap.
        String bad = VALID.replace("\"coverageEffective\":\"2026-01-01\",", "");
        mvc.perform(post("/claims/adjudicate").contentType(MediaType.APPLICATION_JSON).content(bad))
                .andExpect(status().isBadRequest());
        verify(service, never()).adjudicateAndPersist(any());
    }

    @Test
    void zeroQuantity_isRejected() throws Exception {
        mvc.perform(post("/claims/adjudicate").contentType(MediaType.APPLICATION_JSON)
                        .content(VALID.replace("\"quantity\":30", "\"quantity\":0")))
                .andExpect(status().isBadRequest());
        verify(service, never()).adjudicateAndPersist(any());
    }

    @Test
    void malformedNpi_isRejected() throws Exception {
        mvc.perform(post("/claims/adjudicate").contentType(MediaType.APPLICATION_JSON)
                        .content(VALID.replace("\"1234567890\"", "\"12345\"")))
                .andExpect(status().isBadRequest());
        verify(service, never()).adjudicateAndPersist(any());
    }

    @Test
    void unparseableBody_is400_notAServerError() throws Exception {
        mvc.perform(post("/claims/adjudicate").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"claimId\": "))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.resourceType").value("OperationOutcome"));
        verify(service, never()).adjudicateAndPersist(any());
    }

    @Test
    void unparseableDate_is400_withoutEchoingThePayload() throws Exception {
        mvc.perform(post("/claims/adjudicate").contentType(MediaType.APPLICATION_JSON)
                        .content(VALID.replace("\"2026-06-01\"", "\"01/06/2026\"")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issue[0].diagnostics").value(
                        org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("000000001"))));
    }

    @Test
    void theSameBadClaim_alwaysProducesTheIdenticalResponse() throws Exception {
        // Bean validation reports violations in an unspecified order; the advice sorts them so
        // the API stays deterministic (R17.4's rationale, applied to the error surface).
        String first = mvc.perform(post("/claims/adjudicate")
                        .contentType(MediaType.APPLICATION_JSON).content(EMPTY))
                .andReturn().getResponse().getContentAsString();
        String second = mvc.perform(post("/claims/adjudicate")
                        .contentType(MediaType.APPLICATION_JSON).content(EMPTY))
                .andReturn().getResponse().getContentAsString();
        assertThat(first).isEqualTo(second);
    }

    // ── Class 2: adjudication decision → 200 (a denial is NOT a validation error) ────────────

    @Test
    void validClaim_isAdjudicated_200() throws Exception {
        given(service.adjudicateAndPersist(any())).willReturn(decision(Outcome.APPROVED));

        mvc.perform(post("/claims/adjudicate").contentType(MediaType.APPLICATION_JSON).content(VALID))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.decisionId").value("DEC-C1"))
                .andExpect(jsonPath("$.outcome").value("APPROVED"));
    }

    @Test
    void aDeniedClaim_isStill200_becauseDenialIsADecisionNotAnError() throws Exception {
        given(service.adjudicateAndPersist(any())).willReturn(decision(Outcome.DENIED));

        mvc.perform(post("/claims/adjudicate").contentType(MediaType.APPLICATION_JSON).content(VALID))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.outcome").value("DENIED"));
    }

    @Test
    void optionalFieldsMayBeOmitted_drugNameAndTheBooleans() throws Exception {
        given(service.adjudicateAndPersist(any())).willReturn(decision(Outcome.APPROVED));
        String minimal = """
                {"claimId":"C1","memberId":"000000001","planId":"COM-SILVER","rxcui":"29046",
                 "ndc":"51655-999","quantity":30,"daysSupply":30,"dateOfService":"2026-06-01",
                 "prescriberNpi":"1234567890","coverageEffective":"2026-01-01",
                 "coverageTermination":"2026-12-31"}""";

        mvc.perform(post("/claims/adjudicate").contentType(MediaType.APPLICATION_JSON).content(minimal))
                .andExpect(status().isOk());

        // Absent booleans default false — the conservative reading (pends/routes, never approves).
        org.mockito.ArgumentCaptor<CanonicalClaim> captor =
                org.mockito.ArgumentCaptor.forClass(CanonicalClaim.class);
        verify(service).adjudicateAndPersist(captor.capture());
        assertThat(captor.getValue().priorAuthOnFile()).isFalse();
        assertThat(captor.getValue().stepTherapyMet()).isFalse();
    }

    // ── Class 3: system error → 503, retry-safe ──────────────────────────────────────────────

    @Test
    void downstreamFailure_is503_andRetrySafe() throws Exception {
        given(service.adjudicateAndPersist(any()))
                .willThrow(new IllegalStateException("FHIR store unavailable"));

        mvc.perform(post("/claims/adjudicate").contentType(MediaType.APPLICATION_JSON).content(VALID))
                .andExpect(status().isServiceUnavailable());
    }

    @Test
    void systemErrorIsDistinctFromValidationError() throws Exception {
        // Same well-formed claim: only the downstream state differs. A 503 must never be
        // reported as a 400, or a client would "fix" a claim that was never wrong.
        given(service.adjudicateAndPersist(any()))
                .willThrow(new ResponseStatusException(
                        org.springframework.http.HttpStatus.SERVICE_UNAVAILABLE, "down"));

        mvc.perform(post("/claims/adjudicate").contentType(MediaType.APPLICATION_JSON).content(VALID))
                .andExpect(status().isServiceUnavailable());
    }
}
