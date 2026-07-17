#!/usr/bin/env python3
"""
Fetch REAL ZCTA centroids + state assignment for the curated ingestion states
(no login). Two Census Bureau sources, joined:

  1. 2024 Gazetteer ZCTA file — centroid lat/lon per ZCTA5 (INTPTLAT/INTPTLONG).
     Verified live, M3 (design.md §7):
     https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_zcta_national.zip
  2. 2020 ZCTA-to-county relationship file — the Gazetteer file has NO state
     column (checked, not assumed); this file provides GEOID_COUNTY_20, whose
     first 2 digits are the state FIPS code:
     https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_county20_natl.txt

A ZCTA can span multiple counties/states (split ZCTAs near a border) — this script
assigns each ZCTA to whichever county/state has the largest AREALAND_PART, i.e. its
majority state. Acceptable imprecision for a proximity *stub* (design.md §4.2); not
used for anything requiring exact jurisdiction.

Writes a curated derivative filtered to the requested states (small — a few
thousand rows for 3 states, vs. 33,791 nationally) to
data/reference/providers/zip_centroids.csv. Raw downloads are NOT committed
(fetched to a temp dir and discarded).

Usage:  python3 data/scripts/provider_ingest/fetch_zcta_centroids.py [--states NC,CA,MT]
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

GAZETTEER_ZIP_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_zcta_national.zip"
)
ZCTA_COUNTY_REL_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_county20_natl.txt"
)
OUT_DIR = Path(__file__).resolve().parents[2] / "reference" / "providers"
OUT_FILE = OUT_DIR / "zip_centroids.csv"
TIMEOUT = 120

DEFAULT_STATES = ["NC", "CA", "MT"]

# Standard, static FIPS state-code table (Census Bureau invariant reference data,
# not fetched — this doesn't change and doesn't need "verification" the way a
# dataset URL does).
FIPS_TO_STATE = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT",
    "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL",
    "18": "IN", "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME", "24": "MD",
    "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT", "31": "NE",
    "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA", "54": "WV",
    "55": "WI", "56": "WY", "72": "PR",
}


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "fhir-agent-phase3/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def _fetch_centroids() -> dict[str, tuple[float, float]]:
    """zip5 -> (lat, lon)"""
    raw_zip = _get(GAZETTEER_ZIP_URL)
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
        inner_name = next(n for n in zf.namelist() if n.endswith(".txt"))
        text = zf.read(inner_name).decode("latin-1")

    centroids: dict[str, tuple[float, float]] = {}
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    for row in reader:
        row = {k.strip(): v.strip() for k, v in row.items()}
        centroids[row["GEOID"]] = (float(row["INTPTLAT"]), float(row["INTPTLONG"]))
    return centroids


def _fetch_zcta_states() -> dict[str, str]:
    """zip5 -> majority-area state abbreviation."""
    raw = _get(ZCTA_COUNTY_REL_URL).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw), delimiter="|")

    best_area: dict[str, int] = {}
    best_state: dict[str, str] = {}
    for row in reader:
        zip5 = row["GEOID_ZCTA5_20"].strip()
        county_fips = row["GEOID_COUNTY_20"].strip()
        if not zip5 or not county_fips:
            continue
        state = FIPS_TO_STATE.get(county_fips[:2])
        if state is None:
            continue
        area = int(row["AREALAND_PART"] or 0)
        if area > best_area.get(zip5, -1):
            best_area[zip5] = area
            best_state[zip5] = state
    return best_state


def fetch_zcta_centroids(states: list[str]) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    states_set = {s.upper() for s in states}

    print("fetching Gazetteer centroids...")
    centroids = _fetch_centroids()
    print(f"  {len(centroids)} ZCTAs nationally")

    print("fetching ZCTA-to-state relationship...")
    zcta_states = _fetch_zcta_states()
    print(f"  {len(zcta_states)} ZCTAs with a resolved state")

    rows = []
    for zip5, state in sorted(zcta_states.items()):
        if state not in states_set:
            continue
        centroid = centroids.get(zip5)
        if centroid is None:
            continue
        lat, lon = centroid
        rows.append({"zip5": zip5, "lat": lat, "lon": lon, "state": state})

    with OUT_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["zip5", "lat", "lon", "state"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {len(rows)} ZIP centroids for {sorted(states_set)} -> {OUT_FILE}")
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--states", default=",".join(DEFAULT_STATES),
                         help="Comma-separated 2-letter state codes (default: NC,CA,MT)")
    args = parser.parse_args()
    states = [s.strip() for s in args.states.split(",") if s.strip()]
    return 0 if fetch_zcta_centroids(states) > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
