# Source PRD (archived) — Prescription Claim Adjudication Modernization Platform

> **Provenance.** This is a content reconstruction of the **source DRAFT PRD** that seeded
> the Phase 2 work, preserved here for posterity. The original was supplied as a chat prompt
> (plus an identical PDF) and was later lost from the author's chat archive due to a sync bug;
> this Markdown copy was reconstructed from that prompt's content and committed so the planning
> set is self-contained. **Lightly edited:** some framing has been reworded to generic
> enterprise-modernization rationale; all technical, data, architecture, and regulatory
> content is preserved.
>
> **Status of the original:** DRAFT — WORK IN PROGRESS.
>
> **⚠️ ARCHIVAL — NON-NORMATIVE — DO NOT EXECUTE AS-IS.** This is the **input, not the
> contract**, and it has been **superseded** by the working documents. The requirements we
> actually build (which deviate from this) live in [`requirements.md`](./requirements.md)
> (deviation table D1–D8 maps changes back to the sections below), and the design in
> [`plan.md`](./plan.md). **Do not implement from this file.**
>
> **Commands here are illustrative only** — several will not work against this platform
> as-is (e.g. §11 uses `Authorization: Bearer` while our gateway uses the `apikey` header;
> hosts/URLs may be stale). For runnable steps, use the repo's authoritative scripts and
> runbooks, not the snippets below.

---

# Prescription Claim Adjudication Modernization Platform
## Phase 2 Scope — Product Requirements Document

**STATUS: DRAFT — WORK IN PROGRESS**

---

## 1. Document Purpose and Status

This document is a working draft of the Phase 2 scope for a prescription claim adjudication modernization prototype. It is a living Product Requirements Document (PRD) and will continue to evolve as decisions are finalized; open items are flagged explicitly in Section 14, Open Questions, Risks and Next Steps.

The prototype is built to demonstrate enterprise claims-adjudication modernization leadership — centered on claims adjudication platform transformation, the vision of "Adjudication as a Service," Java/API development around IBM i and AS/400 systems, modularization, scalability, regulatory compliance, and the leadership of a large technology organization. Every scoping decision in this document is made with that modernization intent in mind and is deliberately framed to demonstrate that kind of leadership, rather than to build a generic healthcare-AI showcase.

## 2. Executive Summary

Phase 2 extends an existing Agentic Healthcare Platform — which already provides a FHIR R4 backend, a Kong API gateway, a triage service, a Model Context Protocol (MCP) agent, audit-oriented RiskAssessment output, a GKE/Kong/Neon deployment architecture, and an existing suite of test cases — into a focused Prescription Claim Adjudication Modernization Slice.

Rather than positioning Phase 2 as "payer operations" in the abstract, it is deliberately scoped as an API façade, a rules service, an audit trail, and an MCP explanation layer wrapped around a simulated legacy adjudication core, applied strictly to medication-prescription payer workflows. This keeps the project credible, prevents it from growing into an unfocused conceptual platform, and mirrors an "Adjudication as a Service" vision.

At minimum, the Minimum Viable Product (MVP) will:

- Accept a prescription claim request as input.
- Process it through eligibility, formulary, prior-authorization, and drug-allergy/duplicate-therapy checks.
- Emulate a legacy IBM i/RxClaim-style adjudication core.
- Produce a ClaimResponse, a review Task, and Provenance/RiskAssessment output.
- Use an AI agent to explain, in plain language, why a claim was approved, rejected, pended, or routed to manual review.

## 3. Background and Strategic Rationale

### 3.1 Strategic Framing

The purpose of this prototype is to demonstrate leadership of enterprise claims-adjudication modernization — claims adjudication platform transformation, the "Adjudication as a Service" strategy, Java/API development around IBM i/AS400 systems, modularization, scalability, regulatory compliance, and the leadership of large technology organizations. Because of that, Phase 2 must speak the language of that domain rather than presenting a broad, generic "payer operations" concept.

### 3.2 Why the Scope Is Deliberately Narrow

Phase 2 is intentionally restricted to **medication-prescription payer workflows only**. This is the single most important scoping decision in this document: it keeps the project credible and prevents it from becoming an overgrown, conceptual platform that tries to model an entire payer organization. Within that boundary, the prototype includes prescription claims intake, benefit verification, prior-authorization routing, clinical decision support (CDS), and audit — all of which are directly relevant to claims adjudication and payer workflows.

### 3.3 Foundation to Build On

Phase 2 does not start from zero. It builds naturally on the existing Agentic Healthcare Platform, which already includes:

- A FHIR R4 backend.
- A Kong API gateway.
- A triage service.
- An MCP agent.
- Audit-oriented RiskAssessment output.
- A GKE/Kong/Neon deployment architecture.
- A number of existing test cases.

## 4. Product Framing and Naming

