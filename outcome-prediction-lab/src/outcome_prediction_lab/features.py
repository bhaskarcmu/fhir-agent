"""Feature sets and model pipelines for round 001.

Every learned transformation — TF-IDF vocabulary and weights, SVD axes, autoencoder weights,
imputers, scalers — lives INSIDE a scikit-learn Pipeline, so cross-validation refits it on each
training fold and nothing is learned from the fold being scored.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import TruncatedSVD
from sklearn.ensemble import (
    HistGradientBoostingClassifier, HistGradientBoostingRegressor, RandomForestClassifier,
)
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from outcome_prediction.model import FEATURES as PROTO_FEATURES

CATEGORICAL = ["sex", "racethx", "regiony1", "inscovy1", "povcaty1"]
NUMERIC_BASE = [f for f in PROTO_FEATURES if f not in CATEGORICAL]
DX_FLAGS = ["hibpdx", "chddx", "angidx", "midx", "ohrtdx", "strkdx", "emphdx", "diabdx",
            "arthdx", "asthdx", "choldx"]
COVERAGE = ["mcrevy1", "mcdevy1"]
CODE_COUNTS = ["n_icd", "n_ccsr_systems", "n_rx_classes", "n_suppressed_codes"]
KNOWLEDGE = ["hfrs", "charlson_approx", "elixhauser_vw_approx", "elixhauser_count_approx"]
SURVEY_NUMERIC = ["rthlth1", "rthlth2", "mnhlth1", "mnhlth2", "adlhlp1", "iadlhp1", "actlim1",
                  "k6sum2", "phq22", "vpcs2", "vmcs2", "educyr"]
SURVEY_CATEGORICAL = ["empst1", "marryy1x", "hideg"]
# Risk should never FALL as these rise — domain knowledge, imposed as monotonic constraints.
MONOTONE_UP = {"ipdisy1", "ipngtdy1", "ertoty1", "hfrs", "charlson_approx", "elixhauser_vw_approx"}


def honest_frame(t: pd.DataFrame) -> pd.DataFrame:
    """Re-encode MEPS codes without hidden decisions (round 001, concept 4):
    refused / don't know / not ascertained / cannot compute (all negative codes) -> missing,
    never "no" or category 0; yes/no items -> 1/0; the raw diagnosis answers replace the
    prototype's "anything but yes is no" flags."""
    x = t.copy()
    for col in NUMERIC_BASE + CATEGORICAL + SURVEY_NUMERIC + SURVEY_CATEGORICAL:
        if col in x and col not in DX_FLAGS:
            x[col] = x[col].where(x[col] >= 0)
    for col in DX_FLAGS:
        raw = x[f"{col}_raw"]
        x[col] = np.select([raw == 1, raw == 2], [1.0, 0.0], default=np.nan)
    for col in COVERAGE + ["adlhlp1", "iadlhp1", "actlim1"]:
        x[col] = np.select([x[col] == 1, x[col] == 2], [1.0, 0.0], default=np.nan)
    return x


FEATURE_SETS = {
    "prototype": (CATEGORICAL, NUMERIC_BASE),
    "honest": (CATEGORICAL, NUMERIC_BASE),
    "portable": (CATEGORICAL, NUMERIC_BASE + COVERAGE + CODE_COUNTS),
    "portable+knowledge": (CATEGORICAL, NUMERIC_BASE + COVERAGE + CODE_COUNTS + KNOWLEDGE),
    "portable+knowledge+survey": (CATEGORICAL + SURVEY_CATEGORICAL,
                                  NUMERIC_BASE + COVERAGE + CODE_COUNTS + KNOWLEDGE + SURVEY_NUMERIC),
}


class ToDense(BaseEstimator, TransformerMixin):
    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return X.toarray() if hasattr(X, "toarray") else np.asarray(X)


