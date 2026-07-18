"""
Unit tests for fetch_nppes.py — record parsing, pagination, dedup, and the
wrong-state-address filter found live in M3. HTTP mocked, no network.

Run:
  python3 -m pytest data/scripts/provider_ingest/test_fetch_nppes.py -v
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

_MODULE_PATH = Path(__file__).parent / "fetch_nppes.py"
_spec = importlib.util.spec_from_file_location("fetch_nppes", _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def _individual(npi: str, state: str, purpose: str = "LOCATION") -> dict:
    return {
        "number": npi,
        "enumeration_type": "NPI-1",
        "basic": {"first_name": "Jane", "last_name": "Doe", "status": "A"},
        "addresses": [{
            "address_purpose": purpose, "address_1": "1 Main St",
            "city": "Townsville", "state": state, "postal_code": "275149999",
        }],
        "taxonomies": [{"code": "207RE0101X", "primary": True}],
    }


def _organization(npi: str, state: str) -> dict:
    return {
        "number": npi,
        "enumeration_type": "NPI-2",
        "basic": {"organization_name": "Acme Health System", "status": "A"},
        "addresses": [{
            "address_purpose": "LOCATION", "address_1": "2 Hospital Way",
            "city": "Townsville", "state": state, "postal_code": "276019999",
        }],
        "taxonomies": [{"code": "282N00000X", "primary": True}],
    }


class TestParseRecord(unittest.TestCase):
    def test_individual_record_shape(self):
        record = _mod._parse_record(_individual("1111111111", "NC"))
        self.assertEqual(record["npi"], "1111111111")
        self.assertEqual(record["entity_type"], 1)
        self.assertEqual(record["name"], "Jane Doe")
        self.assertEqual(record["npi_status"], "active")
        self.assertEqual(record["addresses"][0]["zip5"], "27514")  # first 5 of postal_code

    def test_organization_record_uses_organization_name(self):
        record = _mod._parse_record(_organization("2222222222", "NC"))
        self.assertEqual(record["entity_type"], 2)
        self.assertEqual(record["name"], "Acme Health System")

    def test_status_other_than_a_maps_to_deactivated(self):
        raw = _individual("3333333333", "NC")
        raw["basic"]["status"] = "X"  # never actually observed live, but must still be
        record = _mod._parse_record(raw)  # a value the schema's CHECK constraint accepts
        self.assertEqual(record["npi_status"], "deactivated")

    def test_falls_back_to_any_address_when_no_location_purpose(self):
        raw = _individual("4444444444", "NC", purpose="MAILING")
        record = _mod._parse_record(raw)
        self.assertEqual(len(record["addresses"]), 1)  # still captured, just not LOCATION-filtered


class TestFetchState(unittest.TestCase):
    def test_dedupes_across_taxonomy_terms_by_npi(self):
        # Same NPI appears under two different taxonomy_description queries.
        page1 = {"results": [_individual("1111111111", "NC")]}
        page2 = {"results": [_individual("1111111111", "NC")]}
        with patch.object(_mod, "_get_json", side_effect=[page1, {"results": []}, page2, {"results": []}]), \
             patch.object(_mod, "time"):
            records = _mod.fetch_state("NC", terms=["Family Medicine", "Internal Medicine"], max_pages=2)
        self.assertEqual(len(records), 1)

    def test_drops_records_whose_location_address_is_a_different_state(self):
        # Found live in M3: state=NC can match a provider whose LOCATION address
        # is actually in another state (matched on a different address type).
        page = {"results": [_individual("1111111111", "NC"), _individual("2222222222", "SC")]}
        with patch.object(_mod, "_get_json", side_effect=[page, {"results": []}]), \
             patch.object(_mod, "time"):
            records = _mod.fetch_state("NC", terms=["Family Medicine"], max_pages=2)
        npis = {r["npi"] for r in records}
        self.assertEqual(npis, {"1111111111"})

    def test_stops_paginating_a_term_when_page_is_short(self):
        page = {"results": [_individual("1111111111", "NC")]}  # 1 result, < PAGE_SIZE
        with patch.object(_mod, "_get_json", side_effect=[page]) as mock_get, \
             patch.object(_mod, "time"):
            _mod.fetch_state("NC", terms=["Family Medicine"], max_pages=5)
        self.assertEqual(mock_get.call_count, 1)  # didn't fetch a 2nd page needlessly


if __name__ == "__main__":
    unittest.main()