How this initiative is named and introduced matters as much as what it contains, particularly because senior technical leaders evaluating the work may be skeptical of AI-first framing. The work calls for modernization and execution ownership first, with AI as a secondary enabler — and the naming should reflect that ordering.

**Avoid:** "Payer Operations MCP Agent" as a headline. This framing sounds AI-first and undersells the modernization and platform-engineering substance of the work.

**Use instead:**
- **Headline:** "Claims Adjudication Modernisation Layer"
- **Subtitle:** "with an MCP-powered explanation and workflow assistant"

**Full descriptive name:** "Prescription Claim Adjudication Modernisation Slice: API façade + rules service + audit trail + MCP explanation layer." This framing is much closer to the modernization intent than a broad "payer operations" description.

## 5. Scope Definition

### 5.1 In Scope — Medication-Prescription Payer Workflows Only

Within the boundary of medication-prescription payer workflows, Phase 2 explicitly includes:

- Prescription claims intake.
- Benefit verification.
- Prior-authorization routing.
- Clinical decision support (CDS) — as a sub-module rather than a standalone service in this phase.
- Audit trail and explainability.

### 5.2 MVP Definition

| Element | Definition |
|---|---|
| Input | Prescription claim request |
| Processing | Eligibility + formulary + prior-authorization + drug-allergy/duplicate-therapy check |
| Legacy simulation | IBM i/RxClaim-style adjudication emulator |
| Output | ClaimResponse + review Task + Provenance/RiskAssessment |
| Agent | Explains why the claim was approved, rejected, pended, or routed to review |

### 5.3 Out of Scope for Phase 2

- A full pharmacy benefit manager (PBM) platform.
- Coordination of Benefits (COB) — a significant real-world claims topic (for example, determining whether an employer plan or Medicare pays first when a patient has both) that is likely beyond this MVP; see Section 10.2, rule 15.
- A broad "payer operations" framing.

## 6. Solution Architecture

### 6.1 Legacy Integration Strategy: IBM i / AS400

This modernization explicitly involves IBM i fundamentals, AS/400 integration, Control Language (CL), the Integrated File System (IFS), SQL/400, Data Description Specifications (DDS), Java APIs, and connecting front-end/API layers to backend IBM i systems.

Building an actual IBM i environment is **not** necessary for this prototype. Instead, the plan calls for a simulated legacy adjudication core — a **"Legacy RxClaim / IBM i Emulator"** — consisting of:

- A simulated RPG/CL-style adjudication function.
- DB2/SQL400-like tables represented in PostgreSQL or JSON fixtures.
- A REST façade implemented in Java/Spring Boot.
- An anti-corruption layer that converts legacy claim fields into canonical FHIR/claim domain objects.

This design choice is what makes the project a credible enterprise-modernization slice, rather than a generic healthcare-AI demo.

### 6.2 Technology Stack

The domain has a strong Java emphasis — Core Java, Java EE, Spring, Spring Boot, JDBC, and Hibernate — and the technology split should foreground that rather than a Python-only prototype. The stack divides as follows:

- **Spring Boot:** the claims-adjudication façade, benefit rules, legacy adapter, and claim domain APIs.
- **Python/FastAPI:** MCP/agent orchestration and optional CDS support.
- **Existing HAPI FHIR:** persistence and the clinical-resource backbone.

This stack division foregrounds Java/Spring modernization leadership rather than a Python-only prototype.

### 6.3 Service Decomposition — Three Deployable Slices

For first-round credibility, the execution plan is simplified from an earlier five-service design down to three deployable slices:

1. **Claim Intake + Legacy Adapter Service** — A Spring Boot API that accepts prescription claim requests, validates them, maps them to canonical claim objects, and calls a simulated IBM i adjudication backend.
2. **Benefit + Prior Auth Rules Service** — Deterministic rules covering formulary status, coverage active/inactive determination, prior-authorization requirements, non-formulary handling, and manual-review triggers.
3. **MCP Explanation Agent** — Calls the underlying APIs and explains, in natural language, why a claim was paid, rejected, pended, or routed to review.

Clinical decision support (CDS) remains a sub-module within this scope rather than a full separate service.

### 6.4 Existing Platform Foundation

- FHIR R4 backend — a HAPI FHIR JPA R4 server backed by a Neon PostgreSQL database ("fhirdb").
- Kong API gateway.
- Triage service.
- MCP agent.
- Audit-oriented RiskAssessment output.
- GKE/Kong/Neon architecture.
- Synthea-generated FHIR R4 bundles and loading scripts, plus an existing suite of test cases.

### 6.5 Architecture Patterns

Three architecture patterns anchor the design and should be explicitly called out when presenting the work:

- **Strangler (fig) pattern:** incrementally replacing legacy functionality behind a routing façade rather than attempting a full rewrite, reducing risk during modernization.¹
- **API façade:** a single, well-defined interface fronting the legacy adjudication core so that consumers never call the legacy system directly.
- **Anti-corruption layer:** a translation boundary that converts legacy/proprietary data shapes into the platform's canonical FHIR-aligned domain model, preventing legacy data quirks from leaking into the new services.

