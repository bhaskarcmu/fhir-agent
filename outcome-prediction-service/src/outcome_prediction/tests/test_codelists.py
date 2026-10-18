"""M13: versioned diagnosis code lists, the SNOMED CT -> ICD-10-CM map, and how a code sets a flag."""
from __future__ import annotations

import json

import pytest

from outcome_prediction.etl import codelists
from outcome_prediction.etl.synthea import SYNTHEA_SHA256, SYNTHEA_VERSION
from outcome_prediction.etl.transform import to_contract
from outcome_prediction.tests.conftest import _offline


def test_one_versioned_unreviewed_list_per_flag():
    lists = codelists.flag_lists()
    assert set(lists) == set(to_contract.FLAGS)
    for flag, doc in lists.items():
        assert doc["flag"] == flag and doc["version"] >= 1 and doc["status"] == "unreviewed"   # O27
        assert doc["codes"] and all(e["prefix"] and e["description"] for e in doc["codes"])
        assert doc["meaning"]


def test_the_map_is_the_pinned_synthea_release():
    source = json.loads(codelists.MAP_FILE.read_text())["source"]
    assert (source["synthea"], source["jar_sha256"]) == (SYNTHEA_VERSION, SYNTHEA_SHA256)
    assert source["codes"] == len(codelists.snomed_map())
    assert all(t == codelists.normalise(t) for ts in codelists.snomed_map().values() for t in ts)


@pytest.mark.parametrize("code, flags", [
    ("59621000", {"hibpdx"}),       # essential hypertension -> I10 (+ neonatal P29.2, a context-only target)
    ("414545008", {"chddx"}),       # ischemic heart disease -> I25.9
    ("399211009", {"chddx", "midx"}),   # history of MI -> I25.2: old MI is both
    ("22298006", {"midx"}),         # myocardial infarction -> I21.9
    ("88805009", {"ohrtdx"}),       # chronic congestive heart failure -> I50.x / I09.81
    ("44054006", {"diabdx"}),       # type 2 diabetes -> E11.9
    ("368581000119106", {"diabdx"}),    # neuropathy due to T2D -> E11.4x + G53: most targets are diabetes
    ("203082005", {"arthdx"}),      # fibromyalgia -> M79.7: MEPS counts it as arthritis
    ("431855005", set()),           # CKD stage 1: may be due to hypertension or diabetes — not either
    ("399261000", {"chddx"}),       # history of CABG -> Z95.1 / Z95.818: half, and no other flag claims it
    ("157141000119108", {"diabdx"}),    # proteinuria due to T2D -> E11.2x / R80.x: half, unclaimed
    ("60951000119105", {"diabdx"}),     # blindness due to T2D -> E11.39 / H54.3
    ("367498001", set()),           # seasonal allergic rhinitis: not asthma, though one target is J45
    ("15777000", set()),            # prediabetes -> R73.03
    ("I10", {"hibpdx"}), ("i25.2", {"chddx", "midx"}), ("M26.643", set()),   # ICD-10-CM used as it is
    ("160903007", set()), ("", set()), (None, set()),                        # unmapped / missing
])
def test_how_a_condition_code_sets_flags(code, flags):
    assert codelists.flags_for_code(code) == flags


def test_coronary_regression_holds_for_the_code_lists():
    """Regression (prototype-baseline.md §6.3): this finding must never set coronary heart disease."""
    assert codelists.icd10_codes("274531002") == ["R931"]
    assert codelists.flags_for_code("274531002") == set()


def test_check_reports_unknown_codes_and_changed_descriptions():
    good = {codelists.normalise(e["prefix"]): e["description"]
            for doc in codelists.flag_lists().values() for e in doc["codes"]}
    assert codelists.check(good) == []
    bad = {**good, "I10": "Something else"}
    del bad["J45"]
    problems = codelists.check(bad)
    assert any("I10" in p and "Something else" in p for p in problems)
    assert any("J45" in p and "not an ICD-10-CM" in p for p in problems)


def test_lists_match_icd10cm_fy2026():
    """Against the pinned CDC release itself (fetched if missing — O44)."""
    if _offline():
        pytest.skip("offline: the CDC ICD-10-CM release can't be fetched")
    assert codelists.check() == []
