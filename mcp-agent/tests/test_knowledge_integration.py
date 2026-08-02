"""
Live smoke test against the real openFDA Drug Label API and RxClass API
(docs/phase6/decisions.md H15) -- these are third-party public services
this repo doesn't operate, unlike Ollama (H50), so a genuine connectivity
failure here self-skips rather than hard-fails; a real response shape
mismatch (a KeyError/parsing bug) does not self-skip and fails the test
normally.

Confirms live 2026-08-02 during M6 design: amoxicillin's real RXCUI in
this repo's FHIR data (723, ingredient-level) 404s against openFDA's
product-level rxcui field but works fine for RxClass -- this test
exercises exactly that split.

Run:
  python3 -m pytest mcp-agent/tests/test_knowledge_integration.py -v
"""

from __future__ import annotations

import httpx
import pytest

from agent_platform.knowledge import fetch_drug_class, fetch_drug_label_citation


def _internet_reachable() -> bool:
    try:
        httpx.get("https://api.fda.gov/drug/label.json", params={"limit": 1}, timeout=5.0)
        return True
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(
    not _internet_reachable(),
    reason="No network access to api.fda.gov -- skipping live openFDA/RxClass smoke test.",
)


def test_live_openfda_label_lookup_for_a_real_drug():
    result = fetch_drug_label_citation("Amoxicillin")
    assert result is not None
    assert result["source"] == "openFDA Drug Label API"
    assert result["boxed_warning"] or result["contraindications"]


def test_live_openfda_lookup_for_a_nonexistent_drug_returns_none():
    result = fetch_drug_label_citation("Definitelynotarealdrugxyz123")
    assert result is None


def test_live_rxclass_lookup_for_amoxicillins_real_ingredient_rxcui():
    """RXCUI 723 -- this repo's own Synthea demo data uses this exact code for amoxicillin."""
    classes = fetch_drug_class("723")
    assert classes
    assert any("PENICILLIN" in c["class_name"].upper() for c in classes)
