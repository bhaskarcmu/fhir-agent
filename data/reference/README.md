# Phase 2 — Reference & Synthetic Data (data-engineering prework)

> **Data-engineering working notes** (source catalog + synthesis tooling). Raw downloads
> (Synthea jar, CMS zips, formulary PUF) are **gitignored**; only small, public-domain,
> curated derivatives and this README are tracked. Everything here is reproducible from the
> scripts noted below.
>
> All sources verified reachable & **no-auth** from this environment (terminology + Medicare
> sources 2026-07-13; ACA/commercial sources 2026-07-14). Use `curl` for `www.cms.gov`
> (automated fetchers get 403; `curl` returns 200).

## TL;DR — what to use for the adjudication demo

- **Synthesize patients/claims:** Synthea v4.0.0 JAR → Patient, Condition, MedicationRequest,
  AllergyIntolerance, **Claim**, **ExplanationOfBenefit** (validated: 657 Claim + 657 EOB from a
  p=3 run). Bias the cohort with a `-k` keep-module (diabetes + penicillin allergy).
- **Formulary/PA/step-therapy/quantity rules — Medicare (REAL):** CMS Medicare Part D Formulary PUF
  (per-NDC tier + PA + ST + QL flags). 2.4 GB — URL documented; pull a slice when needed.
- **Formulary/PA/step-therapy/quantity rules — Commercial (REAL):** ACA **QHP machine-readable
  formulary** files — per-drug **tier + prior_authorization + step_therapy + quantity_limit**, keyed
  by **rxnorm_id + HIOS plan_id**. Sampled locally (`aca-commercial/example_qhp_formulary_records.json`).
- **Drug normalization & class:** RxNav REST API (RxCUI + ATC/VA class) — no download needed.
- **Diagnoses:** NLM Clinical Tables API (on-demand validation) + CDC full ICD-10-CM zip.
- **Medical-necessity rules:** CMS NCD export (downloaded).
- **Provider eligibility:** NPPES NPI API.
- **Canonical Claim/ClaimResponse shape:** HL7 Da Vinci PAS IG (reference) + local Synthea samples.

## Inventory