The legacy core is **wrapped, not rewritten** — a distinction that matters both technically and as a message to stakeholders evaluating modernization risk.

## 7. "Adjudication as a Service" Value Proposition

This initiative develops and executes a vision for **"Adjudication as a Service."**² The Phase 2 plan should repeatedly connect back to that language:

- API façade over legacy adjudication.
- Modular benefit/prior-authorization rules.
- A reusable adjudication decision service.
- An audit trail for every decision.
- Lower cost of change.
- Faster speed to market.
- A scalable, serviceable platform.

This is the vocabulary of the role, and the prototype's architecture and narrative should consistently reinforce it.

## 8. Stakeholder Narrative

Suggested framing when presenting this work to senior stakeholders:

> "For Phase 2, I am extending my existing FHIR/MCP healthcare platform into a prescription claims adjudication modernisation slice. The goal is not to build a full PBM, but to demonstrate how I would wrap a legacy adjudication core with Spring Boot APIs, isolate benefit and prior-auth rules, persist auditable FHIR-aligned decision artefacts, and use an MCP agent only as an explanation/orchestration layer. The clinical and business logic stays deterministic and testable."

This framing is intended to read at a senior-leadership level. Supporting statements to reinforce it include:

- "AI helps explain and orchestrate; deterministic services make decisions."
- "FHIR is used where appropriate for interoperability and audit artefacts."
- "The legacy core is wrapped, not rewritten."
- "The architecture demonstrates strangler pattern, API façade, and anti-corruption layer."

## 9. Business Rules and Regulatory Domain Model

This section defines the regulatory and business-rule grounding for the adjudication pipeline. It answers, in depth, the question "what actual business rules govern claims adjudication, and where are they documented?" — a question relevant to business stakeholders (what the platform must comply with), product owners (what to prioritize), architects (how to layer the rules engine), and developers (what to implement and test).

### 9.1 The Claims Adjudication Pipeline

A prescription claim moves through the following ten-step pipeline:

1. Claim arrives.
2. Member eligibility is checked.
3. Provider eligibility is checked.
4. Benefit verification is performed.
5. Coding is validated.
6. Medical necessity is assessed.
7. Prior authorization is evaluated.
8. Clinical safety is checked.
9. Pricing is calculated.
10. Payment or denial is determined.

### 9.2 Fifteen Rule Domains

The following fifteen domains, each illustrated with a concrete example, define the representative rule set for the MVP.

1. **Member Eligibility** — Coverage must be active on the date of service. *Pass:* coverage effective Jan 1, 2026 through Dec 31, 2026, claim dated within that window. *Fail:* coverage ended Jan 31, 2026, but the claim is dated March 15, 2026, so it is denied for inactive coverage.
2. **Provider Eligibility** — The rendering provider must be credentialed for the service performed. *Pass:* a cardiologist orders a stress test. *Fail:* a dentist orders a cardiac catheterization, outside their scope of practice, and is rejected.
3. **CPT/HCPCS Coding Validation** — Procedure codes must be valid and consistent with the patient and context. Common examples: CPT 99213 (established patient office visit), 93000 (electrocardiogram), 45378 (diagnostic colonoscopy). *Fail:* a pediatric vaccine code billed for an adult patient (18+) is flagged as invalid.
4. **ICD-10 Diagnosis Validation** — Diagnosis codes must be valid ICD-10-CM codes and clinically coherent with the requested service — e.g. J18.9 (pneumonia, unspecified organism) or E11.9 (Type 2 diabetes mellitus without complications). *Routes to review:* an MRI of the brain ordered with a diagnosis of a broken toe, clinically inconsistent, routed to manual review rather than automatic denial.
5. **Medical Necessity** — Evaluated against CMS National Coverage Determinations (NCDs) and Local Coverage Determinations (LCDs).³ *Example:* an MRI is covered only after six weeks of documented conservative therapy and the presence of a neurological deficit.
6. **Prior Authorization** — High-cost medications require prior authorization before dispensing. *Example:* a $12,000 medication triggers a PA requirement and is routed to review if authorization is not on file. For Medicare Part D, the NCPDP SCRIPT standard governs electronic prior-authorization and prescribing transactions.⁴
7. **Formulary Status** — Each medication has a formulary status (covered/non-covered), a cost-sharing tier, a PA flag, and sometimes a quantity limit. *Example:* semaglutide (Ozempic) may be covered under a plan, assigned to a tier, and subject to both a PA requirement and a quantity limit — all evaluated together.
8. **Step Therapy** — Some medications require a lower-cost/first-line alternative be tried and fail first. *Example:* adalimumab (Humira) may require the patient first try and fail methotrexate; without documented step therapy, the claim is denied.
9. **Duplicate Therapy** — Checks for therapeutic duplication across a patient's active medications. *Example:* a patient already taking lisinopril prescribed a second ACE inhibitor triggers a duplicate-therapy warning.
10. **Drug Allergy** — Prescriptions are checked against documented allergies. *Example:* a patient with a documented penicillin allergy prescribed amoxicillin (a penicillin-class antibiotic) triggers a clinical safety alert.
11. **Age-Based Rules** — Certain medications are restricted by patient age. *Example:* a medication indicated only for patients 18+, prescribed for a 12-year-old, is rejected.
12. **Quantity Limits** — Formulary quantity limits cap the amount dispensable per fill or period. *Example:* a plan limit of 30 tablets per 30 days, with a request for 180 tablets, is routed to manual review.
13. **Frequency Limits** — Some services have minimum intervals between repeat occurrences. *Example:* an MRI requested only two weeks after a prior MRI is routed to manual review for frequency-limit evaluation.
14. **Benefit Exclusions** — Certain services are excluded entirely; others are conditionally covered. *Example:* cosmetic surgery is typically excluded outright, while weight-loss medications may or may not be covered depending on the plan.
15. **Coordination of Benefits (COB)** — When a member has more than one payer (e.g. an employer plan and Medicare), a COB determination establishes which payer is primary. A legitimate and significant real-world topic, but likely beyond this MVP; called out explicitly in Section 5.3.

