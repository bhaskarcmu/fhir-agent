"""Config-driven research runs — the engine behind the `outcome-prediction-lab` CLI.

A run is one JSON config: what to predict, from which features, with which model. `run` scores it by
leave-one-panel-out cross-validation on the training panels ONLY and writes the result next to
the config. `confirm` is the only path to the test panels, and refuses without a ledger entry.
`card`, `scorecard` and `promote` turn a confirmed run into reviewable documents and, with a
decision ID, a promotion record (decisions.md O31–O39).

    rounds/<round>/configs/<name>.json      the config (committed, written by a person)
    rounds/<round>/runs/<name>.json         CV result (committed)
    rounds/<round>/runs/<name>.confirm.json test-panel result (committed)
    rounds/<round>/cards/<name>.md          model card (committed)
    rounds/<round>/scorecards/<name>.md     target scorecard (committed)
    models/lab-round-<round>/<name>.joblib  fitted model (gitignored binary, O17)
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, LogisticRegression, PoissonRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from outcome_prediction_lab import holdout
from outcome_prediction_lab.evaluate import (
    TEST_PANELS, TRAIN_PANELS, binary_metrics, cost_metrics, count_metrics, cv_predict,
)
from outcome_prediction_lab.features import FEATURE_SETS, honest_frame, make_model

LAB_ROOT = Path(__file__).resolve().parents[2]
ROUNDS = LAB_ROOT / "rounds"
DECISIONS = LAB_ROOT.parent / "docs" / "phase8" / "decisions.md"
# Round 001's CV-chosen gradient-boosting settings (rounds/001-what-and-how/README.md).
TUNED = {"learning_rate": 0.03, "max_leaf_nodes": 15, "min_samples_leaf": 120,
         "l2_regularization": 1.0, "max_iter": 600}
REQUIRED = {"name", "label", "task", "features", "model"}
ALLOWED = REQUIRED | {"text", "params", "monotone", "baseline_inputs", "learning_only", "description",
                      "outcome_phrase"}


class ConfigError(ValueError):
    """A config is malformed — or tries to reach the test panels."""


class PromotionRefused(PermissionError):
    """Promotion prerequisites are missing."""


# ── configs ──────────────────────────────────────────────────────────────────────────

def load_config(path: Path) -> dict:
    cfg = json.loads(Path(path).read_text())
    if missing := REQUIRED - cfg.keys():
        raise ConfigError(f"{path}: missing {sorted(missing)}")
    if unknown := cfg.keys() - ALLOWED:
        # Deliberately strict: a config can't name panels, splits or test sets at all.
        raise ConfigError(f"{path}: unknown keys {sorted(unknown)} — configs choose WHAT to model; "
                          f"the split is fixed (training panels for runs, test panels only via confirm)")
    if cfg["features"] not in FEATURE_SETS:
        raise ConfigError(f"{path}: features must be one of {sorted(FEATURE_SETS)}")
    if cfg["task"] not in ("binary", "count", "cost"):
        raise ConfigError(f"{path}: task must be binary, count or cost")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", cfg["name"]):
        raise ConfigError(f"{path}: name must be lowercase letters, digits, '.' and '-'")
    return cfg


def round_dir(round_id: str) -> Path:
    d = ROUNDS / round_id
    if not d.is_dir():
        raise ConfigError(f"no round directory {d} — create it with its pre-registration README first")
    return d


def config_path(round_id: str, name: str) -> Path:
    return round_dir(round_id) / "configs" / f"{name}.json"


# ── data ─────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def lab_frame() -> pd.DataFrame:
    """The honest-encoded lab table plus `desc_text` (codes as plain words). desc_text is a fixed
    lookup, not learned, so computing it outside the CV folds leaks nothing."""
    from outcome_prediction_lab.data import build_lab_table
    from outcome_prediction_lab.vocabulary import build_vocabulary, describe_tokens
    t = build_lab_table()
    h = honest_frame(t)
    vocab = build_vocabulary()
    h["desc_text"] = h["tokens"].map(lambda s: describe_tokens(s, vocab) if s else "")
    return h


def _factory(cfg: dict):
    cats, nums = FEATURE_SETS[cfg["features"]]
    params = TUNED if cfg.get("params") == "tuned" else (cfg.get("params") or {})
    return lambda: make_model(cfg["model"], cats, nums, text=cfg.get("text"), task=cfg["task"],
                              params=params, monotone=cfg.get("monotone", False))


def _baseline_factory(task: str):
    if task == "binary":
        return lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    if task == "count":
        return lambda: make_pipeline(StandardScaler(), PoissonRegressor(alpha=1e-4, max_iter=1000))
    return lambda: make_pipeline(StandardScaler(), LinearRegression())


def _baseline_X(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    X = df[cols].copy()
    X = X.fillna(X.median())
    if "totexpy1" in cols:
        X["totexpy1"] = np.log1p(X["totexpy1"].clip(lower=0))
    return X


def _targets(df: pd.DataFrame, cfg: dict):
    raw = df[cfg["label"]].to_numpy(float)
    return (np.log1p(raw) if cfg["task"] == "cost" else raw), raw


def _metrics(cfg, y, pred, raw, age):
    if cfg["task"] == "binary":
        return binary_metrics(y, pred, age)
    if cfg["task"] == "count":
        return count_metrics(y, pred)
    return cost_metrics(raw, pred)


def _provenance() -> dict:
    def git(*a):
        try:
            return subprocess.run(["git", *a], cwd=LAB_ROOT, capture_output=True, text=True,
                                  check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None
    from outcome_prediction.meps.manifest import MANIFEST_PATH
    return {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "git_commit": git("rev-parse", "HEAD"),
            "manifest_sha256": hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest()}


# ── run / compare ────────────────────────────────────────────────────────────────────

def run(round_id: str, name: str, frame: pd.DataFrame | None = None) -> dict:
    """Cross-validate one config on the training panels and write runs/<name>.json."""
    cfg = load_config(config_path(round_id, name))
    df = lab_frame() if frame is None else frame
    rows = df.panel.isin(TRAIN_PANELS).to_numpy() & df[cfg["label"]].notna().to_numpy()
    X = df[rows].reset_index(drop=True)
    y, raw = _targets(X, cfg)
    g, age = X.panel.to_numpy(), X.agey1x.to_numpy()
    proba = cfg["task"] == "binary"
    pred = cv_predict(_factory(cfg), X, y, g, proba=proba)
    result = {"config": cfg, "cv": _metrics(cfg, y, pred, raw, age if proba else None),
              "provenance": _provenance()}
    if cfg.get("baseline_inputs"):
        pb = cv_predict(_baseline_factory(cfg["task"]), _baseline_X(X, cfg["baseline_inputs"]), y, g, proba=proba)
        result["cv_baseline"] = _metrics(cfg, y, pb, raw, age if proba else None)
    out = round_dir(round_id) / "runs" / f"{name}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n")
    _mlflow(round_id, name, cfg, result["cv"])
    return result


def _mlflow(round_id, name, cfg, metrics):
    try:
        import mlflow
        mlflow.set_tracking_uri(f"sqlite:///{LAB_ROOT / 'mlflow.db'}")
        mlflow.set_experiment(f"round-{round_id}")
        with mlflow.start_run(run_name=name):
            mlflow.log_params({k: json.dumps(v) if isinstance(v, (list, dict)) else v
                               for k, v in cfg.items() if k != "description"})
            mlflow.log_metrics({k: v for k, v in metrics.items() if isinstance(v, (int, float))})
    except Exception:  # noqa: BLE001 — tracking is optional (O46)
        pass


def compare(round_id: str, metric: str | None = None) -> str:
    """A Markdown table of every run in the round, best first (writes comparison.md)."""
    runs = [json.loads(p.read_text()) for p in sorted((round_dir(round_id) / "runs").glob("*.json"))
            if not p.name.endswith(".confirm.json")]
    if not runs:
        return "_no runs yet_"
    rows = []
    for r in runs:
        cfg, cv = r["config"], r["cv"]
        key = metric or ("auroc" if cfg["task"] == "binary" else "spearman")
        base = r.get("cv_baseline", {}).get(key)
        rows.append((cfg["label"], cv.get(key, float("nan")), cfg["name"], cfg, cv, base, key))
    rows.sort(key=lambda x: (x[0], -x[1]))
    lines = ["| Label | Run | Model | Text | CV metric | Value | Baseline | AUPRC / extra |", "|---|---|---|---|---|---|---|---|"]
    for label, val, nm, cfg, cv, base, key in rows:
        extra = f"{cv['auprc']:.3f}" if "auprc" in cv else (f"top-10% share {cv.get('top10_share_of_events', cv.get('top10_share_of_spend', float('nan'))):.3f}")
        text = ", ".join(cfg["text"]) if isinstance(cfg.get("text"), list) else (cfg.get("text") or "—")
        lines.append(f"| {label} | `{nm}` | {cfg['model']} | {text} | {key} | {val:.4f} | "
                     f"{'' if base is None else f'{base:.4f}'} | {extra} |")
    table = "\n".join(lines) + "\n"
    (round_dir(round_id) / "comparison.md").write_text(f"# Round {round_id} — cross-validated runs\n\n{table}")
    return table


# ── confirm ──────────────────────────────────────────────────────────────────────────

def fitted_path(round_id: str, name: str) -> Path:
    from outcome_prediction.settings import models_dir
    return models_dir() / f"lab-round-{round_id}" / f"{name}.joblib"


def fit_on_training_panels(round_id: str, name: str, frame: pd.DataFrame | None = None):
    cfg = load_config(config_path(round_id, name))
    df = lab_frame() if frame is None else frame
    rows = df.panel.isin(TRAIN_PANELS).to_numpy() & df[cfg["label"]].notna().to_numpy()
    y, _ = _targets(df[rows], cfg)
    return cfg, _factory(cfg)().fit(df[rows], y)


def confirm(round_id: str, name: str, frame: pd.DataFrame | None = None) -> dict:
    """The ONE path to the test panels: refuses unless the ledger already records this look."""
    holdout.require(round_id, name)
    df = lab_frame() if frame is None else frame
    cfg, model = fit_on_training_panels(round_id, name, df)
    test = df.panel.isin(TEST_PANELS).to_numpy() & df[cfg["label"]].notna().to_numpy()
    Xt = df[test]
    y, raw = _targets(Xt, cfg)
    proba = cfg["task"] == "binary"
    pred = model.predict_proba(Xt)[:, 1] if proba else model.predict(Xt)
    result = {"config": cfg, "test": _metrics(cfg, y, pred, raw, Xt.agey1x.to_numpy() if proba else None),
              "provenance": _provenance()}
    if cfg.get("baseline_inputs"):
        train = df.panel.isin(TRAIN_PANELS).to_numpy() & df[cfg["label"]].notna().to_numpy()
        yb, _ = _targets(df[train], cfg)
        b = _baseline_factory(cfg["task"])().fit(_baseline_X(df[train], cfg["baseline_inputs"]), yb)
        Xb = _baseline_X(Xt, cfg["baseline_inputs"])
        pb = b.predict_proba(Xb)[:, 1] if proba else b.predict(Xb)
        result["test_baseline"] = _metrics(cfg, y, pb, raw, Xt.agey1x.to_numpy() if proba else None)
    path = fitted_path(round_id, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)
    result["fitted_model_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (round_dir(round_id) / "runs" / f"{name}.confirm.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


# ── model card, scorecard, promotion ─────────────────────────────────────────────────

def _load(round_id, name, kind):
    p = round_dir(round_id) / "runs" / (f"{name}.confirm.json" if kind == "confirm" else f"{name}.json")
    return json.loads(p.read_text()) if p.exists() else None


def _fmt_metrics(m: dict | None) -> str:
    if not m:
        return "_not available_"
    keys = [k for k in ("auroc", "auprc", "brier", "top10_ppv", "top10_sensitivity", "auroc_65plus",
                        "spearman", "poisson_deviance", "r2_log", "top10_share_of_events",
                        "top10_share_of_spend") if k in m]
    return ", ".join(f"{k} {m[k]:.3f}" for k in keys) + f" (n = {m['n']:,})"


def card(round_id: str, name: str) -> Path:
    """A model card in the spirit of TRIPOD+AI: intended use, data, outcome, inputs, performance
    (CV and, if confirmed, test), limitations — generated from the committed run records."""
    r, c = _load(round_id, name, "run"), _load(round_id, name, "confirm")
    if r is None:
        raise ConfigError(f"no run result for {name} — run it first")
    cfg = r["config"]
    cats, nums = FEATURE_SETS[cfg["features"]]
    text = ", ".join(cfg["text"]) if isinstance(cfg.get("text"), list) else (cfg.get("text") or "none")
    md = f"""# Model card — `{name}` (round {round_id})

