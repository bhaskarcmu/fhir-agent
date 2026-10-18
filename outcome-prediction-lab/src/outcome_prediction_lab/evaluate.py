"""Honest evaluation for round 001 (decisions.md O32).

Exploration: leave-one-panel-out cross-validation within the TRAINING panels (21–25) — each
panel is predicted by a model that never saw it, the closest a training-only scheme gets to
"a new year of patients". The test panels (26–27) are touched only by `confirm` in round_001,
after a ledger entry, for finalists chosen beforehand on cross-validation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import (
    average_precision_score, brier_score_loss, mean_poisson_deviance, r2_score, roc_auc_score,
)
from sklearn.model_selection import LeaveOneGroupOut

TRAIN_PANELS = (21, 22, 23, 24, 25)
TEST_PANELS = (26, 27)


def cv_predict(factory, X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, *, proba=True,
               train_hook=None, test_hook=None) -> np.ndarray:
    """Out-of-fold predictions. Hooks transform a fold's training or scoring rows (used to
    simulate production missingness without leaking it into training, or vice versa)."""
    out = np.full(len(y), np.nan)
    for tr, te in LeaveOneGroupOut().split(X, y, groups):
        Xtr, Xte = X.iloc[tr], X.iloc[te]
        if train_hook:
            Xtr = train_hook(Xtr)
        if test_hook:
            Xte = test_hook(Xte)
        model = factory().fit(Xtr, y[tr])
        out[te] = model.predict_proba(Xte)[:, 1] if proba else model.predict(Xte)
    return out


def top_k(y, p, frac=0.10):
    k = int(len(y) * frac)
    idx = np.argsort(-p, kind="stable")[:k]
    return float(y[idx].mean()), float(y[idx].sum() / max(y.sum(), 1))


def binary_metrics(y, p, age=None) -> dict:
    y, p = np.asarray(y), np.asarray(p)
    ppv, sens = top_k(y, p)
    m = {"n": int(len(y)), "rate": float(y.mean()), "auroc": float(roc_auc_score(y, p)),
         "auprc": float(average_precision_score(y, p)), "brier": float(brier_score_loss(y, p)),
         "mean_pred": float(p.mean()), "top10_ppv": ppv, "top10_sensitivity": sens}
    if age is not None:
        old = np.asarray(age) >= 65
        m["auroc_65plus"] = float(roc_auc_score(y[old], p[old]))
    return m


def count_metrics(y, mu) -> dict:
    y, mu = np.asarray(y, float), np.clip(np.asarray(mu, float), 1e-6, None)
    top = np.argsort(-mu, kind="stable")[: int(len(y) * 0.10)]
    return {"n": int(len(y)), "mean": float(y.mean()),
            "poisson_deviance": float(mean_poisson_deviance(y, mu)),
            "poisson_deviance_null": float(mean_poisson_deviance(y, np.full_like(y, y.mean()))),
            "spearman": float(spearmanr(y, mu).statistic),
            "top10_share_of_events": float(y[top].sum() / y.sum())}


def cost_metrics(cost, pred_log) -> dict:
    cost, pred_log = np.asarray(cost, float), np.asarray(pred_log, float)
    top = np.argsort(-pred_log, kind="stable")[: int(len(cost) * 0.10)]
    return {"n": int(len(cost)), "mean_cost": float(cost.mean()),
            "r2_log": float(r2_score(np.log1p(cost), pred_log)),
            "spearman": float(spearmanr(cost, pred_log).statistic),
            "top10_share_of_spend": float(cost[top].sum() / cost.sum())}


def paired_bootstrap_delta(y, p_new, p_old, metric=roc_auc_score, n=500, seed=0) -> dict:
    """How much better is p_new than p_old ON THE SAME PEOPLE — resampling people jointly, so the
    interval reflects the difference, not two independent uncertainties."""
    rng = np.random.default_rng(seed)
    y, p_new, p_old = map(np.asarray, (y, p_new, p_old))
    deltas = []
    for _ in range(n):
        s = rng.integers(0, len(y), len(y))
        if y[s].min() == y[s].max():
            continue
        deltas.append(metric(y[s], p_new[s]) - metric(y[s], p_old[s]))
    lo, hi = np.percentile(deltas, [2.5, 97.5])
    return {"delta": float(metric(y, p_new) - metric(y, p_old)), "ci95": [float(lo), float(hi)],
            "share_of_resamples_new_better": float(np.mean(np.array(deltas) > 0))}