### 9.3 Representative Rule Set (15–20 Rules)

A recommended representative rule set spanning eight domains, suitable for an MVP-scale rules engine:

| Domain | Example Rule(s) |
|---|---|
| Eligibility | Coverage must be active on the date of service; both member and provider must be eligible. |
| Provider | Rendering provider must be credentialed for the billed service. |
| Formulary | Medication must be on formulary, or a non-formulary exception/prior authorization must be on file. |
| Prior authorisation | High-cost medications and select procedures require prior authorization before adjudication. |
| Clinical | Drug-allergy and duplicate-therapy checks must pass before approval. |
| Coding | CPT/HCPCS and ICD-10 codes must be valid and clinically coherent with each other. |
| Medical necessity | Service must satisfy the applicable NCD/LCD criteria. |
| Quantity | Dispensed quantity must not exceed the plan's quantity limit without an approved exception. |

### 9.4 Example MCP Explanation Output

> "Claim denied because member coverage was active and the provider was in network, but the prescribed medication is non-formulary and requires prior authorization. Additionally, the requested quantity exceeds the plan limit of 30 tablets per 30 days. A manual review task has been created."

### 9.5 Layered Rules Architecture

Business rules should be organized into three layers so that federal policy, plan design, and customer-specific overrides never become entangled in a single monolithic rule set:

- **Layer 1 — Federal/public policy:** rules derived from CMS NCD/LCD determinations and other federal requirements. Apply universally, change infrequently.
- **Layer 2 — Plan configuration:** rules specific to a plan design (e.g. Commercial Silver, Commercial Gold, Employer Plan A, Medicare Advantage demonstration plan).
- **Layer 3 — Customer-specific overrides:** rules that override or extend the above for a specific customer or contract.

## 10. Data and Terminology Standards

This section answers the question "which open, authoritative data sources and terminology standards should the prototype use instead of fabricated data?" It is organized into four tiers by priority.

### 10.1 Tier 1 — Definitely Use

- **RxNorm**⁵ — normalized medication naming and relationships. *Example:* Ozempic → semaglutide → GLP-1 receptor agonist → 0.25 mg, 0.5 mg, 1 mg doses.
- **ICD-10-CM** — diagnosis coding. *Examples:* E11.9 (Type 2 diabetes without complications), J18.9 (pneumonia, unspecified organism), I10 (essential hypertension).
- **CPT** — procedure coding. *Examples:* 99213 (established patient office visit), 93000 (electrocardiogram), 45378 (diagnostic colonoscopy). CPT codes are licensed by the American Medical Association; the prototype should use only a small, curated subset rather than the full code set.
- **LOINC**⁶ — laboratory and clinical observation coding. *Example:* Hemoglobin A1c = LOINC 4548-4.

### 10.2 Tier 2 — Strongly Recommended

- **CMS National Coverage Determinations (NCD)**⁷ — for example, an MRI is covered only if a neurological deficit is present or conservative therapy has failed. Implementing roughly ten NCDs well is more valuable than implementing many superficially.
- **Medicare Local Coverage Determinations (LCD)**⁸ — regional coverage policies that supplement NCDs.
- **NPI Registry** — the National Provider Identifier registry, used to validate provider eligibility. *Example:* provider NPI 1234567890, specialty cardiology, status active.

### 10.3 Tier 3 — Excellent If Time Allows