{cfg.get("description", "")}

| | |
|---|---|
| **Intended use** | {"LEARNING ONLY — not for promotion (decisions.md O48)" if cfg.get("learning_only") else "Population-level planning aid for primary-care care management; not a diagnosis, not for emergencies"} |
| **Outcome** | `{cfg["label"]}` — {cfg.get("outcome_phrase", "see the round report")} (year 2 of a MEPS two-year panel) |
| **Population** | US civilian non-institutionalised adults (18+) in MEPS panels 21–27, observed in both years |
| **Training data** | Panels 21–25 (2016–2021); evaluation by leave-one-panel-out cross-validation |
| **Test data** | Panels 26–27 (2021–2023), scored once after a holdout-ledger entry |
| **Inputs** | {len(cats)} categorical + {len(nums)} numeric features (`{cfg["features"]}`); text representations: {text} |
| **Model** | `{cfg["model"]}`, task `{cfg["task"]}`, params {"round-001 tuned" if cfg.get("params") == "tuned" else (cfg.get("params") or "defaults")} |
| **Cross-validated performance** | {_fmt_metrics(r["cv"])} |
| **Cross-validated baseline** | {_fmt_metrics(r.get("cv_baseline"))} |
| **Test performance** | {_fmt_metrics(c["test"]) if c else "_not confirmed_"} |
| **Test baseline** | {_fmt_metrics(c.get("test_baseline")) if c else "_not confirmed_"} |
| **Data provenance** | manifest sha256 `{r["provenance"]["manifest_sha256"][:12]}…`, code `{(r["provenance"]["git_commit"] or "unknown")[:12]}` |

