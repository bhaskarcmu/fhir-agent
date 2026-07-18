#!/usr/bin/env python3
"""
Fetch REAL NPPES NPI Registry data for a curated state (no login).

Source: npiregistry.cms.hhs.gov/api/?version=2.1 — verified live, M3 (design.md §7);
Phase 2 had already confirmed the host is reachable (data/reference/README.md), this
milestone confirmed the actual response shape and two gotchas:

  1. A bare `state` filter is rejected: {"Errors":[{"description":"Field state
     requires additional search criteria", ...}]}. Worked around by pairing `state`
     with each of a curated TAXONOMY_TERMS list, deduping results by NPI across
     terms — so widening taxonomy coverage later is growing that list, not a
     schema change (design.md §6).
  2. `basic.status` was `"A"` on every one of hundreds of sampled records —
     never anything else in this build's samples. Deactivated NPIs don't appear
     to surface via this endpoint in practice. Any non-"A" value maps to
     `"deactivated"` — NPPES's own status field is binary (active vs. not), and
     the registry schema's `npi_status` CHECK constraint only ever permits
     `'active'`/`'deactivated'` (schema.sql). An earlier version of this script
     mapped non-"A" to an invented third value, "unknown" — which matched no
     real live data yet but would have violated that CHECK constraint the first
     time NPPES ever did return a non-"A" record, silently failing an entire
     ingestion run instead of just recording a deactivated provider.
  3. `state=NC` matches ANY of a provider's addresses, not specifically the
     practice (LOCATION) one — a provider whose mailing address is NC but whose
     actual practice is in another state still matched, ~13% of raw results in
     the first real pull. Filtered out post-hoc (fetch_state()) by requiring the
     LOCATION address itself be in the queried state — referring a patient to an
     out-of-state practice would be a real bug, not a stub-quality shortcut.

Bounded, not exhaustive: MAX_PAGES_PER_TERM caps this at a verification-scale pull,
not a full-state census — mirrors Phase 2's "range-/temp-sample, don't ingest whole"
precedent for large real sources (data/reference/README.md's ACA formulary note). A
true full-state pull is a longer-running operation left for a separate run.

Writes a curated real sample (not synthetic) to
data/reference/providers/nppes_<state>.json — committed, small enough.

Usage:  python3 data/scripts/provider_ingest/fetch_nppes.py --state NC
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_BASE = "https://npiregistry.cms.hhs.gov/api/"
OUT_DIR = Path(__file__).resolve().parents[2] / "reference" / "providers"
TIMEOUT = 30
PAGE_SIZE = 200
MAX_PAGES_PER_TERM = 3        # bound — see module docstring
REQUEST_DELAY_SECONDS = 0.2   # polite pacing; the API's rate limit is undocumented

# Curated taxonomy terms spanning multiple NUCC groupings/classifications, so the
# pilot pull exercises real taxonomy diversity — design.md's stated rationale for
# curating by geography over specialty (PRD §9). Includes one organization-type
# term (General Acute Care Hospital) so entity_type=2 records are represented too.
TAXONOMY_TERMS = [
    "Family Medicine",
    "Internal Medicine",
    "Pediatrics",
    "Cardiovascular Disease",
    "Dermatology",
    "Endocrinology, Diabetes & Metabolism",
    "Obstetrics & Gynecology",
    "Psychiatry",
    "Orthopaedic Surgery",
    "General Acute Care Hospital",
]


def _get_json(params: dict) -> dict:
    url = f"{API_BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "fhir-agent-phase3/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def _parse_record(raw: dict) -> dict:
    basic = raw["basic"]
    entity_type = 1 if raw["enumeration_type"] == "NPI-1" else 2
    name = (
        basic.get("organization_name")
        if entity_type == 2
        else f"{basic.get('first_name', '')} {basic.get('last_name', '')}".strip()
    )
    addresses = [a for a in raw.get("addresses", []) if a.get("address_purpose") == "LOCATION"]
    if not addresses:
        addresses = raw.get("addresses", [])
    return {
        "npi": raw["number"],
        "entity_type": entity_type,
        "name": name,
        "npi_status": "active" if basic.get("status") == "A" else "deactivated",
        "addresses": [
            {
                "address_1": a.get("address_1", ""),
                "address_2": a.get("address_2"),
                "city": a.get("city", ""),
                "state": a.get("state", ""),
                "zip5": (a.get("postal_code") or "")[:5],
            }
            for a in addresses
        ],
        "taxonomies": [
            {"code": t["code"], "is_primary": bool(t.get("primary"))}
            for t in raw.get("taxonomies", [])
            if t.get("code")
        ],
    }


def fetch_state(state: str, terms: list[str] = TAXONOMY_TERMS,
                 max_pages: int = MAX_PAGES_PER_TERM) -> list[dict]:
    by_npi: dict[str, dict] = {}
    for term in terms:
        for page in range(max_pages):
            skip = page * PAGE_SIZE
            try:
                data = _get_json({
                    "version": "2.1", "state": state, "taxonomy_description": term,
                    "limit": PAGE_SIZE, "skip": skip,
                })
            except urllib.error.URLError as exc:
                print(f"  {state}/{term!r} page {page}: {exc} — stopping this term")
                break
            results = data.get("results", [])
            if not results:
                break
            skipped_wrong_state = 0
            for raw in results:
                record = _parse_record(raw)
                # `state=NC` matches ANY of the provider's addresses (found live, M3 —
                # not documented anywhere): a provider whose *mailing* address is NC
                # but whose *practice* (LOCATION) address is elsewhere still matches.
                # For a provider-search registry, practice location is what matters —
                # referring an NC patient to a Charleston, SC practice would be a real
                # bug, not a stub-quality shortcut. Drop records whose LOCATION address
                # isn't actually in the queried state.
                if record["addresses"] and record["addresses"][0]["state"] != state:
                    skipped_wrong_state += 1
                    continue
                by_npi[record["npi"]] = record
            print(f"  {state}/{term!r} page {page}: +{len(results)} "
                  f"(unique so far: {len(by_npi)}, {skipped_wrong_state} wrong-state dropped)")
            if len(results) < PAGE_SIZE:
                break
            time.sleep(REQUEST_DELAY_SECONDS)
    return list(by_npi.values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, help="2-letter state code, e.g. NC")
    parser.add_argument("--max-pages-per-term", type=int, default=MAX_PAGES_PER_TERM)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"fetching NPPES records for {args.state} across {len(TAXONOMY_TERMS)} taxonomy terms "
          f"(bounded: {args.max_pages_per_term} pages/term x {PAGE_SIZE}/page)...")
    records = fetch_state(args.state, max_pages=args.max_pages_per_term)

    out_file = OUT_DIR / f"nppes_{args.state.lower()}.json"
    out_file.write_text(json.dumps(records, indent=2))
    print(f"wrote {len(records)} unique providers -> {out_file}")
    return 0 if records else 1


if __name__ == "__main__":
    sys.exit(main())
