"""FR-E1–E5: temporal-test evaluation of the validation models on panels 26–27.

Reproduces the prototype's procedure exactly (prototype-baseline.md §4.3), including the
order in which the shared bootstrap generator is consumed — confidence intervals depend on it:
comparison AUROC, comparison AUPRC, then GBM AUROC, GBM AUPRC, each 500 resamples, seed 0.

Usage:
    python -m outcome_prediction.model.evaluate      # writes <data>/reports/metrics.json + model_report.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from outcome_prediction.model import (
    FEATURES, LABEL, TEST_PANELS, TRAIN_PANELS, comparison_matrix, feature_matrix, split_masks,
)
from outcome_prediction.model.fit import fit_validation
from outcome_prediction.settings import processed_dir, reports_dir

BOOTSTRAP_RESAMPLES = 500
TOP_FRACTIONS = (0.05, 0.10, 0.20)
SYNTHEA_NOTE = ("All metrics are on held-out MEPS panels. Synthea results, where they appear "
                "elsewhere, are pipeline checks only and never evidence of accuracy.")


def top_k(y: np.ndarray, p: np.ndarray, fraction: float) -> tuple[float, float]:
    """(PPV, sensitivity) among the `fraction` of people with the highest predicted risk."""
    k = int(len(y) * fraction)
    top = np.argsort(-p)[:k]
    return float(y[top].mean()), float(y[top].sum() / y.sum())


def _bootstrap_ci(rng, metric, y, p) -> list[float]:
    idx = np.arange(len(y))
    values = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        s = rng.choice(idx, len(idx))
        values.append(metric(y[s], p[s]))
    lo, hi = np.percentile(values, [2.5, 97.5])
    return [float(lo), float(hi)]


def _model_metrics(rng, y, p) -> dict:
    out = {
        "auroc": float(roc_auc_score(y, p)),
        "auroc_ci95": _bootstrap_ci(rng, roc_auc_score, y, p),
        "auprc": float(average_precision_score(y, p)),
        "auprc_ci95": _bootstrap_ci(rng, average_precision_score, y, p),
        "brier": float(brier_score_loss(y, p)),
        "mean_predicted": float(p.mean()),
        "top_k": {},
    }
    for fraction in TOP_FRACTIONS:
        ppv, sens = top_k(y, p, fraction)
        out["top_k"][f"{int(fraction * 100)}%"] = {"ppv": ppv, "sensitivity": sens}
    return out


def _subgroup(name: str, mask: np.ndarray, y: np.ndarray, p: np.ndarray) -> dict:
    return {"group": name, "n": int(mask.sum()), "events": int(y[mask].sum()),
            "rate": float(y[mask].mean()), "auroc": float(roc_auc_score(y[mask], p[mask])),
            "mean_predicted": float(p[mask].mean())}


def evaluate(table: pd.DataFrame) -> dict:
    train, test = split_masks(table)
    y = table[LABEL].to_numpy()
    X = feature_matrix(table)
    fitted = fit_validation(table)

    yt = y[test]
    p = fitted.gbm.predict_proba(X[test])[:, 1]
    pb = fitted.comparison.predict_proba(comparison_matrix(table)[test])[:, 1]
    weights = table["longwt"].to_numpy()[test]

    rng = np.random.default_rng(0)
    metrics = {
        "split": {"train_panels": list(TRAIN_PANELS), "test_panels": list(TEST_PANELS),
                  "n_train": int(train.sum()), "n_test": int(test.sum()),
                  "events_test": int(yt.sum()), "rate_test": float(yt.mean())},
        # Order matters: the shared rng is consumed comparison-first, as in the prototype.
        "comparison": _model_metrics(rng, yt, pb),
        "gbm": _model_metrics(rng, yt, p),
    }
    metrics["gbm"]["auroc_survey_weighted"] = float(roc_auc_score(yt, p, sample_weight=weights))
    metrics["brier_null"] = float(brier_score_loss(yt, np.full_like(p, y[train].mean())))

    deciles = pd.DataFrame({"y": yt, "p": p})
    deciles["decile"] = pd.qcut(deciles.p, 10, labels=False) + 1
    metrics["calibration_deciles"] = [
        {"decile": int(d), "n": int(len(g)), "predicted": float(g.p.mean()), "actual": float(g.y.mean())}
        for d, g in deciles.groupby("decile")]

    age = table["agey1x"].to_numpy()[test]
    sex = table["sex"].to_numpy()[test]
    prior = table["ipdisy1"].to_numpy()[test] > 0
    metrics["subgroups"] = [
        _subgroup("age 18-44", age < 45, yt, p),
        _subgroup("age 45-64", (age >= 45) & (age < 65), yt, p),
        _subgroup("age 65+", age >= 65, yt, p),
        _subgroup("male", sex == 1, yt, p),
        _subgroup("female", sex == 2, yt, p),
        _subgroup("no prior stay", ~prior, yt, p),
        _subgroup("prior stay", prior, yt, p),
    ]

    importance = permutation_importance(fitted.gbm, X[test], yt, scoring="roc_auc",
                                        n_repeats=5, random_state=0)
    metrics["permutation_importance"] = dict(sorted(
        zip(FEATURES, map(float, importance.importances_mean)), key=lambda kv: -kv[1]))

    coef = fitted.comparison.coef_[0]
    metrics["comparison_coefficients"] = {
        "intercept": float(fitted.comparison.intercept_[0]),
        "age_per_year": float(coef[0]), "prior_stay": float(coef[1])}
    metrics["note"] = SYNTHEA_NOTE
    return metrics


def _fmt_ci(ci) -> str:
    return f"[{ci[0]:.3f}, {ci[1]:.3f}]"


def render_report(metrics: dict, model_id: str | None = None) -> str:
    s, c, g = metrics["split"], metrics["comparison"], metrics["gbm"]
    lines = [
        "# 12-month hospitalization model — evaluation report", "",
        f"Model: `{model_id}`" if model_id else "Model: validation models (not persisted)", "",
        f"Validation models trained on panels {s['train_panels'][0]}–{s['train_panels'][-1]} "
        f"(n = {s['n_train']:,}), tested on panels {s['test_panels'][0]}–{s['test_panels'][-1]} "
        f"(n = {s['n_test']:,}, {s['events_test']:,} hospitalized, rate {s['rate_test']:.4f}). "
        "The released model is refit on all panels; its own held-out performance is unknown "
        "by construction.", "",
        "| Measure | Comparison model | Gradient boosting |", "|---|---|---|",
        f"| AUROC [95% CI] | {c['auroc']:.3f} {_fmt_ci(c['auroc_ci95'])} | {g['auroc']:.3f} {_fmt_ci(g['auroc_ci95'])} |",
        f"| AUPRC [95% CI] | {c['auprc']:.3f} {_fmt_ci(c['auprc_ci95'])} | {g['auprc']:.3f} {_fmt_ci(g['auprc_ci95'])} |",
        f"| Brier (null {metrics['brier_null']:.4f}) | {c['brier']:.4f} | {g['brier']:.4f} |",
        f"| Mean predicted | {c['mean_predicted']:.4f} | {g['mean_predicted']:.4f} |",
    ]
    for k in c["top_k"]:
        lines.append(f"| Top {k} PPV / sensitivity | {c['top_k'][k]['ppv']:.3f} / "
                     f"{c['top_k'][k]['sensitivity']:.3f} | {g['top_k'][k]['ppv']:.3f} / "
                     f"{g['top_k'][k]['sensitivity']:.3f} |")
    lines += [f"| Survey-weighted AUROC | | {g['auroc_survey_weighted']:.3f} |", "",
              "## Calibration by decile (gradient boosting)", "",
              "| Decile | n | Predicted | Actual |", "|---|---|---|---|"]
    lines += [f"| {d['decile']} | {d['n']:,} | {d['predicted']:.3f} | {d['actual']:.3f} |"
              for d in metrics["calibration_deciles"]]
    lines += ["", "## Subgroups (gradient boosting)", "",
              "| Group | n | Events | Rate | AUROC | Mean predicted |", "|---|---|---|---|---|---|"]
    lines += [f"| {r['group']} | {r['n']:,} | {r['events']:,} | {r['rate']:.3f} | {r['auroc']:.3f} | "
              f"{r['mean_predicted']:.3f} |" for r in metrics["subgroups"]]
    lines += ["", "## Permutation importance (AUROC drop, test panels)", "",
              "| Feature | Mean drop |", "|---|---|"]
    lines += [f"| `{f}` | {v:.4f} |" for f, v in list(metrics["permutation_importance"].items())[:10]]
    cc = metrics["comparison_coefficients"]
    lines += ["", "## Comparison model", "",
              f"Logistic regression: intercept {cc['intercept']:.3f}, age {cc['age_per_year']:.4f} "
              f"per year, any prior stay {cc['prior_stay']:.4f}.", "", f"_{metrics['note']}_", ""]
    return "\n".join(lines)


def write_reports(metrics: dict, out: Path, model_id: str | None = None) -> tuple[Path, Path]:
    out.mkdir(parents=True, exist_ok=True)
    json_path, md_path = out / "metrics.json", out / "model_report.md"
    json_path.write_text(json.dumps(metrics, indent=2) + "\n")
    md_path.write_text(render_report(metrics, model_id))
    return json_path, md_path


def summary_line(name: str, m: dict) -> str:
    return (f"{name}: AUROC {m['auroc']:.3f} {_fmt_ci(m['auroc_ci95'])} AUPRC {m['auprc']:.3f} "
            f"{_fmt_ci(m['auprc_ci95'])} Brier {m['brier']:.4f} meanpred {m['mean_predicted']:.4f}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--table", type=Path, default=None,
                        help="modelling table CSV (default: <data>/processed/meps_hosp12.csv)")
    parser.add_argument("--out", type=Path, default=None, help="report directory (default: <data>/reports)")
    args = parser.parse_args(argv)

    table = pd.read_csv(args.table or processed_dir() / "meps_hosp12.csv")
    metrics = evaluate(table)
    paths = write_reports(metrics, args.out or reports_dir())
    s = metrics["split"]
    print(f"n_train {s['n_train']} n_test {s['n_test']} events_test {s['events_test']} rate {s['rate_test']:.4f}")
    print(summary_line("comparison", metrics["comparison"]))
    print(summary_line("gbm", metrics["gbm"]))
    print(f"weighted AUROC {metrics['gbm']['auroc_survey_weighted']:.3f} Brier null {metrics['brier_null']:.4f}")
    print("wrote", *paths)


if __name__ == "__main__":
    main()