| Source | Status | Location / URL | Auth | License | Adjudication use |
|---|---|---|---|---|---|
| **Synthea v4.0.0 JAR** | ✅ downloaded (188 MB, gitignored) | `data/synthea/synthea-with-dependencies.jar` · `github.com/synthetichealth/synthea/releases/download/v4.0.0/synthea-with-dependencies.jar` | none | Apache-2.0 | Generate Patient/Condition/MedicationRequest/AllergyIntolerance/Claim/EOB transaction bundles |
| **Synthea sample output** | ✅ generated (p=3, gitignored) | `data/synthea/output/fhir/` | — | Apache-2.0 (synthetic) | Validated payer/claims emission |
| **RxNorm / RxClass** | ✅ derivative pulled | `rxnorm/rxnorm_drug_classes.csv` (20 drugs, real RxCUI + ATC) · `rxnav.nlm.nih.gov/REST/` | none | Public domain | Normalize drug→RxCUI→ATC class for drug-allergy, duplicate/step-therapy, formulary |
| **ICD-10-CM** | ✅ derivative pulled | `icd10/icd10cm_subset.csv` (153 codes) · full set: `ftp.cdc.gov/.../ICD10CM/2026/icd10cm-Code Descriptions-2026.zip` | none | Public domain | Diagnosis validation, coding-coherence & medical-necessity edits |
| **CMS NCD export** | ✅ downloaded (gitignored) | `cms-ncd/ncd.mdb`, `ncd_csv.zip` · `downloads.cms.gov/medicare-coverage-database/downloads/exports/ncd.zip` | none | US Gov / public domain | Medical-necessity (Layer-1 federal rules) |
| **CMS Part D Formulary PUF** (Medicare) | ⏳ referenced (2.4 GB) | `data.cms.gov/sites/default/files/2026-04/65e8dafd-c42b-4c2a-93c2-551bbc80bef9/SPUF_2026_20260408.zip` | none | US Gov / public domain | **Real** per-NDC formulary status, tier, PA, step-therapy, quantity-limit flags |
| **ACA QHP machine-readable formulary** (commercial) | ✅ sampled | `aca-commercial/example_qhp_formulary_records.json` (3 real records) + `issuer_index.json`. Chain: MR-URL PUF → issuer `index.json` → `drugs.json`. Entry: `download.cms.gov/marketplace-puf/2026/machine-readable-url-puf.zip` | none | US Gov / public | **Real** commercial per-drug **tier + PA + step-therapy + quantity-limit**, keyed by **rxnorm_id + HIOS plan_id** |
| **CMS Marketplace PUFs** (commercial) | ⏳ referenced | `download.cms.gov/marketplace-puf/2026/{benefits-and-cost-sharing,plan-attributes,business-rules,machine-readable-url}-puf.zip` (12.5 MB / 1 MB / 33 KB / 19 KB) | none | US Gov / public | Benefit-level coverage + cost-sharing (`IsEHB`), deductible/MOOP, `FormularyId`↔`FormularyURL` linkage |
| **ACA EHB benchmark plans** | ⏳ referenced | `cms.gov/marketplace/resources/data/essential-health-benefits` (per-state zips) | none | US Gov / public | The **floor** of what every ACA plan must cover (incl. Rx classes) |
| **Transparency in Coverage (TiC)** | ⏳ referenced (GBs) | payer indexes e.g. `transparency-in-coverage.uhc.com`; CMS-side URLs in Marketplace TiC PUF | none | US Gov / public | Pricing/negotiated-rate side only (not tier/PA/ST/QL); **do not ingest** |
| **QHP formulary JSON schema** | ⏳ referenced | `github.com/CMSgov/QHP-provider-formulary-APIs` | none | US Gov / public | Authoritative schema + validator for the commercial formulary files |
| **NPPES NPI** | ⏳ referenced (API) | `npiregistry.cms.hhs.gov/api/?version=2.1` · bulk: `download.cms.gov/nppes/NPPES_Data_Dissemination_July_2026_V2.zip` | none | Public / FOIA | Prescriber & pharmacy eligibility/taxonomy/active-status |
| **openFDA NDC/label** | ⏳ referenced (API) | `api.fda.gov/drug/ndc.json`, `api.fda.gov/drug/label.json` | none (key optional) | CC0-ish | NDC↔product resolution, labeling/contraindication signals |
| **Local Claim/EOB samples** | ✅ extracted | `samples/example_pharmacy_claim.json`, `samples/example_eob.json` | — | Apache-2.0 (synthetic) | Canonical `Claim`(type=pharmacy)/EOB shapes for our FHIR artefacts |
| **HL7 Da Vinci PAS** | ⏳ referenced | `build.fhir.org/ig/HL7/davinci-pas/` · `github.com/HL7/davinci-pas` | none | HL7 CC0 | Canonical request/response `Claim`↔`ClaimResponse` (PA number in `ClaimResponse.preAuthRef`) |
| **CMS DE-SynPUF** | ⏳ referenced | `www.cms.gov/.../de-synpuf`; OMOP on AWS Open Data `registry.opendata.aws/cmsdesynpuf-omop/` | none (CMS pages 403 bots) | Public domain | Real Part D pharmacy-claim field distributions (CSV → map to FHIR) |
| **CMS BCDA sandbox** | ⏳ referenced | `sandbox.bcda.cms.gov/`, `bcda.cms.gov/bcda-data.html` | generic token | US Gov | Synthetic FHIR EOB/Coverage NDJSON reference |

Legend: ✅ obtained locally · ⏳ verified + documented, pull on demand.

## Reproduce

```bash
# Small reference derivatives (ICD-10 subset + RxNorm/ATC classes):
python3 data/scripts/fetch_reference_data.py

# Small ACA commercial formulary sample (QHP 3-hop chain → 3 real drug records):
python3 data/scripts/fetch_aca_formulary_sample.py

# Synthea generator (already fetched to data/synthea/, gitignored):
#   curl -sL -o data/synthea/synthea-with-dependencies.jar \
#     https://github.com/synthetichealth/synthea/releases/download/v4.0.0/synthea-with-dependencies.jar

# Generate a claims-bearing R4 population (transaction bundles → loadable into HAPI):
java -jar data/synthea/synthea-with-dependencies.jar \
  -p 10 -s 20260713 \
  --exporter.baseDirectory data/synthea/output \
  --exporter.fhir.transaction_bundle true \
  Massachusetts
```

## Notes & caveats

- **Coverage not in default Synthea R4 export.** The p=3 run emitted Claim/EOB/Provenance/Organization
  but **no `Coverage`**. Synthea models payers internally; Coverage appears via the payer/US-Core
  config. For the demo we will **author `Coverage` in the claims seed** (grounded to our plan
  definitions), as `seed_demo.py` already does for its resources — don't assume Synthea provides it.
- **Part D Formulary PUF is 2.4 GB.** Don't commit or bulk-load it. When needed, download once,
  extract only the Basic-Drugs-Formulary table, and distill a **curated** subset into `data/payer-kb/`
  (Phase 2 plan M1). This keeps us within the "curated fixtures" requirement (R13) and avoids the
  AMA/CPT redistribution concern.