- **Synthetic FHIR datasets** covering resource types including Patient, MedicationRequest, Coverage, Claim, ExplanationOfBenefit, AllergyIntolerance, Condition, Encounter, Observation, MedicationDispense, Organization, Practitioner, CoverageEligibilityRequest, CoverageEligibilityResponse, PriorAuthorization, and ClaimResponse.
- **Synthea**⁹˒¹⁰ — an open-source synthetic patient generator from The MITRE Corporation that produces millions of synthetic patients with realistic demographics, diagnoses, medications, allergies, encounters, labs, insurance coverage, procedures, and vaccinations.

### 10.4 Tier 4 — Very Useful

- **OHDSI OMOP Common Data Model**¹¹ — a standardized data model used widely by pharmaceutical companies and payers for observational health data.
- **CMS Open Data** — provider directories, hospital quality metrics, procedure utilization, payment statistics, coverage information, and drug spending data.

### 10.5 What Not to Use

- Random, fabricated JSON records.
- Fake or invented diagnosis names.
- Fake or invented medication names.
- Made-up CPT numbers.
- Arbitrary, undocumented business rules.

### 10.6 Recommended Reference Architecture

Data should flow: **FHIR Patient → Coverage → Eligibility Service → Rules Engine → Prior Authorization Service → Formulary Service → Clinical Decision Service → Claim Response** — backed underneath by FHIR resources, RxNorm, ICD-10, a curated CPT subset, the NPI registry, CMS NCD rules, and synthetic patients.

### 10.7 Recommended "Mini Payer Knowledge Base"

| Component | Target Size |
|---|---|
| ICD-10 diagnoses | 500–1,000 codes |
| RxNorm medications | 500–1,000 medications |
| CPT procedures | 100–200 procedures (curated subset) |
| CMS-inspired medical necessity rules | 20–30 rules |
| Synthetic FHIR patient records | Several, generated via Synthea |
| Configurable insurance plans | 5–10 plans (e.g., Commercial Silver, Commercial Gold, Medicare Advantage Demo, Medicaid Demo, Employer PPO), defined in JSON or YAML |

## 11. Data Acquisition and Validation Plan

> **⚠️ Illustrative commands — not runnable as-is.** The snippets below are from the
> archived PRD. They use `Authorization: Bearer` whereas this platform's gateway expects
> the `apikey` header, and some hosts/URLs are stale. For verified, no-auth sources and
> working commands, use the data-engineering prework (`data/reference/README.md` +
> `data/scripts/fetch_reference_data.py`).

This section answers "how do we actually obtain this reference data, and how do we check what already exists on the platform before importing anything new?" The recommended approach treats these sources as reference/terminology and plan-rule inputs — not as a full production database. Importantly, the existing platform already runs a HAPI FHIR JPA R4 server on a Neon PostgreSQL database named "fhirdb," and already has Synthea-generated bundles and loading scripts, so existing data should be checked first before any new import.

### 11.1 Best Sources by Data Type

| Data Type | Source |
|---|---|
| Medication vocabulary | RxNorm — NLM full-release ZIP archive |
| Diagnoses | ICD-10-CM — CDC/CMS |
| Lab codes | LOINC — free registered account required |
| Medicare coverage rules | CMS NCD/LCD database — exportable to Excel |
| Synthetic patients | Synthea (MITRE) |
| Procedures | CPT/HCPCS — small curated subset only (AMA-licensed; do not redistribute full code set) |

### 11.2 Reference Data Download Commands

The following commands establish a local reference-data folder structure and download the RxNorm full release:

```bash
mkdir -p data/reference/{rxnorm,icd10,loinc,cms-ncd,cpt-sample,npi}

cd data/reference/rxnorm
curl -L -o RxNorm_full_current.zip \
  https://download.nlm.nih.gov/umls/kss/rxnorm/RxNorm_full_current.zip
unzip RxNorm_full_current.zip
```

ICD-10-CM, LOINC, and CMS NCD/LCD data require manual download steps: ICD-10-CM code files are published by the CDC/CMS and downloaded manually; LOINC requires creating a free Regenstrief account before download;¹² the CMS NCD/LCD coverage database can be exported directly to Excel from the CMS coverage database web interface.¹³

A small, curated CPT sample (well within licensing limits) can be created directly as a CSV file:

```bash
cat > data/reference/cpt-sample/cpt_sample.csv <<'EOF'
code,display,category
99213,Established patient office visit,office_visit
93000,Electrocardiogram,diagnostic
80053,Comprehensive metabolic panel,lab
83036,Hemoglobin A1c,lab
45378,Diagnostic colonoscopy,procedure
EOF
```

### 11.3 Checking the Existing FHIR Server Before Importing

Before importing anything new, confirm what already exists on the platform's FHIR server:

```bash
export FHIR_BASE="http://localhost:8080/fhir"
# Alternative, via the Kong gateway:
# export FHIR_BASE="http://localhost:8000/fhir"
# export FHIR_API_KEY="<key>"

curl -s "$FHIR_BASE/metadata" | jq '.fhirVersion'
```

