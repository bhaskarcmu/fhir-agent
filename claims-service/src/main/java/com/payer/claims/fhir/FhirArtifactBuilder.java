package com.payer.claims.fhir;

import com.payer.claims.domain.AdjudicationDecision;
import com.payer.claims.domain.CanonicalClaim;
import com.payer.claims.domain.Finding;
import java.util.Date;
import java.util.UUID;
import org.hl7.fhir.r4.model.Bundle;
import org.hl7.fhir.r4.model.Claim;
import org.hl7.fhir.r4.model.ClaimResponse;
import org.hl7.fhir.r4.model.CodeableConcept;
import org.hl7.fhir.r4.model.Identifier;
import org.hl7.fhir.r4.model.Provenance;
import org.hl7.fhir.r4.model.Quantity;
import org.hl7.fhir.r4.model.Reference;
import org.hl7.fhir.r4.model.Resource;
import org.hl7.fhir.r4.model.RiskAssessment;
import org.hl7.fhir.r4.model.Task;
import org.springframework.stereotype.Component;

/**
 * Builds the auditable FHIR R4 artefact graph for one decision as a single TRANSACTION bundle
 * (R18): one {@code decisionId} stamped on every resource (identifier + meta.tag), mandatory
 * references between them, and per-entry {@code ifNoneExist} conditional creates so a retry is
 * idempotent (R18.3) and the whole graph commits all-or-nothing (R18.4).
 */
@Component
public class FhirArtifactBuilder {

    public static final String DECISION_SYSTEM = "urn:phase2:decision";
    private static final String CLAIM_TYPE = "http://terminology.hl7.org/CodeSystem/claim-type";
    private static final String RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm";

    public Bundle buildTransaction(CanonicalClaim claim, AdjudicationDecision decision) {
        String dz = decision.decisionId();
        String claimUrn = urn(dz, "Claim");
        String crUrn = urn(dz, "ClaimResponse");
        String taskUrn = urn(dz, "Task");

        Bundle tx = new Bundle().setType(Bundle.BundleType.TRANSACTION);

        // --- Claim -------------------------------------------------------------------------
        Claim c = new Claim();
        stamp(c, dz);
        c.setStatus(Claim.ClaimStatus.ACTIVE);
        c.getType().addCoding().setSystem(CLAIM_TYPE).setCode("pharmacy");
        c.setUse(Claim.Use.CLAIM);
        c.setPatient(refByIdentifier(claim.memberId()));
        c.setCreated(new Date());
        c.setProvider(refByIdentifier(claim.prescriberNpi()));
        c.getPriority().addCoding()
                .setSystem("http://terminology.hl7.org/CodeSystem/processpriority").setCode("normal");
        c.addInsurance().setSequence(1).setFocal(true).setCoverage(refByIdentifier(claim.planId()));
        Claim.ItemComponent item = c.addItem().setSequence(1);
        item.getProductOrService().addCoding().setSystem(RXNORM)
                .setCode(claim.rxcui()).setDisplay(claim.drugName());
        item.setQuantity(new Quantity().setValue(claim.quantity()));
        add(tx, c, claimUrn, "Claim", dz);

        // --- ClaimResponse (request -> Claim) ----------------------------------------------
        ClaimResponse cr = new ClaimResponse();
        stamp(cr, dz);
        cr.setStatus(ClaimResponse.ClaimResponseStatus.ACTIVE);
        cr.getType().addCoding().setSystem(CLAIM_TYPE).setCode("pharmacy");
        cr.setUse(ClaimResponse.Use.CLAIM);
        cr.setPatient(refByIdentifier(claim.memberId()));
        cr.setCreated(new Date());
        cr.setInsurer(refByIdentifier(claim.planId()));
        cr.setRequest(new Reference(claimUrn));
        cr.setOutcome(mapOutcome(decision));
        cr.setDisposition(decision.outcome().name());
        for (Finding f : decision.reasons()) {
            cr.addProcessNote().setText(f.code() + ": " + f.message());
        }
        add(tx, cr, crUrn, "ClaimResponse", dz);

        // --- Task (only when routed for manual review) -------------------------------------
        boolean routed = decision.outcome() == com.payer.claims.domain.Outcome.ROUTED_FOR_REVIEW;
        if (routed) {
            Task t = new Task();
            stamp(t, dz);
            t.setStatus(Task.TaskStatus.REQUESTED);
            t.setIntent(Task.TaskIntent.ORDER);
            t.setFocus(new Reference(crUrn));
            t.setFor(refByIdentifier(claim.memberId()));
            t.setReasonReference(new Reference(crUrn));
            t.setDescription("Prescription claim routed for manual review.");
            add(tx, t, taskUrn, "Task", dz);
        }

        // --- Provenance (target -> Claim, ClaimResponse, Task?) ----------------------------
        Provenance p = new Provenance();
        stamp(p, dz);
        p.addTarget(new Reference(claimUrn));
        p.addTarget(new Reference(crUrn));
        if (routed) p.addTarget(new Reference(taskUrn));
        p.setRecorded(new Date());
        p.addAgent().setWho(new Reference().setDisplay("claims-service"));
        add(tx, p, urn(dz, "Provenance"), "Provenance", dz);

        // --- RiskAssessment (clinical safety, when a clinical finding fired) ----------------
        Finding clinical = decision.allFindings().stream()
                .filter(f -> "clinical".equals(f.domain())).findFirst().orElse(null);
        if (clinical != null) {
            RiskAssessment ra = new RiskAssessment();
            stamp(ra, dz);
            ra.setStatus(RiskAssessment.RiskAssessmentStatus.FINAL);
            ra.setSubject(refByIdentifier(claim.memberId()));
            String risk = clinical.code().endsWith("high") ? "HIGH" : "MODERATE";
            ra.addPrediction().setQualitativeRisk(new CodeableConcept().setText(risk));
            ra.addBasis(new Reference(crUrn));
            add(tx, ra, urn(dz, "RiskAssessment"), "RiskAssessment", dz);
        }
        return tx;
    }