## Limitations

- Trained on MEPS **self-reported** survey data; customer records differ (codes, charges vs payments,
  missing income). Recalibrate and validate on customer data before any use (Phase 8b).
- Condition codes are 3-character ICD-10 and only for conditions linked to a year-1 medical event.
- Explanations describe what the model weighed, not causes.
- **Uplift / impactability is not assessable with MEPS** (no intervention data — O37): this model ranks
  risk, not who would benefit from outreach.
- Subgroup fairness by race/ethnicity and insurance is not yet reported on this card.
"""
    out = round_dir(round_id) / "cards" / f"{name}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(md)
    return out


CRITERION_NAMES = {"measurable_in_customer_data": "Measurable in customer data", "actionable": "Actionable",
                   "lead_time": "Lead time", "fhir_representability": "FHIR representability",
                   "regulatory_posture": "Regulatory posture"}
HUMAN_CRITERIA = {
    "measurable_in_customer_data": "Can a customer's own FHIR / claims data observe this outcome (needed to validate and recalibrate)?",
    "actionable": "What would a care manager do differently for a flagged patient?",
    "lead_time": "Is there time to act before the outcome happens?",
    "fhir_representability": "Probability -> RiskAssessment natively; count / cost needs a decision revisiting O3 (O35).",
    "regulatory_posture": "Does this change the FDA clinical-decision-support position?",
}


def scorecard(round_id: str, name: str, criteria: Path | None = None) -> Path:
    """The target scorecard (O36): ML criteria filled from the records; non-ML criteria from a
    person's JSON ({criterion: {"score": ..., "rationale": ...}}) — or marked as still owed."""
    r, c = _load(round_id, name, "run"), _load(round_id, name, "confirm")
    if r is None:
        raise ConfigError(f"no run result for {name}")
    human = json.loads(Path(criteria).read_text()) if criteria else {}
    cv, base = r["cv"], r.get("cv_baseline")
    m = c["test"] if c else cv
    lines = [f"# Target scorecard — `{r['config']['label']}` via `{name}` (round {round_id})", "",
             "| Criterion | Source | Assessment |", "|---|---|---|"]
    if "auroc" in m:
        lines += [f"| Discrimination | {'test' if c else 'CV'} | AUROC {m['auroc']:.3f}, AUPRC {m['auprc']:.3f}"
                  + (f" (baseline AUROC {base['auroc']:.3f}, CV)" if base else "") + " |",
                  f"| Calibration | {'test' if c else 'CV'} | Brier {m['brier']:.4f}; mean predicted {m['mean_pred']:.3f} vs rate {m['rate']:.3f} |",
                  f"| Base rate | data | {m['rate']:.1%} |",
                  f"| Worklist value | {'test' if c else 'CV'} | top 10%: {m['top10_ppv']:.0%} have the outcome; they hold {m['top10_sensitivity']:.0%} of all cases |",
                  f"| Adults 65+ | {'test' if c else 'CV'} | AUROC {m.get('auroc_65plus', float('nan')):.3f} |"]
    else:
        lines += [f"| Ranking | {'test' if c else 'CV'} | Spearman {m['spearman']:.3f} |"]
    for key, question in HUMAN_CRITERIA.items():
        entry = human.get(key)
        cell = (f"**{entry['score']}** — {entry['rationale']}" if entry
                else f"_TO BE SCORED BY A PERSON_ — {question}")
        lines.append(f"| {CRITERION_NAMES[key]} | person | {cell} |")
    lines.append("| Uplift / impactability | — | Not assessable with MEPS (no intervention data — O37) |")
    if r["config"].get("learning_only"):
        lines += ["", "**Learning-only target (O48): not eligible for promotion.**"]
    out = round_dir(round_id) / "scorecards" / f"{name}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    return out