Resource counts can be checked in a loop across all relevant resource types:

```bash
for r in Patient Coverage Claim ClaimResponse ExplanationOfBenefit \
         MedicationRequest MedicationDispense MedicationStatement \
         AllergyIntolerance Condition Encounter Observation \
         Organization Practitioner Task Provenance RiskAssessment \
         GuidanceResponse ServiceRequest; do
  count=$(curl -s "$FHIR_BASE/$r?_summary=count" \
    -H "Authorization: Bearer $FHIR_API_KEY" | jq '.total')
  echo "$r: $count"
done
```

Representative sample pulls, with field projections, for the most relevant resource types:

```bash
curl -s "$FHIR_BASE/Patient?_count=3" | jq '.entry[].resource'
curl -s "$FHIR_BASE/MedicationRequest?_count=5" | jq '.entry[].resource'
curl -s "$FHIR_BASE/Coverage?_count=5" | jq '.entry[].resource'
```

### 11.4 Direct Database Inspection (Diagnostics Only)

Direct PostgreSQL/HAPI inspection is useful for diagnostics but should never be treated as the application's contract — the FHIR API remains the contract for all application logic. Connect using either the full connection string or discrete variables:

```bash
psql "$SPRING_DATASOURCE_URL"
# — or —
psql "host=$PGHOST port=5432 dbname=fhirdb user=$PGUSER \
  password=$PGPASSWORD sslmode=require"
```

Useful diagnostic queries:

```sql
-- Resource-type counts
SELECT res_type, COUNT(*) FROM hfj_resource
GROUP BY res_type ORDER BY count DESC;

-- Recently updated resources
SELECT * FROM hfj_resource ORDER BY updated DESC LIMIT 25;

-- Payer/claims resource check
SELECT res_type, COUNT(*) FROM hfj_resource
WHERE res_type IN ('Coverage','Claim','ClaimResponse',
  'ExplanationOfBenefit','Task','Provenance','RiskAssessment',
  'GuidanceResponse','ServiceRequest')
GROUP BY res_type;

-- Clinical resource check
SELECT res_type, COUNT(*) FROM hfj_resource
WHERE res_type IN ('Patient','MedicationRequest','MedicationStatement',
  'MedicationDispense','AllergyIntolerance','Condition','Encounter',
  'Observation')
GROUP BY res_type;
```

### 11.5 "Complete Enough" Dataset Sizing

| Resource / Dataset | Target Count |
|---|---|
| Patients | 10–25 |
| Coverage | 5–10 |
| MedicationRequest | 20–50 |
| AllergyIntolerance (including penicillin) | 5–10 |
| Condition (including diabetes, hypertension) | 20–50 |
| Claim | 10 |
| ClaimResponse | 10 |
| Task | 3–5 |
| Provenance | 1 per decision |
| RxNorm subset | 50–200 medications |
| Formulary rules | 20–50 rules |
| Prior-authorization rules | 10–20 rules |

### 11.6 Recommended Next Move

Build a small, dedicated payer-knowledge-base folder (CSV/JSON files for the RxNorm subset, formulary, prior-authorization rules, and plan definitions), and seed the FHIR server with only the patient, coverage, claim, and audit resources needed for the demonstration — rather than attempting to load a full production-scale reference dataset.

## 12. Frequently Asked Questions, by Discipline

This section is written to stand on its own for readers who want discipline-specific answers without reading the full document end to end. Where a question requires deeper technical detail, it points to the relevant section above rather than repeating it in full.

### 12.1 For Business and Executive Stakeholders

**Q: Why is the scope limited to medication-prescription payer workflows instead of the full breadth of payer operations?**
A: A narrow scope keeps the prototype credible and demonstrable within the time available, and it maps directly onto enterprise claims-adjudication modernization and "Adjudication as a Service." A broad "payer operations" framing would dilute the story and make the project harder to evaluate on its merits. See Section 3.2 and Section 5.

**Q: How does wrapping a legacy IBM i/AS400 system, rather than replacing it, reduce risk?**
A: The design applies the strangler (fig) pattern: new functionality is introduced behind an API façade while the legacy adjudication core continues running underneath, and functionality migrates incrementally rather than through a single high-risk cutover. This is the same pattern recommended by mainstream cloud architecture guidance for legacy modernization. See Section 6.5.

**Q: How does this align with regulatory compliance?**
A: The rules engine is explicitly grounded in CMS National and Local Coverage Determinations for medical necessity, and the architecture anticipates the CMS Interoperability and Prior Authorization Final Rule (CMS-0057-F), which sets new standards for electronic prior authorization. See Section 9 and Section 10.2.

**Q: What does success look like for this phase?**
A: A working demonstration that accepts a prescription claim, adjudicates it through eligibility, formulary, prior-authorization, and clinical-safety checks against a simulated legacy core, and produces both a structured decision (ClaimResponse) and a plain-language explanation of that decision — all while remaining explicitly scoped and auditable. See Section 2 and Section 5.2.

