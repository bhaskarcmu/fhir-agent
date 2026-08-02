"""
Knowledge base retrieval for drug-safety citations (docs/phase6/design.md
Section 4.6, decisions.md H15): openFDA Drug Label API (boxed warnings,
contraindications) and RxClass API (NLM/RxNav, drug-class relationships).
Both free, no auth, confirmed live 2026-08-02.

The non-clinical-judgment constraint is structural, not a prompt
instruction: every function here is called strictly AFTER
triage-service has already returned a determination, to fetch citation
TEXT for a decision that already exists -- never before, as an input
the agent reasons over. Nothing in this module makes or influences a
clinical decision; it only looks up reference text for one that already
happened. Callers (agent.py) must never call these before
submit_decision resolves.

openFDA's own `openfda.rxcui` field lists product-level RxNorm codes
(e.g. a specific labeled product), not the ingredient-level codes this
repo's FHIR data actually carries (confirmed live: RXCUI 723 for plain
amoxicillin 404s against openFDA's rxcui search) -- so the drug label
lookup is by generic name, extracted from the medication's display text,
not by RXCUI. RxClass, by contrast, works directly with the same
ingredient-level RXCUI already on hand (confirmed live).
"""

from __future__ import annotations

import re

import httpx

OPENFDA_LABEL_URL = "https://api.fda.gov/drug/label.json"
RXCLASS_BY_RXCUI_URL = "https://rxnav.nlm.nih.gov/REST/rxclass/class/byRxcui.json"

# How many distinct drug classes to surface -- RxClass returns dozens of
# overlapping classification-scheme entries per drug; a handful of
# distinct class names is a citation, not a research dump.
MAX_DRUG_CLASSES = 5


def extract_generic_name(display: str) -> str:
    """
    "Amoxicillin 500 MG Oral Capsule" -> "Amoxicillin". Medication.display
    strings are FHIR/RxNorm "clinical drug" names: generic name, then a
    dose/form description starting with the first number. Everything
    before that first number is the drug name.
    """
    match = re.split(r"\s+\d", display, maxsplit=1)
    return match[0].strip() if match else display.strip()


def fetch_drug_label_citation(generic_name: str) -> dict | None:
    """
    openFDA Drug Label API: boxed_warning/contraindications for a drug,
    looked up by generic name. Returns None if openFDA has no matching
    label (a real, expected outcome -- not every drug has FDA label data
    indexed, and this is never treated as an error) or on any request
    failure -- retrieval failing must never block the decision it would
    have cited.
    """
    try:
        response = httpx.get(
            OPENFDA_LABEL_URL,
            params={"search": f'openfda.generic_name:"{generic_name.upper()}"', "limit": 1},
            timeout=10.0,
        )
    except httpx.HTTPError:
        return None

    if response.status_code == 404:
        return None
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError:
        return None

    results = response.json().get("results") or []
    if not results:
        return None

    label = results[0]
    boxed_warning = (label.get("boxed_warning") or [None])[0]
    contraindications = (label.get("contraindications") or [None])[0]
    if not boxed_warning and not contraindications:
        return None

    return {
        "source": "openFDA Drug Label API",
        "boxed_warning": boxed_warning,
        "contraindications": contraindications,
    }


def fetch_drug_class(rxcui: str) -> list[dict]:
    """
    RxClass API (NLM/RxNav): drug-class relationships for an RxNorm code.
    Returns [] on any failure or when nothing is found -- same
    never-block-the-decision discipline as fetch_drug_label_citation.
    Deduplicated by class name, capped at MAX_DRUG_CLASSES.
    """
    try:
        response = httpx.get(RXCLASS_BY_RXCUI_URL, params={"rxcui": rxcui}, timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPError:
        return []

    entries = response.json().get("rxclassDrugInfoList", {}).get("rxclassDrugInfo") or []
    seen: set[str] = set()
    classes: list[dict] = []
    for entry in entries:
        item = entry.get("rxclassMinConceptItem", {})
        name = item.get("className")
        if not name or name in seen:
            continue
        seen.add(name)
        classes.append({"class_name": name, "class_type": item.get("classType", "")})
        if len(classes) >= MAX_DRUG_CLASSES:
            break
    return classes
