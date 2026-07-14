#!/usr/bin/env python3
"""
Fetch REAL, no-login reference data for the Phase 2 claims-adjudication prototype.

Sources (all public, no API key):
  - ICD-10-CM diagnoses .... NLM Clinical Tables API (clinicaltables.nlm.nih.gov)
  - RxNorm + drug class .... RxNav REST API (rxnav.nlm.nih.gov) incl. RxClass (ATC)

Writes curated CSVs under data/reference/. Those files are gitignored — this
script is the reproducible source of truth, not the downloaded output.

Usage:  python3 data/scripts/fetch_reference_data.py
"""
from __future__ import annotations

import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REF = Path(__file__).resolve().parents[1] / "reference"
ICD_DIR = REF / "icd10"
RX_DIR = REF / "rxnorm"

# Clinical domains relevant to the adjudication demo (grounds Condition + coding rules).
ICD_TERMS = [
    "type 2 diabetes", "type 1 diabetes", "essential hypertension",
    "pneumonia", "asthma", "hyperlipidemia", "atrial fibrillation",
    "chronic kidney disease", "major depressive disorder", "gastro-esophageal reflux",
]

# Curated drug list spanning our rule domains: penicillins (allergy), ACE/ARB (dup
# therapy), high-cost PA drugs (semaglutide, adalimumab), statins, PPIs, SSRIs.
DRUGS = [
    "amoxicillin", "ampicillin", "penicillin V potassium", "piperacillin",
    "lisinopril", "enalapril", "losartan", "valsartan",
    "atorvastatin", "simvastatin", "omeprazole", "pantoprazole",
    "sertraline", "fluoxetine", "semaglutide", "adalimumab",
    "metformin", "amlodipine", "levothyroxine", "albuterol",
]

TIMEOUT = 20


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
        return r.read()


def fetch_icd10() -> int:
    ICD_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for term in ICD_TERMS:
        q = urllib.parse.quote(term)
        url = (
            "https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search"
            f"?terms={q}&maxList=25&sf=code,name&df=code,name"
        )
        data = json.loads(_get(url))
        for code, name in data[3]:
            if code not in seen:
                seen.add(code)
                rows.append((code, name, term))
        time.sleep(0.1)
    out = ICD_DIR / "icd10cm_subset.csv"
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["code", "display", "matched_term"])
        w.writerows(sorted(rows))
    print(f"  ICD-10-CM: {len(rows)} codes -> {out.relative_to(REF.parent.parent)}")
    return len(rows)


def _rxcui(name: str) -> str | None:
    url = f"https://rxnav.nlm.nih.gov/REST/rxcui.json?name={urllib.parse.quote(name)}"
    ids = json.loads(_get(url)).get("idGroup", {}).get("rxnormId", [])
    return ids[0] if ids else None


def _atc_classes(rxcui: str) -> list[str]:
    url = (
        "https://rxnav.nlm.nih.gov/REST/rxclass/class/byRxcui.json"
        f"?rxcui={rxcui}&relaSource=ATC"
    )
    info = json.loads(_get(url)).get("rxclassDrugInfoList", {}).get("rxclassDrugInfo", [])
    names = {i["rxclassMinConceptItem"]["className"] for i in info}
    return sorted(names)


def fetch_rxnorm() -> int:
    RX_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for drug in DRUGS:
        try:
            rxcui = _rxcui(drug)
            classes = _atc_classes(rxcui) if rxcui else []
            rows.append({"drug": drug, "rxcui": rxcui or "", "atc_classes": "; ".join(classes)})
            print(f"    {drug:26} rxcui={rxcui or '?':>8}  {('; '.join(classes))[:60]}")
        except Exception as e:  # noqa: BLE001 - best-effort enrichment
            rows.append({"drug": drug, "rxcui": "", "atc_classes": f"ERROR: {e}"})
            print(f"    {drug:26} ERROR {e}")
        time.sleep(0.1)
    out = RX_DIR / "rxnorm_drug_classes.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["drug", "rxcui", "atc_classes"])
        w.writeheader()
        w.writerows(rows)
    print(f"  RxNorm: {len(rows)} drugs -> {out.relative_to(REF.parent.parent)}")
    return len(rows)


def main() -> int:
    print("Fetching ICD-10-CM (NLM Clinical Tables)...")
    fetch_icd10()
    print("Fetching RxNorm + ATC classes (RxNav)...")
    fetch_rxnorm()
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