### 12.2 For Product Owners

**Q: Why does the MVP include only four checks (eligibility, formulary, prior authorization, and drug-allergy/duplicate therapy) rather than the full fifteen rule domains?**
A: The four checks in the MVP represent the highest-value, most demonstrable subset of the full fifteen-domain rule model described in Section 9.2. They exercise eligibility, coverage, safety, and cost-control logic — the core of what "adjudication" means — without requiring the full breadth of a production rules engine.

**Q: What was explicitly cut from scope, and why?**
A: Coordination of Benefits (COB) and a full pharmacy benefit manager (PBM) platform were both cut. COB is a legitimate and important real-world topic, but determining which of two payers is primary adds significant complexity without adding much demonstration value at this stage. See Section 5.3.

**Q: How should the rules engine be sized for this phase?**
A: A representative set of 15–20 rules spanning roughly eight domains (eligibility, provider, formulary, prior authorization, clinical, coding, medical necessity, and quantity) is sufficient to demonstrate the rules-engine pattern convincingly. See Section 9.3.

**Q: What is the minimum dataset needed to make the demo believable?**
A: The "Mini Payer Knowledge Base" outlined in Section 10.7 — roughly 500–1,000 ICD-10 diagnoses, 500–1,000 RxNorm medications, 100–200 curated CPT procedures, 20–30 CMS-inspired medical necessity rules, a handful of Synthea-generated synthetic patients, and 5–10 configurable insurance plans — is the recommended floor.

### 12.3 For Solution Architects

**Q: Why strangler pattern, API façade, and anti-corruption layer specifically?**
A: Together, these three patterns let the platform introduce new, testable services in front of a legacy adjudication core without a risky rewrite: the strangler pattern governs the migration path, the API façade gives consumers one stable interface, and the anti-corruption layer keeps legacy data shapes from leaking into the canonical FHIR-aligned domain model. See Section 6.1 and Section 6.5.

**Q: Why split the stack between Spring Boot and Python/FastAPI instead of building everything in one language?**
A: Spring Boot carries the claims façade, benefit rules, legacy adapter, and claim domain APIs — directly matching the platform's Java/Spring/JDBC/Hibernate needs — while Python/FastAPI is reserved for MCP/agent orchestration and optional CDS support. This keeps deterministic business logic in a strongly-typed, enterprise-standard stack while isolating AI orchestration in a separate, clearly-labeled layer. See Section 6.2.

**Q: How does the rules engine avoid becoming an unmaintainable pile of conditional logic?**
A: Rules are organized into three explicit layers: federal/public policy (CMS NCD/LCD), plan configuration (e.g., Commercial Silver, Commercial Gold, Employer Plan A, Medicare Advantage Demo), and customer-specific overrides. Each layer can change independently without destabilizing the others. See Section 9.5.

**Q: Which data standards should be used, and which should be avoided?**
A: Use RxNorm, ICD-10-CM, a small licensed CPT subset, LOINC, CMS NCD/LCD, the NPI registry, and Synthea-generated synthetic FHIR patients. Avoid fabricated JSON, invented diagnosis or medication names, made-up CPT codes, and arbitrary undocumented rules. See Section 10.1 through Section 10.5.

**Q: What does the end-to-end reference architecture look like?**
A: FHIR Patient → Coverage → Eligibility Service → Rules Engine → Prior Authorization Service → Formulary Service → Clinical Decision Service → Claim Response, with RxNorm, ICD-10, a curated CPT subset, the NPI registry, CMS NCD rules, and synthetic patients as the underlying reference data. See Section 10.6.

### 12.4 For Developers

**Q: What are the three services, and what does each one own?**
A: (1) The Claim Intake + Legacy Adapter Service is a Spring Boot API that validates incoming prescription claim requests, maps them to canonical claim objects, and calls the simulated IBM i adjudication backend. (2) The Benefit + Prior Auth Rules Service evaluates deterministic rules covering formulary status, coverage status, prior-authorization requirements, and manual-review triggers. (3) The MCP Explanation Agent calls the underlying APIs and generates a natural-language explanation of the adjudication outcome. See Section 6.3.

**Q: How do I simulate the legacy IBM i/RxClaim core without a real IBM i environment?**
A: Implement a simulated RPG/CL-style adjudication function, represent DB2/SQL400-like tables using PostgreSQL tables or JSON fixtures, expose a REST façade in Java/Spring Boot, and write an anti-corruption layer that converts the legacy field shapes into canonical FHIR/claim domain objects before they reach the rest of the platform. See Section 6.1.

**Q: Where do I get reference data, and what commands should I run to fetch it?**
A: See the exact download commands, folder structure, and curated CPT CSV sample in Section 11.2. RxNorm can be downloaded directly via curl; ICD-10-CM, LOINC, and CMS NCD/LCD require manual or account-gated downloads as noted there.

