"""Fast unit tests for the lab — synthetic data only."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from outcome_prediction_lab import holdout, knowledge
from outcome_prediction_lab.data import add_targets, normalize_ids
from outcome_prediction_lab.evaluate import paired_bootstrap_delta, top_k
from outcome_prediction_lab.explain import describe, narrative
from outcome_prediction_lab.features import AutoencoderEmbedding, honest_frame


# ── holdout ledger (O32) ─────────────────────────────────────────────────────────────

def test_test_panel_scoring_requires_a_prior_ledger_entry(tmp_path):
    ledger = tmp_path / "ledger.md"
    with pytest.raises(holdout.NotInLedger):
        holdout.require("r1", "cand", ledger=ledger)
    holdout.record("r1", "cand", "finalist", ledger=ledger)
    holdout.require("r1", "cand", ledger=ledger)                  # now allowed
    with pytest.raises(holdout.NotInLedger):
        holdout.require("r1", "other-cand", ledger=ledger)
    assert ledger.read_text().count("| r1 | cand |") == 1


def test_ledger_rejects_pipe_characters(tmp_path):
    with pytest.raises(ValueError):
        holdout.record("r1", "a|b", "x", ledger=tmp_path / "l.md")


# ── data ─────────────────────────────────────────────────────────────────────────────

def test_person_ids_normalise_to_ten_digits_with_panel_prefix():
    ids = pd.Series(["90001101", "2290001101", "10001101"])
    panels = pd.Series([22, 22, 21])
    assert normalize_ids(ids, panels).tolist() == ["2290001101", "2290001101", "2110001101"]


def test_high_cost_is_ranked_within_each_panel():
    t = pd.DataFrame({"panel": [1] * 10 + [2] * 10, "totexpy2": list(range(10)) + [x * 1000 for x in range(10)],
                      "ertoty2": 0, "died": 0, "inscovy1": 1, "inscovy2": 1})
    out = add_targets(t)
    assert out.groupby("panel").high_cost_y2.sum().tolist() == [1, 1]   # top decile in EACH panel


def test_lost_insurance_only_defined_for_the_insured():
    t = pd.DataFrame({"panel": 1, "totexpy2": 0, "ertoty2": 0, "died": 0,
                      "inscovy1": [1, 2, 3], "inscovy2": [3, 2, 3]})
    assert add_targets(t).lost_insurance_y2.tolist()[:2] == [1.0, 0.0]
    assert np.isnan(add_targets(t).lost_insurance_y2.iloc[2])


# ── knowledge features ───────────────────────────────────────────────────────────────

def test_frailty_score_uses_published_points():
    assert knowledge.HFRS_POINTS["F00"] == 7.1 and len(knowledge.HFRS_POINTS) == 109
    assert knowledge.scores({"F00", "G81"})["hfrs"] == pytest.approx(11.5)
    assert knowledge.scores(set())["charlson_approx"] == 0.0


# ── honest missing-value encoding (concept 4) ────────────────────────────────────────

def test_refused_and_dont_know_become_missing_not_no():
    raw = {f"{d}_raw": [1, 2, -8] for d in
           ["hibpdx", "chddx", "angidx", "midx", "ohrtdx", "strkdx", "emphdx", "diabdx", "arthdx", "asthdx", "choldx"]}
    t = pd.DataFrame({"povcaty1": [3, -1, 2], "totexpy1": [10, 20, -1], "mcrevy1": [1, 2, -7],
                      "mcdevy1": [2, 2, 2], "adlhlp1": [1, 2, -1], "iadlhp1": [2, 2, 2], "actlim1": [2, 1, 2],
                      **raw})
    h = honest_frame(t)
    assert h.hibpdx.tolist()[:2] == [1.0, 0.0] and np.isnan(h.hibpdx.iloc[2])
    assert np.isnan(h.povcaty1.iloc[1]) and np.isnan(h.totexpy1.iloc[2])
    assert h.mcrevy1.tolist()[:2] == [1.0, 0.0] and np.isnan(h.mcrevy1.iloc[2])


# ── autoencoder (concept 2) ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("denoise", [0.0, 0.2])
def test_autoencoder_embeds_to_the_bottleneck_width(denoise):
    X = np.random.default_rng(0).random((200, 30))
    Z = AutoencoderEmbedding(dim=4, hidden=8, denoise=denoise, max_iter=5).fit(X).transform(X)
    assert Z.shape == (200, 4) and np.isfinite(Z).all()


# ── evaluation and narratives ────────────────────────────────────────────────────────

def test_top_k_and_paired_bootstrap():
    y = np.array([1, 0, 0, 1, 0, 0, 0, 0, 0, 0] * 20)
    good = y + np.random.default_rng(1).normal(0, 0.3, len(y))
    noise = np.random.default_rng(2).random(len(y))
    assert top_k(y, good, 0.2)[0] > 0.8
    d = paired_bootstrap_delta(y, good, noise, n=100)
    assert d["delta"] > 0 and d["ci95"][0] > 0 and d["share_of_resamples_new_better"] == 1.0


def test_narrative_is_templated_from_contributions():
    row = pd.Series({"agey1x": 78, "ipdisy1": 2, "ertoty1": 0, "povcaty1": np.nan})
    text = narrative(0.31, 0.09, row, {"ipdisy1": 0.7, "agey1x": 0.4, "ertoty1": -0.1, "povcaty1": 0.0})
    assert "31%" in text and "9%" in text
    assert "2 hospital stays last year (odds ×2.01)" in text
    assert "0 ER visits last year" in text and "not causes" in text
    assert describe("povcaty1", np.nan) == "povcaty1 not recorded"
