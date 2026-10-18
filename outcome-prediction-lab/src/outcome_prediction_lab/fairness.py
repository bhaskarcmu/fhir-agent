"""Subgroup fairness for a confirmed model (FR-E6; decisions.md O57).

For each group — race/ethnicity, insurance type, sex, age band — on the test panels:

  discrimination     AUROC with a bootstrap 95% CI (groups with < 20 events: "too few events")
  calibration        mean predicted vs observed rate, and their ratio (1.0 = calibrated;
                     > 1 over-predicts the group, < 1 under-predicts it)
  flagging           share of the group in the overall top 10% of predicted risk
  equal opportunity  share of the group's actual cases that the top-10% flag catches
  precision          share of the group's flagged people who had the outcome

Scoring the test panels is a look at test outcomes, so `run` requires its own ledger entry
(`<config>:fairness`) — recorded, like every other look, before it happens.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

RACE = {1: "Hispanic", 2: "White, non-Hispanic", 3: "Black, non-Hispanic", 4: "Asian, non-Hispanic",
        5: "Other or multiple, non-Hispanic"}
INSURANCE = {1: "Any private insurance", 2: "Public insurance only", 3: "Uninsured"}
SEX = {1: "Men", 2: "Women"}
MIN_EVENTS = 20


def groups(df: pd.DataFrame) -> dict[str, pd.Series]:
    from outcome_prediction_lab.narrate import band
    return {
        "Race / ethnicity": df.racethx.map(RACE),
        "Insurance (year 1)": df.inscovy1.map(INSURANCE),
        "Sex": df.sex.map(SEX),
        "Age band": df.agey1x.map(band),
    }


def _auroc_ci(y, p, n_boot=200, seed=0):
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        s = rng.integers(0, len(y), len(y))
        if y[s].min() != y[s].max():
            vals.append(roc_auc_score(y[s], p[s]))
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return float(lo), float(hi)


def report(y: np.ndarray, p: np.ndarray, df: pd.DataFrame, flag_share: float = 0.10) -> dict:
    y, p = np.asarray(y, float), np.asarray(p, float)
    cutoff = np.quantile(p, 1 - flag_share)
    flagged = p >= cutoff
    out = {"overall": {"n": int(len(y)), "rate": float(y.mean()), "auroc": float(roc_auc_score(y, p)),
                       "flag_cutoff": float(cutoff), "flagged_share": float(flagged.mean()),
                       "share_of_cases_flagged": float(y[flagged].sum() / max(y.sum(), 1))},
           "groups": {}}
    for dim, labels in groups(df).items():
        rows = []
        for g in [g for g in labels.dropna().unique()]:
            m = (labels == g).to_numpy()
            yy, pp, ff = y[m], p[m], flagged[m]
            events = int(yy.sum())
            row = {"group": g, "n": int(m.sum()), "events": events, "rate": float(yy.mean()),
                   "mean_predicted": float(pp.mean()),
                   "calibration_ratio": float(pp.mean() / yy.mean()) if yy.mean() > 0 else None,
                   "flagged_share": float(ff.mean()),
                   "share_of_cases_flagged": float(yy[ff].sum() / events) if events else None,
                   "precision_if_flagged": float(yy[ff].mean()) if ff.any() else None}
            if events >= MIN_EVENTS and events < m.sum():
                row["auroc"] = float(roc_auc_score(yy, pp))
                row["auroc_ci95"] = list(_auroc_ci(yy, pp))
            else:
                row["auroc"], row["note"] = None, f"too few events (< {MIN_EVENTS}) for a stable AUROC"
            rows.append(row)
        out["groups"][dim] = sorted(rows, key=lambda r: -r["n"])
    out["summary"] = summarise(out)
    return out


def summarise(rep: dict) -> dict:
    """The widest gaps across groups with enough events — what a reviewer should look at first."""
    summ = {}
    for dim, rows in rep["groups"].items():
        ok = [r for r in rows if r.get("auroc") is not None]
        if len(ok) < 2:
            continue
        aur = [r["auroc"] for r in ok]
        cal = [r["calibration_ratio"] for r in ok if r["calibration_ratio"]]
        cap = [r["share_of_cases_flagged"] for r in ok if r["share_of_cases_flagged"] is not None]
        summ[dim] = {"auroc_range": [min(aur), max(aur)], "auroc_gap": max(aur) - min(aur),
                     "calibration_ratio_range": [min(cal), max(cal)],
                     "share_of_cases_flagged_range": [min(cap), max(cap)]}
    return summ


def markdown(rep: dict, title: str) -> str:
    o = rep["overall"]
    lines = [f"# Fairness — {title}", "",
             f"Test panels 26–27, n = {o['n']:,}, outcome rate {o['rate']:.1%}, AUROC {o['auroc']:.3f}. "
             f"Flag = top 10% of predicted risk (cutoff {o['flag_cutoff']:.1%}); the flag catches "
             f"{o['share_of_cases_flagged']:.0%} of all cases.", "",
             "Calibration ratio = mean predicted ÷ observed rate (1.00 = calibrated; > 1 over-predicts the "
             "group, < 1 under-predicts it). \"Cases caught\" = share of the group's actual cases inside the flag "
             "(equal opportunity). Differences partly reflect real differences in base rates.", ""]
    for dim, rows in rep["groups"].items():
        lines += [f"## {dim}", "", "| Group | n | Rate | AUROC (95% CI) | Mean predicted | Calibration ratio | Flagged | Cases caught | Precision if flagged |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for r in rows:
            auroc = (f"{r['auroc']:.3f} ({r['auroc_ci95'][0]:.3f}–{r['auroc_ci95'][1]:.3f})" if r.get("auroc") is not None
                     else f"_{r.get('note', '—')}_")
            f = lambda v, pct=True: "—" if v is None else (f"{v:.0%}" if pct else f"{v:.2f}")  # noqa: E731
            lines.append(f"| {r['group']} | {r['n']:,} | {r['rate']:.1%} | {auroc} | {r['mean_predicted']:.1%} | "
                         f"{f(r['calibration_ratio'], False)} | {f(r['flagged_share'])} | {f(r['share_of_cases_flagged'])} | "
                         f"{f(r['precision_if_flagged'])} |")
        lines.append("")
    if rep["summary"]:
        lines += ["## Widest gaps (groups with enough events)", "", "| Dimension | AUROC range | Calibration ratio range | Cases caught range |", "|---|---|---|---|"]
        for dim, s in rep["summary"].items():
            lines.append(f"| {dim} | {s['auroc_range'][0]:.3f}–{s['auroc_range'][1]:.3f} (gap {s['auroc_gap']:.3f}) | "
                         f"{s['calibration_ratio_range'][0]:.2f}–{s['calibration_ratio_range'][1]:.2f} | "
                         f"{s['share_of_cases_flagged_range'][0]:.0%}–{s['share_of_cases_flagged_range'][1]:.0%} |")
    return "\n".join(lines) + "\n"


def run(round_id: str, name: str) -> dict:
    """Score a CONFIRMED model's test-panel predictions by subgroup. Needs the fitted model from
    `confirm` and a ledger entry for `<name>:fairness`."""
    import joblib

    from outcome_prediction_lab import holdout, runs
    from outcome_prediction_lab.evaluate import TEST_PANELS
    holdout.require(round_id, f"{name}:fairness")
    cfg = runs.load_config(runs.config_path(round_id, name))
    path = runs.fitted_path(round_id, name)
    if not path.exists():
        raise runs.ConfigError(f"{name} has no fitted model — confirm it first")
    df = runs.frame_for(cfg)
    test = df[df.panel.isin(TEST_PANELS).to_numpy() & runs._in_population(df, cfg)].reset_index(drop=True)
    hook = runs._scoring_hook(cfg)
    p = joblib.load(path).predict_proba(hook(test) if hook else test)[:, 1]
    rep = report(test[cfg["label"]].to_numpy(), p, test)
    out = runs.round_dir(round_id) / "fairness"
    out.mkdir(exist_ok=True)
    (out / f"{name}.json").write_text(json.dumps(rep, indent=2) + "\n")
    (out / f"{name}.md").write_text(markdown(rep, f"`{name}` ({cfg['label']})"))
    return rep
