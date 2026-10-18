"""The portable feature contract meps-portable-v2 (decisions.md O52–O54)."""
from __future__ import annotations

import pytest

from outcome_prediction import contract
from outcome_prediction.model import FEATURES as MEPS25_FEATURES


def test_spending_is_never_a_production_input():
    assert "totexpy1" not in contract.names(contract.DEFAULT_TIERS)
    assert "totexpy1" not in contract.names(contract.WITH_CLAIMS_TIERS)
    assert next(f for f in contract.FEATURES if f.name == "totexpy1").tier == "not_portable"


def test_claims_only_inputs_are_only_in_the_claims_tier():
    records_only = set(contract.names(contract.DEFAULT_TIERS))
    with_claims = set(contract.names(contract.WITH_CLAIMS_TIERS))
    assert {"rxtoty1", "hhtotdy1"} <= with_claims - records_only


def test_income_is_optional_and_every_feature_names_its_fhir_source():
    assert contract.OPTIONAL == ("povcaty1",)
    assert all(f.fhir_source for f in contract.FEATURES)
    assert len({f.name for f in contract.FEATURES}) == len(contract.FEATURES)


def test_every_meps25_feature_has_a_documented_portability_tier():
    assert set(MEPS25_FEATURES) <= {f.name for f in contract.FEATURES}


@pytest.mark.parametrize("code, chapter", [
    ("A08", 1), ("B99", 1), ("C50", 2), ("D49", 2), ("D50", 3), ("E11", 4), ("F32", 5), ("G30", 6),
    ("H52", 7), ("H60", 8), ("I50", 9), ("J44", 10), ("K21", 11), ("L40", 12), ("M17", 13),
    ("N18", 14), ("O26", 15), ("P07", 16), ("Q21", 17), ("R69", 18), ("S72", 19), ("T88", 19),
    ("U07", 22), ("V01", 20), ("Y99", 20), ("Z34", 21),
])
def test_icd10_chapter_boundaries(code, chapter):
    assert contract.icd10_chapter(code) == chapter


def test_high_cost_needs_claims_to_be_validated():
    assert contract.LABEL_OBSERVABILITY["high_cost_y2"].startswith("claims only")
    assert "records" in contract.LABEL_OBSERVABILITY["admit_nonobstetric_y2"]