def promote(round_id: str, name: str, decision: str) -> Path:
    """Write the promotion record (O33) — only for a confirmed, carded, non-learning-only run whose
    promotion is backed by an existing decisions.md entry."""
    if not re.fullmatch(r"O\d+", decision):
        raise PromotionRefused(f"decision must look like O49, got {decision!r}")
    if f"| {decision} |" not in DECISIONS.read_text():
        raise PromotionRefused(f"{decision} is not in {DECISIONS} — record the decision first")
    r, c = _load(round_id, name, "run"), _load(round_id, name, "confirm")
    if c is None:
        raise PromotionRefused(f"{name} has no test-panel confirmation")
    if r["config"].get("learning_only"):
        raise PromotionRefused(f"{name} is a learning-only target (O48)")
    card_path = round_dir(round_id) / "cards" / f"{name}.md"
    if not card_path.exists():
        raise PromotionRefused(f"{name} has no model card — run `card` first")
    model = fitted_path(round_id, name)
    if hashlib.sha256(model.read_bytes()).hexdigest() != c["fitted_model_sha256"]:
        raise PromotionRefused(f"{model} does not match the model that was confirmed")
    record = {"round": round_id, "run": name, "decision": decision, "label": r["config"]["label"],
              "model_sha256": c["fitted_model_sha256"],
              "model_card_sha256": hashlib.sha256(card_path.read_bytes()).hexdigest(),
              "promoted_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    out = model.with_suffix(".PROMOTION.json")
    out.write_text(json.dumps(record, indent=2) + "\n")
    return out
