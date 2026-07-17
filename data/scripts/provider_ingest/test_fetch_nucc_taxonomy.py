"""
Unit tests for fetch_nucc_taxonomy.py — parsing logic only, HTTP mocked.

No network required. Run:
  python3 -m pytest data/scripts/provider_ingest/test_fetch_nucc_taxonomy.py -v
"""

from __future__ import annotations

import csv
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

_MODULE_PATH = Path(__file__).parent / "fetch_nucc_taxonomy.py"
_spec = importlib.util.spec_from_file_location("fetch_nucc_taxonomy", _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

FAKE_CSV = (
    "Code,Grouping,Classification,Specialization,Definition,Notes,Display Name,Section\r\n"
    '207RE0101X,Allopathic & Osteopathic Physicians,Internal Medicine,'
    '"Endocrinology, Diabetes & Metabolism",A specialist,,Endocrinology Physician,Individual\r\n'
    "193200000X,Group,Multi-Specialty,,A business group,,Multi-Specialty Group,Individual\r\n"
).encode("utf-8-sig")


class TestFetchNuccTaxonomy(unittest.TestCase):
    def test_parses_real_csv_shape_into_expected_rows(self):
        with patch.object(_mod, "_get", return_value=FAKE_CSV):
            with patch.object(_mod, "OUT_FILE", Path("/tmp/test_taxonomy_reference.csv")), \
                 patch.object(_mod, "OUT_DIR", Path("/tmp")):
                count = _mod.fetch_nucc_taxonomy()

        self.assertEqual(count, 2)
        with open("/tmp/test_taxonomy_reference.csv", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(rows[0]["code"], "207RE0101X")
        self.assertEqual(rows[0]["specialization"], "Endocrinology, Diabetes & Metabolism")
        self.assertEqual(rows[0]["nucc_version"], _mod.NUCC_VERSION)
        self.assertEqual(rows[1]["specialization"], "")  # blank Specialization -> ""


if __name__ == "__main__":
    unittest.main()
