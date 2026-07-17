#!/usr/bin/env python3
"""
Fetch the REAL NUCC Health Care Provider Taxonomy code set (no login).

Source: nucc.org's published CSV (verified live, M3 — design.md §7). The license
click-through on nucc.org is for vendors embedding the code set in commercial
products; a straight CSV download for this kind of read/redistribution use needs
no auth and returns 200 with no User-Agent spoofing required (unlike the CMS
www.cms.gov gotcha noted in data/reference/README.md — this host has no such block).

Writes the full curated set (883 codes, ~530KB — already small; no sub-sampling
needed the way the larger CMS/ACA sources require) to
data/reference/providers/taxonomy_reference.csv. That file is committed (not
gitignored) — small, public-domain, curated derivative, same policy as
data/reference/icd10/ and data/reference/rxnorm/.

Usage:  python3 data/scripts/provider_ingest/fetch_nucc_taxonomy.py
"""

from __future__ import annotations

import csv
import io
import sys
import urllib.request
from pathlib import Path

NUCC_VERSION = "26.0"
SOURCE_URL = "https://www.nucc.org/images/stories/CSV/nucc_taxonomy_260.csv"
OUT_DIR = Path(__file__).resolve().parents[2] / "reference" / "providers"
OUT_FILE = OUT_DIR / "taxonomy_reference.csv"
TIMEOUT = 30

FIELDNAMES = ["code", "grouping", "classification", "specialization", "definition", "nucc_version"]


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "fhir-agent-phase3/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def fetch_nucc_taxonomy() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw = _get(SOURCE_URL).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))

    rows = []
    for row in reader:
        rows.append({
            "code": row["Code"],
            "grouping": row["Grouping"],
            "classification": row["Classification"],
            "specialization": row["Specialization"] or "",
            "definition": row["Definition"] or "",
            "nucc_version": NUCC_VERSION,
        })

    with OUT_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {len(rows)} taxonomy codes (v{NUCC_VERSION}) -> {OUT_FILE}")
    return len(rows)


if __name__ == "__main__":
    sys.exit(0 if fetch_nucc_taxonomy() > 0 else 1)
