"""Model building blocks the served `meps-portable-v2` models are made of (M12).

They live in the service, not the lab, because a served model is unpickled by the service, and
the service never imports the lab (decisions.md O29). The lab imports them from here.
"""
from __future__ import annotations

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


class MissingnessAugmenter(BaseEstimator, TransformerMixin):
    """Missingness augmentation (O53) as a pipeline step: while FITTING, hide each listed column
    for a random share of training rows, so the model learns to predict without it; when
    predicting, pass rows through untouched. sklearn calls fit_transform on training data and
    transform at prediction time, so the masking can never touch a row being scored."""

    def __init__(self, rates: dict | None = None, random_state: int = 0):
        self.rates, self.random_state = rates, random_state

    def fit(self, X, y=None):
        return self

    def fit_transform(self, X, y=None, **_):
        X = X.copy()
        rng = np.random.default_rng(self.random_state)
        for col, rate in (self.rates or {}).items():
            X.loc[rng.random(len(X)) < rate, col] = np.nan
        return X

    def transform(self, X):
        return X


def comparison_model(inputs: list[str]) -> Pipeline:
    """The simple comparison model served beside a portable model (FR-S2, O18): logistic
    regression on a few inputs, median-imputed with medians LEARNED in training — so a score
    never depends on the other rows in a batch."""
    return Pipeline([
        ("cols", ColumnTransformer([("inputs", Pipeline([("impute", SimpleImputer(strategy="median")),
                                                         ("scale", StandardScaler())]), inputs)])),
        ("clf", LogisticRegression(max_iter=1000)),
    ])