class AutoencoderEmbedding(BaseEstimator, TransformerMixin):
    """A small neural autoencoder: input -> hidden -> BOTTLENECK -> hidden -> input, trained to
    reconstruct its input. The bottleneck activations are the patient's learned embedding.
    `denoise` > 0 hides that share of inputs during training (a denoising autoencoder)."""

    def __init__(self, dim=16, hidden=64, denoise=0.0, max_iter=40, random_state=0):
        self.dim, self.hidden, self.denoise = dim, hidden, denoise
        self.max_iter, self.random_state = max_iter, random_state

    def fit(self, X, y=None):
        X = np.asarray(X, dtype=np.float32)
        rng = np.random.default_rng(self.random_state)
        X_in = X * (rng.random(X.shape) >= self.denoise) if self.denoise else X
        self.net_ = MLPRegressor(hidden_layer_sizes=(self.hidden, self.dim, self.hidden),
                                 activation="tanh", max_iter=self.max_iter, batch_size=256,
                                 random_state=self.random_state).fit(X_in, X)
        return self

    def transform(self, X):
        h = np.asarray(X, dtype=np.float32)
        for W, b in zip(self.net_.coefs_[:2], self.net_.intercepts_[:2]):   # encoder half only
            h = np.tanh(h @ W + b)
        return h


def tfidf():
    # Codes are whitespace-separated tokens ("icdI10", "CIR007", "rx58"). min_df: a code must
    # appear in 20+ training-fold people to earn a column — rare codes are noise at this size.
    return TfidfVectorizer(token_pattern=r"\S+", lowercase=False, min_df=20, sublinear_tf=True)


def text_block(kind: str):
    if kind == "lsa":
        return Pipeline([("tfidf", tfidf()), ("svd", TruncatedSVD(32, random_state=0))])
    if kind in ("ae", "dae"):
        return Pipeline([("tfidf", tfidf()), ("dense", ToDense()),
                         ("ae", AutoencoderEmbedding(denoise=0.2 if kind == "dae" else 0.0))])
    raise ValueError(kind)


GBM_DEFAULT = {"max_iter": 300, "learning_rate": 0.05, "random_state": 0}


def make_model(model: str, cats: list[str], nums: list[str], text: str | None = None,
               task: str = "binary", params: dict | None = None, monotone: bool = False):
    """Columns are ordered categoricals first, so their positions in the transformed matrix are
    known. `text` adds a learned code representation ('lsa', 'ae', 'dae'; 'tfidf' only with lr)."""
    params = {**GBM_DEFAULT, **(params or {})}
    if model == "lr":
        blocks = [("num", Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True)),
                                    ("scale", StandardScaler())]), nums),
                  ("cat", Pipeline([("impute", SimpleImputer(strategy="constant", fill_value=-1)),
                                    ("onehot", OneHotEncoder(handle_unknown="ignore"))]), cats)]
        if text == "tfidf":
            blocks.append(("tfidf", tfidf(), "tokens"))
        return Pipeline([("cols", ColumnTransformer(blocks)),
                         ("clf", LogisticRegression(C=0.5, max_iter=3000))])

    blocks = [("dense", "passthrough", cats + nums)]
    if text:
        blocks.append(("codes", text_block(text), "tokens"))
    cols = ColumnTransformer(blocks)
    is_cat = [True] * len(cats) + [False] * len(nums)
    if model == "rf":
        return Pipeline([("cols", cols), ("clf", RandomForestClassifier(
            n_estimators=400, min_samples_leaf=20, max_features="sqrt", n_jobs=-1, random_state=0))])

    def extended(mask):          # pad masks for appended code columns (32 LSA / 16 AE dims)
        extra = {None: 0, "lsa": 32, "ae": 16, "dae": 16}[text]
        return mask + [type(mask[0])() if isinstance(mask[0], bool) else 0] * extra

    mono = extended([1 if (monotone and c in MONOTONE_UP) else 0 for c in cats + nums]) if monotone else None
    gbm_kwargs = {**params, "categorical_features": extended(is_cat)}
    if mono:
        gbm_kwargs["monotonic_cst"] = mono
    if task == "binary":
        est = HistGradientBoostingClassifier(**gbm_kwargs)
    elif task == "count":
        est = HistGradientBoostingRegressor(loss="poisson", **gbm_kwargs)
    elif task == "cost":
        est = HistGradientBoostingRegressor(loss="squared_error", **gbm_kwargs)   # on log1p(cost)
    else:
        raise ValueError(task)
    return Pipeline([("cols", cols), ("clf", est)])