**Q: How do I check what already exists on the FHIR server before importing anything new?**
A: Use the FHIR metadata and resource-count commands in Section 11.3 (via curl and jq against `$FHIR_BASE`), and, for diagnostics only, the direct PostgreSQL queries against the hfj_resource table in Section 11.4. Treat the FHIR API, not the raw database, as the application's actual contract.

**Q: What dataset sizes should I target so the demo feels complete without over-building?**
A: See the sizing table in Section 11.5 — for example, 10–25 patients, 5–10 Coverage resources, 20–50 MedicationRequest resources, and 10–20 prior-authorization rules. These are deliberately modest targets sized for a convincing demonstration rather than a production system.

## 13. Open Questions, Risks, and Next Steps

This document remains a work in progress. The following items are explicitly open and should be resolved as the prototype matures:

- **Coordination of Benefits (COB):** confirm whether COB should remain fully out of scope for Phase 2, or whether a minimal, illustrative COB rule should be added given how commonly it appears in real adjudication (see Section 9.2, rule 15, and Section 5.3).
- **CPT licensing:** confirm the exact boundaries of permissible use for the curated CPT subset given AMA licensing terms before any public sharing of the prototype or its data.
- **Five-service vs. three-slice decomposition:** validate that collapsing the original five-service design into three deployable slices (Section 6.3) does not lose any architectural nuance that was intentional in the original design.
- **CDS as sub-module:** decide whether clinical decision support should remain a sub-module of the Benefit + Prior Auth Rules Service indefinitely, or should be split out once the platform grows.
- **Dataset seeding scope:** finalize the exact patient, coverage, and claim counts to seed (Section 11.5) based on how much manual review time is available before the demonstration.
- **NCPDP SCRIPT depth:** determine how much of the NCPDP SCRIPT standard for Part D prior authorization needs to be modeled explicitly versus referenced conceptually (Section 9.2, rule 6).
- **Naming finalization:** confirm the final headline and subtitle language in Section 4 with any additional stakeholders before using it externally.

## 14. References

The following sources were used to ground the regulatory, technical, and data-standards content in this document. Numbered citations in the text correspond to the footnote markers used throughout.

1. Microsoft Azure Architecture Center, "Strangler Fig Pattern." https://learn.microsoft.com/en-us/azure/architecture/patterns/strangler-fig
2. CMS, "CMS Interoperability and Prior Authorization Final Rule" (CMS-0057-F) overview. https://www.cms.gov/initiatives/burden-reduction/overview/interoperability/policies-regulations/cms-interoperability-prior-authorization-final-rule-cms-0057-f
3. CMS, "Medicare Coverage Determination Process" (National and Local Coverage Determinations). https://www.cms.gov/medicare/coverage/determination-process
4. CMS, "E-Prescribing Standards and Requirements." https://www.cms.gov/medicare/regulations-guidance/electronic-prescribing/adopted-standard-and-transactions
5. U.S. National Library of Medicine, "RxNorm" overview. https://www.nlm.nih.gov/research/umls/rxnorm/index.html
6. Regenstrief Institute, "LOINC Data Standards." https://www.regenstrief.org/real-world-solutions/loinc/
7. CMS, "Medicare Coverage Determination Process" (NCD/LCD). https://www.cms.gov/medicare/coverage/determination-process
8. CMS, "Medicare Coverage Determination Process" (NCD/LCD). https://www.cms.gov/medicare/coverage/determination-process
9. The MITRE Corporation, "Synthea" downloads. https://synthea.mitre.org/downloads
10. The MITRE Corporation, "Synthea" GitHub repository. https://github.com/synthetichealth/synthea
11. OHDSI, "Standardized Data: The OMOP Common Data Model." https://www.ohdsi.org/data-standardization/
12. Regenstrief Institute, "LOINC Data Standards." https://www.regenstrief.org/real-world-solutions/loinc/
13. CMS, "Medicare Coverage Determination Process" (National and Local Coverage Determinations). https://www.cms.gov/medicare/coverage/determination-process

**Additional sources referenced in the document:**

- HL7 Da Vinci Project, "Prior Authorization Support (PAS)" Implementation Guide. https://build.fhir.org/ig/HL7/davinci-pas/
- HL7 Da Vinci Project, "Coverage Requirements Discovery (CRD)" Implementation Guide. https://projectlifedashboard.hl7.org/specifications/hl7-fhir-us-davinci-crd1-1-0-ballot/
- CMS, "CMS Interoperability and Prior Authorization Final Rule" fact sheet (CMS-0057-F). https://www.cms.gov/newsroom/fact-sheets/cms-interoperability-prior-authorization-final-rule-cms-0057-f
- NLM RxNorm full-release archive (referenced directly in commands). https://download.nlm.nih.gov/umls/kss/rxnorm/RxNorm_full_current.zip
