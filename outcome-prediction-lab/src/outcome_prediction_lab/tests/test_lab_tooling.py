"""Tests for round-002 tooling — CLI engine, vocabulary, narratives, notebook check. Synthetic data."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from outcome_prediction_lab import holdout, narrate, notebooks, runs, vocabulary

# ── vocabulary ───────────────────────────────────────────────────────────────────────

CONDITIONS_HTML = """<table><tr><th>ICD10CDX VALUE</th><th>ICD10CDX LABEL</th><th>UNWEIGHTED</th></tr>
<tr><td>-15</td><td>CANNOT BE COMPUTED</td><td>1</td></tr><tr><td>I50</td><td>HEART FAILURE</td><td>9</td></tr>
<tr><td>E11</td><td>TYPE 2 DIABETES MELLITUS</td><td>9</td></tr></table>
<table><tr><th>CCSR1X VALUE</th><th>CCSR1X LABEL</th><th>CCSR2X VALUE</th><th>CCSR2X LABEL</th></tr>
<tr><td>CIR019</td><td>HEART FAILURE</td><td>END002</td><td>DIABETES MELLITUS WITHOUT COMPLICATION</td></tr></table>"""
RX_HTML = """<table><tr><th>Therapeutic Class Code</th><th>Definition</th></tr>
<tr><td>-1</td><td>inapplicable</td></tr><tr><td>215</td><td>insulin</td></tr></table>"""


def test_vocabulary_parses_ahrq_tables_and_sentence_cases():
    icd, ccsr, rx = {}, {}, {}
    vocabulary.parse_conditions_doc(CONDITIONS_HTML, icd, ccsr)
    vocabulary.parse_prescribed_doc(RX_HTML, rx)
    assert icd == {"I50": "Heart failure", "E11": "Type 2 diabetes mellitus"}
    assert ccsr == {"CIR019": "Heart failure", "END002": "Diabetes mellitus without complication"}
    assert rx == {"215": "insulin"}


def test_tokens_get_names_and_unnamed_groups_their_body_system():
    vocab = {"icd": {"I50": "Heart failure"}, "ccsr": {}, "rx_class": {"215": "insulin"},
             "body_system": vocabulary.BODY_SYSTEMS}
    assert vocabulary.name_token("icdI50", vocab) == ("diagnosis", "Heart failure")
    assert vocabulary.name_token("rx215", vocab) == ("medicine class", "insulin")
    assert vocabulary.name_token("NVS008", vocab) == ("condition group", "a nervous system condition group")
    assert vocabulary.describe_tokens("icdI50 rx215 icdI50", vocab) == "Heart failure . insulin"


def test_acronyms_survive_sentence_casing():
    assert vocabulary.sentence_case("HIV DISEASE AND COPD") == "HIV disease and COPD"


# ── narratives ───────────────────────────────────────────────────────────────────────

def test_a_lowering_factor_that_is_above_average_on_its_own_is_explained():
    vocab = {"icd": {}, "ccsr": {}, "rx_class": {"118": "nonsteroidal anti-inflammatory agents"},
             "body_system": vocabulary.BODY_SYSTEMS}
    agg = _agg(); agg.by_token["rx118"] = 0.13
    phrase = narrate._code_phrase("rx118", agg, "were hospitalised", vocab, up=False)
    assert "13% of adults with this were hospitalised — above the average on its own" in phrase
    assert "points to lower risk" in phrase


def test_relative_and_percentage_wording():
    assert narrate.pct(0.004) == "under 1%" and narrate.pct(0.064) == "6.4%" and narrate.pct(0.31) == "31%"
    assert narrate.relative(0.30, 0.10) == "about 3.0 times"
    assert narrate.relative(0.10, 0.10) == "about the same as"
    assert narrate.relative(0.05, 0.10) == "about 50% of"


def _agg():
    a = narrate.Aggregates(label="admit_nonobstetric_y2", overall=0.08)
    a.by_band = {"18–44": 0.03, "45–64": 0.06, "65–74": 0.12, "75 and over": 0.2}
    a.by_band_sex = {("65–74", 2): 0.11}
    a.prior_stay = {True: 0.28, False: 0.06}
    a.prior_er = {True: 0.15, False: 0.07}
    a.by_token = {"icdI50": 0.27}
    a.by_condition = {c: 0.1 for c in narrate.CONDITION}
    a.medians = {"totexpy1": 1800.0, "rxtoty1": 6.0, "obtotvy1": 3.0}
    return a


def test_narrative_is_self_explanatory_with_names_and_comparison_groups():
    row = pd.DataFrame([{"agey1x": 72, "sex": 2, "ipdisy1": 2, "ertoty1": 0, "povcaty1": np.nan,
                         "racethx": 3, "tokens": "icdI50"}])
    vocab = {"icd": {"I50": "Heart failure"}, "ccsr": {}, "rx_class": {}, "body_system": vocabulary.BODY_SYSTEMS}
    text = narrate.narrative(row, 0.31, {"ipdisy1": 0.8, "racethx": 0.9, "ertoty1": -0.1, "agey1x": 0.3},
                             {"icdI50": 0.5}, _agg(), vocab, "an overnight hospital stay", income_range=(0.27, 0.33))
    assert "72-year-old woman has an estimated 31% chance of an overnight hospital stay" in text
    assert "about 3.9 times the average adult (8.0%)" in text and "women aged 65–74 (11%)" in text
    assert "2 overnight hospital stays in the past year (28% of adults with a hospital stay" in text
    assert "a diagnosis of heart failure (27% of adults with this were hospitalised for reasons other than childbirth)" in text
    assert text.count("an overnight hospital stay") == 1           # full outcome once, short form after
    assert "icdI50" not in text and "I50" not in text            # no codes to look up
    assert "race" not in text.lower()                            # never narrated per patient
    assert "between 27% and 33%" in text and "not a diagnosis" in text


# ── runs: config guard, run, confirm guard, card, scorecard, promotion ───────────────

def _frame(n_per_panel=160, seed=0):
    from outcome_prediction.tests.conftest import synthetic_table
    t = synthetic_table(per_panel=n_per_panel, seed=seed)
    rng = np.random.default_rng(seed)
    for c in ("mcrevy1", "mcdevy1"):
        t[c] = rng.integers(0, 2, len(t)).astype(float)
    for c in ("n_icd", "n_ccsr_systems", "n_rx_classes", "n_suppressed_codes", "hfrs", "charlson_approx",
              "elixhauser_vw_approx", "elixhauser_count_approx"):
        t[c] = rng.poisson(2, len(t)).astype(float)
    vocab = [f"icdA{i:02d}" for i in range(40)] + [f"rx{i}" for i in range(20)]   # > 32 LSA dims
    t["tokens"] = [" ".join(rng.choice(vocab, 4)) for _ in range(len(t))]
    t["desc_text"] = t["tokens"].str.replace("icd", "condition ", regex=False)
    t["drug_names"] = "ASPIRIN | METFORMIN"
    t["admit_nonobstetric_y2"] = t["label_hosp_12m"]
    return t


@pytest.fixture
def lab(tmp_path, monkeypatch):
    rounds = tmp_path / "rounds"
    (rounds / "r1" / "configs").mkdir(parents=True)
    decisions = tmp_path / "decisions.md"
    decisions.write_text("| O99 | a decision | Accepted | x |\n")
    monkeypatch.setattr(runs, "ROUNDS", rounds)
    monkeypatch.setattr(runs, "DECISIONS", decisions)
    monkeypatch.setenv("OUTCOME_PREDICTION_MODELS_DIR", str(tmp_path / "models"))
    ledger = tmp_path / "ledger.md"
    monkeypatch.setattr(holdout, "LEDGER", ledger)
    monkeypatch.setattr(holdout.require, "__defaults__", (ledger,))
    monkeypatch.setattr(holdout.record, "__defaults__", ((26, 27), ledger))

    def write(name, **cfg):
        cfg = {"name": name, "label": "admit_nonobstetric_y2", "task": "binary",
               "features": "portable+knowledge", "model": "gbm", "params": {"max_iter": 30},
               "baseline_inputs": ["agey1x", "ipdisy1"], **cfg}
        (rounds / "r1" / "configs" / f"{name}.json").write_text(json.dumps(cfg))
    return write


def test_configs_cannot_name_panels_or_splits(lab):
    lab("sneaky", test_panels=[26, 27])
    with pytest.raises(runs.ConfigError, match="unknown keys"):
        runs.load_config(runs.config_path("r1", "sneaky"))


def test_run_compare_confirm_card_scorecard_promote(lab, tmp_path):
    frame = _frame()
    lab("m", text=["lsa"])
    r = runs.run("r1", "m", frame=frame)
    assert 0.5 < r["cv"]["auroc"] <= 1 and "cv_baseline" in r
    assert "`m`" in runs.compare("r1")

    with pytest.raises(holdout.NotInLedger):                     # the test panels need a ledger entry
        runs.confirm("r1", "m", frame=frame)
    holdout.record("r1", "m", "unit test")
    c = runs.confirm("r1", "m", frame=frame)
    assert c["test"]["n"] == 2 * 160 and runs.fitted_path("r1", "m").exists()

    with pytest.raises(runs.PromotionRefused, match="model card"):
        runs.promote("r1", "m", "O99")
    card = runs.card("r1", "m").read_text()
    assert "Uplift / impactability is not assessable" in card and "Test performance" in card
    sc = runs.scorecard("r1", "m").read_text()
    assert "_TO BE SCORED BY A PERSON_" in sc and "Worklist value" in sc
    with pytest.raises(runs.PromotionRefused, match="not in"):
        runs.promote("r1", "m", "O12345")
    rec = json.loads(runs.promote("r1", "m", "O99").read_text())
    assert rec["decision"] == "O99" and rec["model_sha256"] == c["fitted_model_sha256"]


def test_learning_only_runs_are_never_promoted(lab):
    frame = _frame()
    lab("death", learning_only=True)
    runs.run("r1", "death", frame=frame)
    holdout.record("r1", "death", "unit test")
    runs.confirm("r1", "death", frame=frame)
    runs.card("r1", "death")
    with pytest.raises(runs.PromotionRefused, match="learning-only"):
        runs.promote("r1", "death", "O99")


# ── notebooks (O38) ──────────────────────────────────────────────────────────────────

def test_notebook_check_flags_outputs_and_strip_fixes_them(tmp_path):
    nb = {"cells": [{"cell_type": "code", "execution_count": 3, "outputs": [{"text": "x"}], "source": []},
                    {"cell_type": "markdown", "source": []}], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    path = tmp_path / "a.ipynb"
    path.write_text(json.dumps(nb))
    assert len(notebooks.check(tmp_path)) == 2
    notebooks.strip(path)
    assert notebooks.check(tmp_path) == []


def test_committed_notebooks_are_clean():
    assert notebooks.check() == []


# ── portable contract and missingness augmentation (O52, O53) ────────────────────────

def test_augmenter_hides_values_only_while_fitting():
    from outcome_prediction_lab.features import MissingnessAugmenter
    X = pd.DataFrame({"povcaty1": [1.0] * 1000, "agey1x": [50.0] * 1000})
    aug = MissingnessAugmenter({"povcaty1": 0.5})
    fitted = aug.fit_transform(X)
    assert 0.4 < fitted.povcaty1.isna().mean() < 0.6 and fitted.agey1x.notna().all()
    assert aug.transform(X).povcaty1.notna().all()                  # scoring rows are never touched
    assert X.povcaty1.notna().all()                                 # and the input isn't mutated


def test_contract_feature_sets_obey_their_tiers():
    from outcome_prediction_lab.features import FEATURE_SETS
    records = set(sum(FEATURE_SETS["portable-v2"], []))
    claims = set(sum(FEATURE_SETS["portable-v2+claims"], []))
    assert "totexpy1" not in records | claims
    assert {"rxtoty1", "hhtotdy1"} <= claims - records
    assert {"n_icd_chapters", "n_distinct_drugs"} <= records and "n_ccsr_systems" not in records


def test_configs_may_request_augmentation_and_production_scoring(lab):
    lab("p", features="portable-v2", augment_missing={"povcaty1": 0.5},
        simulate_missing_at_scoring=["povcaty1"])
    cfg = runs.load_config(runs.config_path("r1", "p"))
    assert runs._scoring_hook(cfg)(pd.DataFrame({"povcaty1": [3.0]})).povcaty1.isna().all()


# ── population filter and fairness (round 004) ───────────────────────────────────────

def test_population_filter_restricts_training_and_scoring(lab):
    frame = _frame()
    lab("old", population={"age_min": 65})
    r = runs.run("r1", "old", frame=frame)
    assert r["cv"]["n"] == int(((frame.agey1x >= 65) & frame.panel.isin([21, 22, 23, 24, 25])).sum())
    lab("bad", population={"income_min": 3})
    with pytest.raises(runs.ConfigError, match="age_min"):
        runs.run("r1", "bad", frame=frame)


def test_fairness_report_covers_groups_and_flags_small_ones():
    from outcome_prediction_lab import fairness
    rng = np.random.default_rng(0)
    n = 3000
    df = pd.DataFrame({"racethx": rng.choice([1, 2, 3, 4, 5], n, p=[.2, .6, .12, .07, .01]),
                       "inscovy1": rng.choice([1, 2, 3], n), "sex": rng.choice([1, 2], n),
                       "agey1x": rng.integers(18, 90, n)})
    p = rng.random(n)
    y = (rng.random(n) < p * 0.3).astype(float)
    rep = fairness.report(y, p, df)
    assert set(rep["groups"]) == {"Race / ethnicity", "Insurance (year 1)", "Sex", "Age band"}
    assert abs(rep["overall"]["flagged_share"] - 0.10) < 0.01
    small = [r for r in rep["groups"]["Race / ethnicity"] if r["group"] == "Other or multiple, non-Hispanic"][0]
    assert small["auroc"] is None and "too few events" in small["note"]
    assert "Widest gaps" in fairness.markdown(rep, "x")


def test_fairness_needs_its_own_ledger_entry(lab):
    from outcome_prediction_lab import fairness
    frame = _frame()
    lab("m")
    runs.run("r1", "m", frame=frame)
    holdout.record("r1", "m", "unit test")
    runs.confirm("r1", "m", frame=frame)
    with pytest.raises(holdout.NotInLedger):
        fairness.run("r1", "m")