- **Commercial ≠ proprietary here.** Private insurers' *internal PA criteria and pricing* are
  proprietary, but the ACA-mandated *disclosure* layer (EHB, QHP machine-readable formularies) is
  **public** and carries the adjudication metadata (tier/PA/ST/QL). So both Medicare and commercial
  plans are grounded in real data; we model the **structure**, not the secret criteria. Issuer
  `drugs.json` files are multi-MB (the sampled one had 3,678 records) — **range-/temp-sample, don't
  commit whole.** Tiers vary by issuer (e.g., `PREFERRED-GENERIC-DRUGS`, `NON-FORMULARY-DRUGS`,
  `SPECIALTY-DRUGS`) — normalize them in the M1 payer-KB schema.
- **CMS HTML pages 403 automated fetchers** but the underlying files on `data.cms.gov` / `downloads.cms.gov`
  download fine (verified). `synthea.mitre.org` is unreachable here — use the GitHub JAR.
- **RxNorm full monthly release** needs a UMLS login; we deliberately use the **no-auth RxNav API**
  instead, which is sufficient for RxCUI + class resolution.

## Glossary — every abbreviation, expanded

**Organizations**
- **NIH** — National Institutes of Health (US medical-research agency).
- **NLM** — National Library of Medicine (part of NIH; publishes RxNorm, terminology APIs).
- **CDC** — Centers for Disease Control and Prevention (publishes ICD-10-CM).
- **CMS** — Centers for Medicare & Medicaid Services (runs Medicare/Medicaid; publishes formulary,
  coverage, and marketplace data).
- **FDA** — Food and Drug Administration (drug regulation; openFDA data).
- **WHO** — World Health Organization (owns the ATC drug classification).
- **HL7** — Health Level Seven (healthcare data-standards body; author of FHIR & Da Vinci).
- **MITRE** — nonprofit R&D operator; builds Synthea.
- **NPPES** — National Plan and Provider Enumeration System (CMS registry issuing NPIs).

**Terminologies / vocabularies**
- **RxNorm** — normalized medication naming (NLM); each drug has an **RxCUI** (RxNorm Concept Unique
  Identifier).
- **ATC** — Anatomical Therapeutic Chemical classification (WHO drug "family tree").
- **ICD-10-CM** — International Classification of Diseases, 10th rev., Clinical Modification
  (diagnosis codes).
- **SNOMED CT** — Systematized Nomenclature of Medicine, Clinical Terms (clinical concepts incl.
  allergies).
- **NDC** — National Drug Code (FDA drug-product identifier; formularies are keyed by NDC).
- **LOINC** — Logical Observation Identifiers Names and Codes (lab/observation codes).

**Programs, files & standards**
- **Part D** — Medicare's prescription-drug benefit.
- **PUF** — Public Use File (a dataset CMS publishes for anyone).
- **SPUF** — the quarterly Part D formulary PUF bundle.
- **Formulary** — a plan's list of covered drugs + their tier/PA/step-therapy/quantity rules.
- **PA** — Prior Authorization. **ST** — Step Therapy. **QL** — Quantity Limit.
- **NCD / LCD** — National / Local Coverage Determination (CMS medical-necessity rulings).
- **NPI** — National Provider Identifier.
- **ACA** — Affordable Care Act.
- **EHB** — Essential Health Benefits (10 categories ACA plans must cover, incl. Rx).
- **QHP** — Qualified Health Plan (an ACA marketplace plan; must publish machine-readable formularies).
- **HIOS** — Health Insurance Oversight System; a **HIOS plan ID** is the 14-char marketplace plan id.
- **MR-URL PUF** — Machine-Readable URL PUF (lists each issuer's `index.json`).
- **MOOP** — Maximum Out-Of-Pocket. **Accumulators** — running deductible/MOOP totals.
- **TiC** — Transparency in Coverage (payer negotiated-rate machine-readable files; pricing-focused).
- **SBC** — Summary of Benefits and Coverage (standardized plan summary document).
- **SERFF** — System for Electronic Rate and Form Filing (state insurance filings).
- **PDL** — Preferred Drug List (state Medicaid formulary; public non-Medicare example).
- **FHIR** — Fast Healthcare Interoperability Resources (HL7's modern data-exchange standard).
- **Da Vinci PAS** — HL7 Da Vinci **Prior Authorization Support** implementation guide (canonical
  `Claim`/`ClaimResponse` shapes).
- **DE-SynPUF** — Data Entrepreneurs' Synthetic Public Use File (CMS synthetic Medicare claims).
- **BCDA** — Beneficiary Claims Data API (CMS; synthetic FHIR EOB/Coverage sandbox).
- **OMOP** — Observational Medical Outcomes Partnership common data model (OHDSI).
