"""Fitting the gradient-boosting model and the comparison model (FR-M1, FR-M2).

Importable functions, not only CLIs: the lab (M3) calls these (decisions.md O29).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression

from outcome_prediction.model import (
    COMPARISON_PARAMS, GBM_PARAMS, LABEL, categorical_indices, comparison_matrix,
    feature_matrix, split_masks,
)


def fit_gbm(X: pd.DataFrame, y: np.ndarray) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        **GBM_PARAMS, categorical_features=categorical_indices()).fit(X, y)


def fit_comparison(B: np.ndarray, y: np.ndarray) -> LogisticRegression:
    return LogisticRegression(**COMPARISON_PARAMS).fit(B, y)


@dataclass(frozen=True)
class Fitted:
    gbm: HistGradientBoostingClassifier
    comparison: LogisticRegression


def fit_validation(table: pd.DataFrame) -> Fitted:
    """Both models on the training panels only (21–25) — the models whose test-panel metrics
    are reported."""
    train, _ = split_masks(table)
    y = table[LABEL].to_numpy()
    return Fitted(gbm=fit_gbm(feature_matrix(table)[train], y[train]),
                  comparison=fit_comparison(comparison_matrix(table)[train], y[train]))


def fit_release(table: pd.DataFrame) -> Fitted:
    """Both models refit on all panels, for serving. Their own held-out performance is
    unknown by construction (design.md §11, defect 5)."""
    y = table[LABEL].to_numpy()
    return Fitted(gbm=fit_gbm(feature_matrix(table), y),
                  comparison=fit_comparison(comparison_matrix(table), y))
