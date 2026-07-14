#!/usr/bin/env python3
"""
Build a small NDC ↔ RxCUI crosswalk for the demo drug set (no login).

WHY: our rules/triage engine keys on **RxNorm (RxCUI)**, but formularies (CMS Part D,
ACA QHP) key on **NDC** (National Drug Code). Adjudication needs to line the two up, so a
claim's NDC resolves to the RxCUI the clinical rules use.

Source: openFDA NDC directory (api.fda.gov/drug/ndc.json) — public, no key required.
Input:  data/reference/rxnorm/rxnorm_drug_classes.csv (drug, rxcui, ...)
Output: data/payer-kb/crosswalk/ndc_rxcui.csv (rxcui, drug, product_ndc, brand_name)

Usage:  python3 data/scripts/build_ndc_rxcui_crosswalk.py
"""
from __future__ import annotations

import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "reference" / "rxnorm" / "rxnorm_drug_classes.csv"
OUT = ROOT / "payer-kb" / "crosswalk" / "ndc_rxcui.csv"
TIMEOUT = 20


def _openfda_ndc(generic: str) -> tuple[str, str] | None:
    q = urllib.parse.quote(f'generic_name:"{generic}"')
    url = f"https://api.fda.gov/drug/ndc.json?search={q}&limit=1"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            res = json.loads(r.read()).get("results", [])
        if not res:
            return None
        rec = res[0]
        return rec.get("product_ndc", ""), (rec.get("brand_name") or rec.get("generic_name") or "")
    except Exception:  # noqa: BLE001 - best-effort; some ingredients have no NDC match
        return None


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    with SRC.open() as f:
        for r in csv.DictReader(f):
            drug, rxcui = r["drug"], r["rxcui"]
            # openFDA generic_name is typically the base ingredient (first token works well)
            generic = drug.split()[0]
            hit = _openfda_ndc(generic)
            ndc, brand = hit if hit else ("", "")
            rows.append({"rxcui": rxcui, "drug": drug, "product_ndc": ndc, "brand_name": brand})
            print(f"  {drug:24} rxcui={rxcui:>8}  ndc={ndc or '(none)':<12} {brand}")
            time.sleep(0.2)  # be polite to openFDA (no key)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["rxcui", "drug", "product_ndc", "brand_name"])
        w.writeheader()
        w.writerows(rows)
    matched = sum(1 for r in rows if r["product_ndc"])
    print(f"\n{matched}/{len(rows)} drugs mapped → {OUT.relative_to(ROOT.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
