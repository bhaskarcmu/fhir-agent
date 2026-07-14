#!/usr/bin/env python3
"""
Fetch a SMALL, real sample of ACA commercial formulary data (no login).

ACA marketplace (Qualified Health Plan) issuers must publish machine-readable
formulary files. The chain is 3 hops:

  1. CMS Machine-Readable URL PUF  → each issuer's index.json URL  (download.cms.gov)
  2. issuer index.json             → formulary_urls[]            (issuer host)
  3. drugs.json (formulary)        → per-drug tier / PA / step-therapy / quantity-limit,
                                     keyed by rxnorm_id + HIOS plan_id

This mirrors CMS Part D for Medicare, but for COMMERCIAL plans — the adjudication
metadata our rules engine consumes. Proprietary PA *criteria* and pricing are NOT
here (those stay with the payer); this is the public disclosure layer.

Writes a tiny curated sample under data/reference/aca-commercial/. Raw multi-MB
formulary files are range-/temp-sampled and deleted, never committed.

Usage:  python3 data/scripts/fetch_aca_formulary_sample.py
Docs:   https://github.com/CMSgov/QHP-provider-formulary-APIs
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "reference" / "aca-commercial"

# A known, currently-published issuer formulary index (Premera AK, via FormularyNavigator).
# Swap for any issuer's "URL Submitted" from the Machine-Readable URL PUF:
#   https://download.cms.gov/marketplace-puf/2026/machine-readable-url-puf.zip
ISSUER_INDEX = "https://fm.formularynavigator.com/jsonFiles/publish/11/47/cms-data-index.json"
SAMPLE_RECORDS = 3
TIMEOUT = 90


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "phase2-dataeng/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    # Hop 2: issuer index.json
    index = json.loads(_get(ISSUER_INDEX))
    (OUT / "issuer_index.json").write_text(json.dumps(index, indent=2))
    formulary_url = index["formulary_urls"][0]
    print(f"issuer index → formulary: {formulary_url}")

    # Hop 3: drugs.json — pull, extract first N complete records, keep only the sample.
    drugs = json.loads(_get(formulary_url))
    print(f"formulary has {len(drugs)} drug records; saving first {SAMPLE_RECORDS}")
    sample = drugs[:SAMPLE_RECORDS]
    (OUT / "example_qhp_formulary_records.json").write_text(json.dumps(sample, indent=2))

    tiers = sorted({p["drug_tier"] for d in drugs for p in d["plans"]})
    print("distinct drug_tier values:", ", ".join(tiers))
    print(f"wrote sample → {OUT/'example_qhp_formulary_records.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
