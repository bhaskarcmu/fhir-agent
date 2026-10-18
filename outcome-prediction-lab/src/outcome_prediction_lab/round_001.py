"""Round 001 — what to predict, and how (docs/phase8 M3; pre-registration in
outcome-prediction-lab/rounds/001-what-and-how/README.md).

Stages (run in order; each writes its results into the round's metrics.json):
  cv_any_stay      the prototype's exact objective: concepts and models, cross-validated
  cv_missing       production-like missingness: what survives, what helps
  cv_targets       new targets vs simple baselines, cross-validated
  confirm          ONE logged look at the test panels for the pre-named finalists
  explain          SHAP, a surrogate tree, per-patient narratives, missing-data action items

    python -m outcome_prediction_lab.round_001 <stage> [<stage> ...]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, PoissonRegressor, LinearRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from outcome_prediction.model import FEATURES as PROTO_FEATURES
from outcome_prediction_lab import holdout
from outcome_prediction_lab.data import build_lab_table
from outcome_prediction_lab.evaluate import (
    TEST_PANELS, TRAIN_PANELS, binary_metrics, cost_metrics, count_metrics, cv_predict,
    paired_bootstrap_delta,
)
from outcome_prediction_lab.features import (
    CATEGORICAL, FEATURE_SETS, NUMERIC_BASE, honest_frame, make_model,
)

ROUND = "001-what-and-how"
ROUND_DIR = Path(__file__).resolve().parents[2] / "rounds" / ROUND


def fitted_model_path() -> Path:
    """Fitted models are binaries: never in the committed round directory (O17)."""
    from outcome_prediction.settings import models_dir
    return models_dir() / f"lab-round-{ROUND}" / "any_stay_new_portable.joblib"
METRICS = ROUND_DIR / "metrics.json"
LABEL = "label_hosp_12m"


# ── data ──────────────────────────────────────────────────────────────────────────────


def frames():
    # Round 001 used the level-3 drug class only (a defect found in round 002); pinned here so the
    # recorded round-001 numbers stay reproducible.
    t = build_lab_table(rx_class_level="level3_only")
    h = honest_frame(t)
    proto = t.copy()
    for c in CATEGORICAL:                        # the prototype's own encoding (clip at 0)
        proto[c] = proto[c].clip(lower=0).astype(int)
    train = t.panel.isin(TRAIN_PANELS).to_numpy()
    test = t.panel.isin(TEST_PANELS).to_numpy()
    return t, h, proto, train, test


def load_metrics() -> dict:
    return json.loads(METRICS.read_text()) if METRICS.exists() else {}


def save_metrics(m: dict) -> None:
    ROUND_DIR.mkdir(parents=True, exist_ok=True)
    METRICS.write_text(json.dumps(m, indent=2, sort_keys=True) + "\n")


def mlflow_log(name: str, params: dict, metrics: dict) -> None:
    """Best-effort local tracking (O30); the committed metrics.json is the record (O31)."""
    try:
        import mlflow
        mlflow.set_tracking_uri(f"sqlite:///{ROUND_DIR.parents[1] / 'mlflow.db'}")   # file store retired in MLflow 3
        mlflow.set_experiment(f"round-{ROUND}")
        with mlflow.start_run(run_name=name):
            mlflow.log_params(params)
            mlflow.log_metrics({k: v for k, v in metrics.items() if isinstance(v, (int, float))})
    except Exception as exc:  # noqa: BLE001 — tracking must never break a round
        print(f"  (mlflow logging skipped: {exc.__class__.__name__})")


# ── any-stay configurations (the prototype's exact objective) ────────────────────────

ANY_STAY_CONFIGS = [
    # name,                          frame,   feature set,                  model, text,  extra
    ("prototype",                    "proto", "prototype",                  "gbm", None,  {}),
    ("honest-missing",               "honest", "honest",                    "gbm", None,  {}),
    ("+coverage+code-counts",        "honest", "portable",                  "gbm", None,  {}),
    ("+knowledge-scores",            "honest", "portable+knowledge",        "gbm", None,  {}),
    ("+knowledge +TF-IDF/LSA",       "honest", "portable+knowledge",        "gbm", "lsa", {}),
    ("+knowledge +autoencoder",      "honest", "portable+knowledge",        "gbm", "ae",  {}),
    ("+knowledge +denoising-AE",     "honest", "portable+knowledge",        "gbm", "dae", {}),
    ("+knowledge, monotonic",        "honest", "portable+knowledge",        "gbm", None,  {"monotone": True}),
    ("logistic (no codes)",          "honest", "portable+knowledge",        "lr",  None,  {}),
    ("logistic + sparse TF-IDF",     "honest", "portable+knowledge",        "lr",  "tfidf", {}),
    ("random forest",                "honest", "portable+knowledge",        "rf",  None,  {}),
    ("+survey (NOT portable)",       "honest", "portable+knowledge+survey", "gbm", None,  {}),
]

GBM_GRID = [
    {"learning_rate": lr, "max_leaf_nodes": leaves, "min_samples_leaf": leaf, "l2_regularization": l2,
     "max_iter": iters}
    for lr, iters in ((0.05, 300), (0.03, 600))
    for leaves in (15, 31)
    for leaf in (40, 120)
    for l2 in (0.0, 1.0)
]


def _run_binary(name, X, y, groups, age, factory, params, train_hook=None, test_hook=None):
    t0 = time.time()
    p = cv_predict(factory, X, y, groups, train_hook=train_hook, test_hook=test_hook)
    m = binary_metrics(y, p, age)
    m["seconds"] = round(time.time() - t0, 1)
    mlflow_log(name, params, m)
    print(f"  {name:<34} AUROC {m['auroc']:.4f}  AUPRC {m['auprc']:.4f}  Brier {m['brier']:.4f}  "
          f"65+ {m['auroc_65plus']:.4f}  ({m['seconds']}s)")
    return m, p


def cv_any_stay():
    t, h, proto, train, _ = frames()
    y, g, age = t[LABEL].to_numpy()[train], t.panel.to_numpy()[train], t.agey1x.to_numpy()[train]
    frames_ = {"proto": proto[train].reset_index(drop=True), "honest": h[train].reset_index(drop=True)}
    out = {}
    print("any-stay, leave-one-panel-out CV on panels 21–25:")
    for name, fr, fs, model, text, extra in ANY_STAY_CONFIGS:
        cats, nums = FEATURE_SETS[fs]
        X = frames_[fr]
        factory = (lambda cats=cats, nums=nums, model=model, text=text, extra=extra:
                   make_model(model, cats, nums, text=text, **extra))
        m, _ = _run_binary(name, X, y, g, age, factory,
                           {"features": fs, "model": model, "text": text, **extra})
        out[name] = {"features": fs, "model": model, "text": text, **extra, **m}

    print("gradient-boosting tuning grid on portable+knowledge (CV only):")
    cats, nums = FEATURE_SETS["portable+knowledge"]
    best = None
    for params in GBM_GRID:
        m, _ = _run_binary(f"grid {params}", frames_["honest"], y, g, age,
                           lambda params=params: make_model("gbm", cats, nums, params=params), params)
        if best is None or m["auroc"] > best[1]["auroc"]:
            best = (params, m)
    out["tuned gbm (portable+knowledge)"] = {"features": "portable+knowledge", "model": "gbm",
                                             "params": best[0], **best[1]}
    res = load_metrics()
    res["cv_any_stay"] = out
    save_metrics(res)


def cv_finalists():
    """Settle the open choices on CV BEFORE naming finalists: does the code-feature gain survive
    where pregnancy can't explain it (non-obstetric label; men only)? Do tuning, LSA and
    monotonic constraints combine? What do survey items add on top?"""
    t, h, _, train, _ = frames()
    params = load_metrics()["cv_any_stay"]["tuned gbm (portable+knowledge)"]["params"]
    cats, nums = FEATURE_SETS["portable+knowledge"]
    X = h[train].reset_index(drop=True)
    g, age = X.panel.to_numpy(), X.agey1x.to_numpy()
    out = {}
    print("final-candidate configurations (any stay, CV):")
    for name, fs, text, extra in (
            ("tuned", "portable+knowledge", None, {}),
            ("tuned + LSA", "portable+knowledge", "lsa", {}),
            ("tuned + LSA + monotonic", "portable+knowledge", "lsa", {"monotone": True}),
            ("tuned + LSA + survey (NOT portable)", "portable+knowledge+survey", "lsa", {})):
        c, n = FEATURE_SETS[fs]
        m, _ = _run_binary(name, X, X[LABEL].to_numpy(), g, age,
                           lambda c=c, n=n, text=text, extra=extra: make_model("gbm", c, n, text=text, params=params, **extra),
                           {"features": fs, "text": text, **extra})
        out[name] = m
    print("is the code gain just pregnancy codes predicting childbirth?")
    checks = {}
    for label, rows in (("admit_nonobstetric_y2 (all)", np.ones(len(X), bool)),
                        ("label_hosp_12m (men only)", (X.sex == 1).to_numpy())):
        col = label.split()[0]
        Xs = X[rows].reset_index(drop=True)
        ys, gs, ages = Xs[col].to_numpy(), Xs.panel.to_numpy(), Xs.agey1x.to_numpy()
        for text in (None, "lsa"):
            m, _ = _run_binary(f"{label} {'+LSA' if text else 'no codes'}", Xs, ys, gs, ages,
                               lambda text=text: make_model("gbm", cats, nums, text=text, params=params), {"check": label})
            checks[f"{label} | {'LSA' if text else 'no codes'}"] = m
    res = load_metrics()
    res["cv_finalists"] = out
    res["cv_pregnancy_check"] = checks
    save_metrics(res)


# ── production-like missingness ──────────────────────────────────────────────────────

# In medical records, household income/size (→ poverty category) is almost never recorded, and
# MEPS spending is PAYMENTS, which records don't hold (they hold charges). Scenario: both absent.
MISSING_IN_PRODUCTION = ["povcaty1", "totexpy1"]


def cv_missing():
    from sklearn.experimental import enable_iterative_imputer  # noqa: F401
    from sklearn.impute import IterativeImputer, SimpleImputer
    from sklearn.pipeline import Pipeline
    t, h, _, train, _ = frames()
    X = h[train].reset_index(drop=True)
    y, g, age = t[LABEL].to_numpy()[train], t.panel.to_numpy()[train], t.agey1x.to_numpy()[train]
    params = load_metrics()["cv_any_stay"]["tuned gbm (portable+knowledge)"]["params"]
    cats, nums = FEATURE_SETS["portable+knowledge"]
    rng = np.random.default_rng(0)

    def mask_all(df):
        df = df.copy(); df[MISSING_IN_PRODUCTION] = np.nan; return df

    def mask_half(df):                          # missingness augmentation (training rows only)
        df = df.copy()
        for c in MISSING_IN_PRODUCTION:
            df.loc[rng.random(len(df)) < 0.5, c] = np.nan
        return df

    gbm = lambda: make_model("gbm", cats, nums, params=params)  # noqa: E731

    def imputed(imputer):
        def factory():
            m = make_model("gbm", cats, nums, params=params)
            # impute the dense block only; categoricals stay integer-coded for the GBM
            m.steps.insert(0, ("impute", _FrameImputer(imputer, cats + nums)))
            return m
        return factory

    scenarios = {
        "complete data (reference)":                 dict(factory=gbm),
        "missing in production, model unaware":      dict(factory=gbm, test_hook=mask_all),
        "missing, median-imputed":                   dict(factory=imputed(SimpleImputer(strategy="median")), test_hook=mask_all),
        "missing, iterative (MICE-style) imputation": dict(factory=imputed(IterativeImputer(max_iter=5, random_state=0)), test_hook=mask_all),
        "missing, trained with missingness augmentation": dict(factory=gbm, train_hook=mask_half, test_hook=mask_all),
        "features dropped entirely (oracle)":        dict(factory=lambda: make_model(
            "gbm", [c for c in cats if c not in MISSING_IN_PRODUCTION],
            [c for c in nums if c not in MISSING_IN_PRODUCTION], params=params)),
    }
    out = {}
    print("production-like missingness (povcaty1 + totexpy1 absent at scoring time):")
    for name, s in scenarios.items():
        m, _ = _run_binary(name, X, y, g, age, s["factory"], {"scenario": name},
                           train_hook=s.get("train_hook"), test_hook=s.get("test_hook"))
        out[name] = m
    res = load_metrics()
    res["cv_missing"] = out
    save_metrics(res)


class _FrameImputer:
    """Impute selected columns of a DataFrame, keeping it a DataFrame (column names matter)."""

    def __init__(self, imputer, cols):
        self.imputer, self.cols = imputer, cols

    def fit(self, X, y=None):
        self.imputer.fit(X[self.cols]); return self

    def transform(self, X):
        X = X.copy()
        filled = self.imputer.transform(X[self.cols])
        X[self.cols] = filled
        for c in CATEGORICAL:                    # imputed categoricals back to valid codes
            X[c] = np.round(X[c]).clip(lower=0)
        return X

    def fit_transform(self, X, y=None):
        return self.fit(X).transform(X)

    def get_params(self, deep=True):
        return {"imputer": self.imputer, "cols": self.cols}

    def set_params(self, **p):
        for k, v in p.items(): setattr(self, k, v)
        return self


# ── new targets ──────────────────────────────────────────────────────────────────────

TARGETS = {
    # name:                 (task,    column,                 baseline inputs (year-1 analogue + age))
    "admit_nonobstetric_y2": ("binary", "admit_nonobstetric_y2", ["agey1x", "ipdisy1"]),
    "admit_via_er_y2":       ("binary", "admit_via_er_y2",       ["agey1x", "ipdisy1", "ertoty1"]),
    "any_ed_y2":             ("binary", "any_ed_y2",             ["agey1x", "ertoty1"]),
    "ed_visits_y2":          ("count",  "ed_visits_y2",          ["agey1x", "ertoty1"]),
    "high_cost_y2":          ("binary", "high_cost_y2",          ["agey1x", "totexpy1"]),
    "cost_y2":               ("cost",   "cost_y2",               ["agey1x", "totexpy1"]),
    "died_y2":               ("binary", "died_y2",               ["agey1x"]),
    "lost_insurance_y2":     ("binary", "lost_insurance_y2",     ["agey1x", "povcaty1", "inscovy1"]),
}


def _baseline(task):
    if task == "binary":
        return lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    if task == "count":
        return lambda: make_pipeline(StandardScaler(), PoissonRegressor(alpha=1e-4, max_iter=1000))
    return lambda: make_pipeline(StandardScaler(), LinearRegression())


def _baseline_inputs(df, cols, task):
    X = df[cols].fillna(df[cols].median())
    if task == "cost" or "totexpy1" in cols:
        X = X.assign(totexpy1=np.log1p(X["totexpy1"].clip(lower=0))) if "totexpy1" in cols else X
    return X


def _score(task, y_true, pred, age=None, cost=None):
    if task == "binary":
        return binary_metrics(y_true, pred, age)
    if task == "count":
        return count_metrics(y_true, pred)
    return cost_metrics(cost, pred)


def cv_targets():
    t, h, _, train, _ = frames()
    params = load_metrics()["cv_any_stay"]["tuned gbm (portable+knowledge)"]["params"]
    cats, nums = FEATURE_SETS["portable+knowledge"]
    out = {}
    for name, (task, col, base_cols) in TARGETS.items():
        rows = train & h[col].notna().to_numpy()
        X = h[rows].reset_index(drop=True)
        yraw = X[col].to_numpy(float)
        y = np.log1p(yraw) if task == "cost" else yraw
        g, age = X.panel.to_numpy(), X.agey1x.to_numpy()
        proba = task == "binary"
        text = load_metrics()["any_stay_text_choice"]
        p_model = cv_predict(lambda: make_model("gbm", cats, nums, task=task, text=text, params=params),
                             X, y, g, proba=proba)
        Xb = _baseline_inputs(X, base_cols, task)
        p_base = cv_predict(_baseline(task), Xb, y, g, proba=proba)
        m = {"task": task, "baseline_inputs": base_cols,
             "model": _score(task, y, p_model, age if proba else None, yraw),
             "baseline": _score(task, y, p_base, age if proba else None, yraw)}
        out[name] = m
        key = "auroc" if proba else ("spearman")
        print(f"  {name:<24} model {key} {m['model'][key]:.4f} | baseline {m['baseline'][key]:.4f}")
        mlflow_log(name, {"task": task}, {f"model_{k}": v for k, v in m["model"].items()})
    res = load_metrics()
    res["cv_targets"] = out
    save_metrics(res)


# ── one logged look at the test panels ───────────────────────────────────────────────

def _fit_train_score_test(factory, X_all, y_all, train, test, proba=True):
    model = factory().fit(X_all[train], y_all[train])
    return (model.predict_proba(X_all[test])[:, 1] if proba else model.predict(X_all[test])), model


def confirm():
    t, h, proto, train, test = frames()
    res = load_metrics()
    finalists = res["preregistered_finalists"]
    params = res["cv_any_stay"]["tuned gbm (portable+knowledge)"]["params"]
    out = {}
    for cand in finalists:
        holdout.require(ROUND, cand)

    # The prototype's exact objective: any stay, same split, same test people.
    y = t[LABEL].to_numpy()
    age = t.agey1x.to_numpy()[test]
    preds = {}
    specs = {
        "any_stay/prototype": (proto, "prototype", "gbm", None, {}),
        "any_stay/new-portable": (h, "portable+knowledge", "gbm", res["any_stay_text_choice"], {"params": params}),
        "any_stay/new-with-survey": (h, "portable+knowledge+survey", "gbm", res["any_stay_text_choice"], {"params": params}),
    }
    for cand, (frame, fs, model, text, extra) in specs.items():
        cats, nums = FEATURE_SETS[fs]
        p, fitted = _fit_train_score_test(lambda: make_model(model, cats, nums, text=text, **extra),
                                          frame, y, train, test)
        preds[cand] = p
        out[cand] = binary_metrics(y[test], p, age)
        if cand == "any_stay/new-portable":
            fitted_model_path().parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(fitted, fitted_model_path())
    yt = y[test]
    old = age >= 65
    for cand in ("any_stay/new-portable", "any_stay/new-with-survey"):
        out[cand]["vs_prototype_auroc"] = paired_bootstrap_delta(yt, preds[cand], preds["any_stay/prototype"])
        out[cand]["vs_prototype_auroc_65plus"] = paired_bootstrap_delta(
            yt[old], preds[cand][old], preds["any_stay/prototype"][old])
        from sklearn.metrics import average_precision_score
        out[cand]["vs_prototype_auprc"] = paired_bootstrap_delta(
            yt, preds[cand], preds["any_stay/prototype"], metric=average_precision_score)

    # New targets: model vs its simple baseline.
    cats, nums = FEATURE_SETS["portable+knowledge"]
    for name, (task, col, base_cols) in TARGETS.items():
        cand = f"target/{name}"
        rows = h[col].notna().to_numpy()
        tr, te = train & rows, test & rows
        yraw = h[col].to_numpy(float)
        yy = np.log1p(np.nan_to_num(yraw)) if task == "cost" else np.nan_to_num(yraw)
        proba = task == "binary"
        p_model, _ = _fit_train_score_test(
            lambda: make_model("gbm", cats, nums, task=task, text=res["any_stay_text_choice"], params=params),
            h, yy, tr, te, proba)
        Xb = _baseline_inputs(h, base_cols, task)
        p_base, _ = _fit_train_score_test(_baseline(task), Xb, yy, tr, te, proba)
        out[cand] = {"model": _score(task, yy[te], p_model, h.agey1x.to_numpy()[te] if proba else None, yraw[te]),
                     "baseline": _score(task, yy[te], p_base, h.agey1x.to_numpy()[te] if proba else None, yraw[te])}
        if proba:
            out[cand]["vs_baseline_auroc"] = paired_bootstrap_delta(yy[te], p_model, p_base)
    res["confirm"] = out
    save_metrics(res)
    for k, v in out.items():
        m = v.get("model", v)
        key = "auroc" if "auroc" in m else "spearman"
        print(f"  {k:<32} {key} {m[key]:.4f}")


# ── explanations ─────────────────────────────────────────────────────────────────────

def explain():
    from outcome_prediction_lab import explain as ex
    res = load_metrics()
    res["explain"] = ex.run(ROUND_DIR, res)
    save_metrics(res)


STAGES = {"cv_any_stay": cv_any_stay, "cv_finalists": cv_finalists, "cv_missing": cv_missing, "cv_targets": cv_targets,
          "confirm": confirm, "explain": explain}

if __name__ == "__main__":
    for stage in sys.argv[1:]:
        print(f"== {stage}")
        STAGES[stage]()
