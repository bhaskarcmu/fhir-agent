"""Unit tests for the feature matrix, fitting, evaluation and the train pipeline — on a
synthetic table, so no MEPS data is needed."""
from __future__ import annotations

import json

import numpy as np
import pytest

from outcome_prediction.meps.build import build
from outcome_prediction.model import (
    CATEGORICAL, FEATURES, ContractMismatch, comparison_matrix, feature_matrix, split_masks,
)
from outcome_prediction.model.artifact import load_artifact
from outcome_prediction.model.evaluate import evaluate, render_report, top_k
from outcome_prediction.model.train import METRICS_PROVENANCE, train
from outcome_prediction.tests.conftest import person, synthetic_table


@pytest.fixture(scope="module")
def table():
    return synthetic_table()


@pytest.fixture(scope="module")
def metrics(table):
    return evaluate(table)


def test_feature_matrix_is_the_contract_in_order(table):
    X = feature_matrix(table)
    assert list(X.columns) == FEATURES and len(FEATURES) == 25


def test_categoricals_clip_negative_missing_codes_to_zero(table):
    X = feature_matrix(table)
    assert (table["regiony1"] == -1).any()
    assert X["regiony1"].min() == 0
    assert all(X[c].dtype.kind == "i" for c in CATEGORICAL)


def test_contract_mismatch_is_refused(table):
    with pytest.raises(ContractMismatch):
        feature_matrix(table.drop(columns=["choldx"]))
    reordered = table[[c for c in table.columns if c != "sex"] + ["sex"]]
    with pytest.raises(ContractMismatch):
        feature_matrix(reordered)


def test_build_output_satisfies_the_contract(write_panel):
    """The table M1's build writes is exactly what the model consumes."""
    df, _ = build({21: write_panel("h1.dta", [person("A", 21), person("B", 21)])})
    assert list(feature_matrix(df).columns) == FEATURES


def test_comparison_matrix_is_age_and_any_prior_stay(table):
    B = comparison_matrix(table)
    assert B.shape == (len(table), 2)
    assert np.array_equal(B[:, 1], (table["ipdisy1"] > 0).to_numpy())


def test_split_is_temporal(table):
    train, test = split_masks(table)
    assert set(table.panel[train]) == {21, 22, 23, 24, 25}
    assert set(table.panel[test]) == {26, 27}
    assert not (train & test).any()


def test_top_k_ppv_and_sensitivity():
    y = np.array([1, 0, 1, 0, 0, 0, 0, 0, 0, 1])
    p = np.linspace(1, 0, 10)        # descending: first items are highest risk
    assert top_k(y, p, 0.2) == (0.5, 1 / 3)
    assert top_k(y, p, 0.3) == (2 / 3, 2 / 3)


def test_evaluation_covers_fr_e1_to_e5(metrics):
    s = metrics["split"]
    assert (s["n_train"], s["n_test"]) == (1500, 600)
    for name in ("comparison", "gbm"):
        m = metrics[name]
        assert m["auroc_ci95"][0] <= m["auroc"] <= m["auroc_ci95"][1]
        assert m["auprc_ci95"][0] <= m["auprc"] <= m["auprc_ci95"][1]
        assert set(m["top_k"]) == {"5%", "10%", "20%"}
    assert "auroc_survey_weighted" in metrics["gbm"]
    assert [d["decile"] for d in metrics["calibration_deciles"]] == list(range(1, 11))
    assert [g["group"] for g in metrics["subgroups"]] == [
        "age 18-44", "age 45-64", "age 65+", "male", "female", "no prior stay", "prior stay"]
    assert list(metrics["permutation_importance"]) and set(metrics["permutation_importance"]) == set(FEATURES)


def test_evaluation_is_deterministic(table, metrics):
    again = evaluate(table)
    assert again["gbm"]["auroc_ci95"] == metrics["gbm"]["auroc_ci95"]
    assert again["permutation_importance"] == metrics["permutation_importance"]


def test_models_learn_the_planted_signal(metrics):
    assert metrics["comparison"]["auroc"] > 0.6
    assert metrics["comparison_coefficients"]["age_per_year"] > 0
    assert metrics["comparison_coefficients"]["prior_stay"] > 0


def test_report_renders_every_section(metrics):
    report = render_report(metrics, "gbm-test")
    for heading in ("Calibration by decile", "Subgroups", "Permutation importance", "Comparison model"):
        assert heading in report
    assert "`gbm-test`" in report


def test_train_writes_a_loadable_artifact_and_reports(tmp_path, table):
    csv = tmp_path / "table.csv"
    table.to_csv(csv, index=False)

    directory, metrics = train(csv, tmp_path / "models", tmp_path / "reports")

    artifact = load_artifact(directory)
    meta = artifact.metadata
    assert meta["model_id"] == directory.name and meta["contract_version"] == "meps25-v1"
    assert meta["features"] == FEATURES
    assert meta["training"]["rows"] == len(table) and meta["training"]["panels"] == list(range(21, 28))
    assert meta["validation_metrics"]["provenance"] == METRICS_PROVENANCE
    assert meta["validation_metrics"]["gbm"]["auroc"] == metrics["gbm"]["auroc"]
    assert len(meta["training_score_quantiles"]) == 101
    assert meta["versions"]["scikit-learn"] == "1.9.1"
    # Both models are persisted and usable (O18).
    X = feature_matrix(table)
    assert artifact.model.predict_proba(X)[:, 1].shape == (len(table),)
    assert artifact.comparison.predict_proba(comparison_matrix(table))[:, 1].shape == (len(table),)
    reports = json.loads((tmp_path / "reports" / "metrics.json").read_text())
    assert reports["gbm"]["auroc"] == metrics["gbm"]["auroc"]
    assert (tmp_path / "reports" / "model_report.md").exists()


def test_train_never_overwrites_an_artifact(tmp_path, table):
    csv = tmp_path / "table.csv"
    table.to_csv(csv, index=False)
    train(csv, tmp_path / "models", tmp_path / "reports")
    with pytest.raises(FileExistsError):
        train(csv, tmp_path / "models", tmp_path / "reports")
