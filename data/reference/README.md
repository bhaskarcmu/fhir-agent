# Phase 2 — Reference & Synthetic Data (data-engineering prework)

> **Not part of the documentation PR.** This lives on the local `dataeng/phase2-prework`
> branch. Raw downloads (Synthea jar, CMS zips, formulary PUF) are **gitignored**;
> only small, public-domain, curated derivatives and this README are tracked.
> Everything here is reproducible from the scripts noted below.
>
> All sources verified reachable & **no-auth** from this environment on 2026-07-13.

## TL;DR — what to use for the adjudication demo

- **Synthesize patients/claims:** Synthea v4.0.0 JAR → Patient, Condition, MedicationRequest,
  AllergyIntolerance, **Claim**, **ExplanationOfBenefit** (validated: 657 Claim + 657 EOB from a
  p=3 run). Bias the cohort with a `-k` keep-module (diabetes + penicillin allergy).
- **Formulary/PA/step-therapy/quantity rules (REAL):** CMS Medicare Part D Formulary PUF (per-NDC
  tier + PA + ST + QL flags). 2.4 GB — URL documented; pull a slice when needed.
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
| **CMS Part D Formulary PUF** | ⏳ referenced (2.4 GB) | `data.cms.gov/sites/default/files/2026-04/65e8dafd-c42b-4c2a-93c2-551bbc80bef9/SPUF_2026_20260408.zip` | none | US Gov / public domain | **Real** per-NDC formulary status, tier, PA, step-therapy, quantity-limit flags |
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
- **CMS HTML pages 403 automated fetchers** but the underlying files on `data.cms.gov` / `downloads.cms.gov`
  download fine (verified). `synthea.mitre.org` is unreachable here — use the GitHub JAR.
- **RxNorm full monthly release** needs a UMLS login; we deliberately use the **no-auth RxNav API**
  instead, which is sufficient for RxCUI + class resolution.
