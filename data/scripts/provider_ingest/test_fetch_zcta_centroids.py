"""
Unit tests for fetch_zcta_centroids.py — the Gazetteer/county-relationship join
logic, including the split-ZCTA majority-area rule. HTTP mocked, no network.

Run:
  python3 -m pytest data/scripts/provider_ingest/test_fetch_zcta_centroids.py -v
"""

from __future__ import annotations

import csv
import importlib.util
import io
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

_MODULE_PATH = Path(__file__).parent / "fetch_zcta_centroids.py"
_spec = importlib.util.spec_from_file_location("fetch_zcta_centroids", _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def _fake_gazetteer_zip() -> bytes:
    text = (
        "GEOID\tALAND\tAWATER\tALAND_SQMI\tAWATER_SQMI\tINTPTLAT\tINTPTLONG\n"
        "27514\t1\t1\t1\t1\t35.9132\t-79.0558\n"
        "29999\t1\t1\t1\t1\t35.0000\t-80.0000\n"  # split ZCTA, no matching state expected below unless majority
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("2024_Gaz_zcta_national.txt", text)
    return buf.getvalue()


def _fake_county_rel() -> bytes:
    # 27514 -> single county, NC (state FIPS 37).
    # 29999 -> split across two counties: a small sliver in SC (45) and a larger
    # majority area in NC (37) -- majority-area rule must pick NC.
    header = "GEOID_ZCTA5_20|GEOID_COUNTY_20|AREALAND_PART\n"
    rows = [
        "27514|37135|1000000\n",
        "29999|45091|100\n",       # SC, tiny sliver
        "29999|37119|900000\n",   # NC, majority
    ]
    return (header + "".join(rows)).encode("utf-8-sig")


class TestFetchZctaCentroids(unittest.TestCase):
    def test_join_assigns_majority_area_state_for_split_zcta(self):
        with patch.object(_mod, "_get", side_effect=[_fake_gazetteer_zip(), _fake_county_rel()]), \
             patch.object(_mod, "OUT_FILE", Path("/tmp/test_zip_centroids.csv")), \
             patch.object(_mod, "OUT_DIR", Path("/tmp")):
            count = _mod.fetch_zcta_centroids(["NC"])

        with open("/tmp/test_zip_centroids.csv", newline="") as f:
            rows = {r["zip5"]: r for r in csv.DictReader(f)}

        self.assertEqual(count, 2)
        self.assertEqual(rows["27514"]["state"], "NC")
        self.assertAlmostEqual(float(rows["27514"]["lat"]), 35.9132)
        # The split ZCTA must be assigned to NC (majority area 900000 > 100 in SC),
        # not silently dropped or assigned to the minority state.
        self.assertEqual(rows["29999"]["state"], "NC")

    def test_filters_to_requested_states_only(self):
        with patch.object(_mod, "_get", side_effect=[_fake_gazetteer_zip(), _fake_county_rel()]), \
             patch.object(_mod, "OUT_FILE", Path("/tmp/test_zip_centroids_sc.csv")), \
             patch.object(_mod, "OUT_DIR", Path("/tmp")):
            count = _mod.fetch_zcta_centroids(["SC"])
        # Neither ZCTA has SC as its majority state -- SC-only filter yields nothing.
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