    private static ClaimResponse.RemittanceOutcome mapOutcome(AdjudicationDecision d) {
        return switch (d.outcome()) {
            case APPROVED -> ClaimResponse.RemittanceOutcome.COMPLETE;
            case DENIED -> ClaimResponse.RemittanceOutcome.ERROR;
            case PENDED, ROUTED_FOR_REVIEW -> ClaimResponse.RemittanceOutcome.PARTIAL;
        };
    }

    /** Stamp the shared decisionId as both an identifier and a meta.tag (tag covers Provenance). */
    private static void stamp(Resource r, String dz) {
        r.getMeta().addTag(DECISION_SYSTEM, dz, "decision");
        if (r instanceof Claim x) x.addIdentifier(idz(dz));
        else if (r instanceof ClaimResponse x) x.addIdentifier(idz(dz));
        else if (r instanceof Task x) x.addIdentifier(idz(dz));
        else if (r instanceof RiskAssessment x) x.addIdentifier(idz(dz));
    }

    private static Identifier idz(String dz) {
        return new Identifier().setSystem(DECISION_SYSTEM).setValue(dz);
    }

    private static Reference refByIdentifier(String value) {
        return new Reference().setIdentifier(new Identifier().setValue(value));
    }

    private static void add(Bundle tx, Resource r, String fullUrl, String type, String dz) {
        tx.addEntry().setFullUrl(fullUrl).setResource(r)
                .getRequest().setMethod(Bundle.HTTPVerb.POST).setUrl(type)
                .setIfNoneExist("_tag=" + DECISION_SYSTEM + "|" + dz); // idempotent create (R18.3)
    }

    /** Deterministic urn:uuid per (decisionId, resourceType) — stable across retries, no randomness. */
    private static String urn(String dz, String type) {
        return "urn:uuid:" + UUID.nameUUIDFromBytes((dz + "|" + type).getBytes());
    }
}
