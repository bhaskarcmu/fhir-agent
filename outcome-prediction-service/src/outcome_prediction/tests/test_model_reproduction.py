"""M2 acceptance: reproduce the research prototype's model on real MEPS data
(docs/phase8/prd.md §9 criterion 2; prototype-baseline.md §5.2).

The PRD's acceptance criterion is the tolerance band. With scikit-learn pinned to the
prototype's version, M2 reproduced every printed digit — the tighter checks below record that,
so a change in any dependency that moves the numbers is noticed, not absorbed.

Needs the real MEPS cache — self-skips without it.
"""
from __future__ import annotations

import pytest

from outcome_prediction.meps import LONGITUDINAL_PANELS
from outcome_prediction.meps.build import build
from outcome_prediction.model.evaluate import evaluate


@pytest.fixture(scope="module")
def metrics(meps_cache, tmp_path_factory):
    import pandas as pd
    table, _ = build({p: meps_cache / f"h{n}.dta" for p, n in LONGITUDINAL_PANELS.items()})
    # Round-trip through CSV, exactly as the pipeline does (build writes it, train reads it).
    csv = tmp_path_factory.mktemp("m2") / "meps_hosp12.csv"
    table.to_csv(csv, index=False)
    return evaluate(pd.read_csv(csv))


def test_split(metrics):
    s = metrics["split"]
    assert (s["n_train"], s["n_test"], s["events_test"]) == (44_497, 11_863, 1_042)


def test_acceptance_tolerances(metrics):
    assert 0.760 <= metrics["gbm"]["auroc"] <= 0.778
    assert 0.700 <= metrics["comparison"]["auroc"] <= 0.716


def test_matches_the_prototype_to_reported_precision(metrics):
    g, c = metrics["gbm"], metrics["comparison"]
    assert round(g["auroc"], 3) == 0.769 and [round(v, 3) for v in g["auroc_ci95"]] == [0.754, 0.786]
    assert round(g["auprc"], 3) == 0.265 and round(g["brier"], 4) == 0.0725
    assert round(c["auroc"], 3) == 0.708 and [round(v, 3) for v in c["auroc_ci95"]] == [0.691, 0.725]
    assert round(c["auprc"], 3) == 0.225 and round(c["brier"], 4) == 0.0751
    assert round(g["auroc_survey_weighted"], 3) == 0.780
    assert round(g["top_k"]["10%"]["ppv"], 3) == 0.293 and round(g["top_k"]["10%"]["sensitivity"], 3) == 0.333
    assert round(metrics["brier_null"], 4) == 0.0801


def test_calibration_and_subgroups(metrics):
    deciles = [(round(d["predicted"], 3), round(d["actual"], 3)) for d in metrics["calibration_deciles"]]
    assert deciles[0] == (0.016, 0.008) and deciles[-1] == (0.304, 0.292)
    by_group = {g["group"]: round(g["auroc"], 3) for g in metrics["subgroups"]}
    assert by_group == {"age 18-44": 0.761, "age 45-64": 0.739, "age 65+": 0.695, "male": 0.794,
                        "female": 0.743, "no prior stay": 0.744, "prior stay": 0.694}


def test_importance_and_comparison_coefficients(metrics):
    top3 = list(metrics["permutation_importance"])[:3]
    assert top3 == ["agey1x", "sex", "rxtoty1"]
    cc = metrics["comparison_coefficients"]
    assert (round(cc["intercept"], 3), round(cc["age_per_year"], 4), round(cc["prior_stay"], 4)) == (
        -4.047, 0.0280, 1.3055)
