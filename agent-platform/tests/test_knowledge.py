"""
Unit tests for agent_platform.knowledge (docs/phase6/decisions.md H15):
openFDA Drug Label API + RxClass API fetchers. Mocked HTTP here; see
mcp-agent/tests/test_knowledge_integration.py for the live smoke test
against the real APIs (verified live 2026-08-02 during design -- rxcui
723, amoxicillin's actual ingredient-level RxNorm code in this repo's
FHIR data, 404s against openFDA's product-level rxcui field, which is
why label lookup is by generic name, not rxcui).

Run:
  python3 -m pytest agent-platform/tests/test_knowledge.py -v
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from agent_platform.knowledge import (
    extract_generic_name,
    fetch_drug_class,
    fetch_drug_label_citation,
)


# ── extract_generic_name ─────────────────────────────────────────────────

@pytest.mark.parametrize(
    "display,expected",
    [
        ("Amoxicillin 500 MG Oral Capsule", "Amoxicillin"),
        ("Fexofenadine hydrochloride 30 MG Oral Tablet", "Fexofenadine hydrochloride"),
        ("Ibuprofen", "Ibuprofen"),  # no dose/form suffix at all
    ],
)
def test_extract_generic_name(display, expected):
    assert extract_generic_name(display) == expected


# ── fetch_drug_label_citation ────────────────────────────────────────────

class _FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json_data


def test_fetch_drug_label_citation_parses_a_real_shaped_response(monkeypatch):
    payload = {
        "results": [{
            "boxed_warning": None,
            "contraindications": ["4 CONTRAINDICATIONS History of hypersensitivity..."],
        }]
    }
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(200, payload))

    result = fetch_drug_label_citation("Amoxicillin")
    assert result["source"] == "openFDA Drug Label API"
    assert result["boxed_warning"] is None
    assert "hypersensitivity" in result["contraindications"]


def test_fetch_drug_label_citation_returns_none_on_404(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(404, {}))
    assert fetch_drug_label_citation("NotARealDrug") is None


def test_fetch_drug_label_citation_returns_none_when_no_warning_data(monkeypatch):
    """A real label exists but has neither field populated -- nothing worth citing."""
    payload = {"results": [{"boxed_warning": None, "contraindications": None}]}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(200, payload))
    assert fetch_drug_label_citation("SomeDrug") is None


def test_fetch_drug_label_citation_returns_none_on_network_failure(monkeypatch):
    def _raise(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", _raise)
    assert fetch_drug_label_citation("Amoxicillin") is None


# ── fetch_drug_class ──────────────────────────────────────────────────────

def test_fetch_drug_class_parses_and_deduplicates_a_real_shaped_response(monkeypatch):
    payload = {
        "rxclassDrugInfoList": {
            "rxclassDrugInfo": [
                {"rxclassMinConceptItem": {"className": "PENICILLINS", "classType": "VA"}},
                {"rxclassMinConceptItem": {"className": "PENICILLINS", "classType": "VA"}},  # dup
                {"rxclassMinConceptItem": {"className": "Penicillins, extended spectrum", "classType": "ATC1-4"}},
            ]
        }
    }
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(200, payload))

    result = fetch_drug_class("723")
    assert len(result) == 2
    assert result[0] == {"class_name": "PENICILLINS", "class_type": "VA"}


def test_fetch_drug_class_caps_at_max_classes(monkeypatch):
    payload = {
        "rxclassDrugInfoList": {
            "rxclassDrugInfo": [
                {"rxclassMinConceptItem": {"className": f"Class {i}", "classType": "VA"}}
                for i in range(20)
            ]
        }
    }
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(200, payload))
    assert len(fetch_drug_class("723")) == 5


def test_fetch_drug_class_returns_empty_list_on_failure(monkeypatch):
    def _raise(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", _raise)
    assert fetch_drug_class("723") == []


def test_fetch_drug_class_returns_empty_list_when_nothing_found(monkeypatch):
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: _FakeResponse(200, {"rxclassDrugInfoList": {}})
    )
    assert fetch_drug_class("000") == []
