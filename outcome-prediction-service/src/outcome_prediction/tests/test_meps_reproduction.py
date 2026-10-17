"""M1 acceptance: reproduce the research prototype's MEPS dataset and HC-252 dictionary
exactly (docs/phase8/prd.md §9 criteria 1 and 3; prototype-baseline.md §3.1, §3.4).

Needs the real MEPS cache — self-skips without it. Populate it with:
    python -m outcome_prediction.meps.download
"""
from __future__ import annotations

import pytest

from outcome_prediction.meps import LONGITUDINAL_PANELS
from outcome_prediction.meps.build import LABEL, build
from outcome_prediction.meps.dictionary import storage_counts, variable_dictionary

# panel: (persons in file, adults kept, events) — prototype-baseline.md §3.1
EXPECTED = {
    21: (15_617, 11_174, 880),
    22: (14_541, 10_613, 940),
    23: (14_067, 10_447, 989),
    24: (9_797, 7_533, 592),
    25: (6_078, 4_730, 377),
    26: (6_741, 5_350, 453),
    27: (8_292, 6_513, 589),
}


@pytest.fixture(scope="module")
def built(meps_cache):
    panels = {p: meps_cache / f"h{n}.dta" for p, n in LONGITUDINAL_PANELS.items()}
    return build(panels)


def test_dataset_totals(built):
    df, _ = built
    assert df.shape == (56_360, 31)
    assert int(df[LABEL].sum()) == 4_820


@pytest.mark.parametrize("panel", sorted(EXPECTED))
def test_dataset_per_panel(built, panel):
    _, report = built
    info = report["panels"][panel]
    assert (info["persons_in_file"], info["adults_kept"], info["events"]) == EXPECTED[panel]


def test_every_dx_flag_resolves_to_exactly_one_candidate(built):
    """design.md §11 defect 6: resolution by prefix is fragile. Today it is unambiguous in
    every panel; this fails if a future file introduces a second matching column."""
    _, report = built
    ambiguous = {(p, flag): v["candidates"]
                 for p, info in report["panels"].items()
                 for flag, v in info["dx_columns"].items() if len(v["candidates"]) > 1}
    assert ambiguous == {}


def test_hc252_dictionary(meps_cache):
    d = variable_dictionary(meps_cache / "h252.dta")
    assert len(d) == 2_648
    assert storage_counts(d) == {
        "int8": 1_603, "int16": 611, "int32": 383, "float64": 25,
        "str2": 21, "str3": 2, "str9": 2, "str10": 1,
    }
