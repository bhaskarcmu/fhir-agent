"""A throwaway, PROMOTED `meps-portable-v2` artifact for the service's tests (no MEPS, no lab).

Built the way the lab builds the real one (augmentation step, a TF-IDF/LSA block over the ICD-10
tokens, gradient boosting, a comparison model) and written with the same metadata keys the lab's
`promote` writes, so the service code under test is the code that serves the real artifact.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import TruncatedSVD
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline

from outcome_prediction import contract
from outcome_prediction.model.artifact import score_quantiles, write_artifact
from outcome_prediction.model.portable import MissingnessAugmenter, comparison_model
from outcome_prediction.model.promotion import write_promotion
from outcome_prediction.tests.conftest import synthetic_table

CATS = list(contract.CATEGORICAL)
NUMS = [f for f in contract.names(contract.DEFAULT_TIERS) if f not in CATS]
INPUTS = CATS + NUMS + [contract.TEXT_COLUMN]


def portable_frame(n_per_panel: int = 200, seed: int = 2):
    t = synthetic_table(per_panel=n_per_panel, seed=seed)
    rng = np.random.default_rng(seed)
    for c in ("mcrevy1", "mcdevy1"):
        t[c] = (rng.random(len(t)) < 0.3).astype(float)
    for c in ("n_icd", "n_icd_chapters", "n_distinct_drugs", "hfrs", "charlson_approx", "elixhauser_vw_approx",
              "elixhauser_count_approx"):
        t[c] = rng.poisson(2, len(t)).astype(float)
    vocab = ["icdI10", "icdE11", "icdI25", "icdJ45", "icdM17", "icdE78", "icdK05", "icdZ73"]
    t[contract.TEXT_COLUMN] = [" ".join(rng.choice(vocab, 3, replace=False)) for _ in range(len(t))]
    t["admit_nonobstetric_y2"] = t["label_hosp_12m"]
    return t


def build_portable_artifact(models: Path) -> Path:
    t = portable_frame()
    X, y = t[INPUTS], t["admit_nonobstetric_y2"].to_numpy()
    cols = ColumnTransformer([("dense", "passthrough", CATS + NUMS),
                              ("codes", Pipeline([("tfidf", TfidfVectorizer(token_pattern=r"\S+", lowercase=False)),
                                                  ("svd", TruncatedSVD(4, random_state=0))]), contract.TEXT_COLUMN)])
    model = Pipeline([("augment", MissingnessAugmenter({"povcaty1": 0.5})), ("cols", cols),
                      ("clf", HistGradientBoostingClassifier(max_iter=40, random_state=0,
                                                             categorical_features=list(range(len(CATS)))))]).fit(X, y)
    comparison = comparison_model(["agey1x", "ipdisy1"]).fit(X[["agey1x", "ipdisy1"]], y)
    blanked = X.assign(povcaty1=np.nan)
    typical = {f: float(X[f].mode().iloc[0]) if f in CATS else float(X[f].median()) for f in CATS + NUMS}
    metadata = {
        "model_id": "gbm-meps-portable-v2-test-000000000000", "contract_version": contract.CONTRACT_VERSION,
        "label": "admit_nonobstetric_y2", "outcome": "an overnight hospital stay that isn't related to pregnancy",
        "features": INPUTS, "categorical": CATS, "text_columns": [contract.TEXT_COLUMN],
        "blank_at_scoring": ["povcaty1"], "comparison_inputs": ["agey1x", "ipdisy1"],
        "training": {"panels": [21, 22, 23, 24, 25], "rows": len(t), "events": int(y.sum())},
        "validation_metrics": {"model": {"auroc": 0.8}, "comparison": {"auroc": 0.7}},
        "metrics_note": "synthetic test artifact",
        "training_score_quantiles": score_quantiles(model.predict_proba(blanked)[:, 1]),
        "typical": {**typical, contract.TEXT_COLUMN: ""}, "round": "test", "run": "test",
        "versions": {}, "created_at": "2026-10-18T00:00:00+00:00",
    }
    directory = write_artifact(models / metadata["model_id"], model, comparison, metadata)
    write_promotion(directory, "O59", round="test", run="test", note="synthetic test artifact")
    return directory
