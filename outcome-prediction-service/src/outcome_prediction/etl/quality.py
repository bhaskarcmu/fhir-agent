"""Data-quality report for contract rows from any source (M6, FR-T6).

Three questions, for rows from Synthea CSV, FHIR, or a customer:

1. **Missing / impossible values** — schema and range checks (`to_contract.check`) and the
   defaults applied (`warnings`, e.g. income not recorded).
2. **Unknown codes** — values the extractor couldn't map: race outside the five MEPS groups,
   states outside the US, encounter classes, payers.
3. **Drift vs MEPS** — how far each feature's distribution is from the data the model learned
   on (training panels 21–25, unweighted). Categorical: population stability index (PSI);
   flags: prevalence ratio; counts: share with any, and mean. A drifting feature means the
   model is being asked about people unlike those it learned from — a reason to recalibrate or
   not to trust it, never a reason to "fix" the data.

    python -m outcome_prediction.etl.quality reference                 # from MEPS -> meps_reference.json
    python -m outcome_prediction.etl.quality csv DIR [--year 2023]     # report on Synthea CSV
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from outcome_prediction.etl.canonical import Canonical
from outcome_prediction.etl.transform import to_contract
from outcome_prediction.model import CATEGORICAL, FEATURES, TRAIN_PANELS

REFERENCE = Path(__file__).with_name("meps_reference.json")
FLAGS = list(to_contract.DX_PATTERNS)
COUNTS = [f for f in FEATURES if f not in CATEGORICAL and f not in FLAGS and f != "agey1x"]
PSI_ALERT, RATIO_ALERT = 0.25, 2.0
KNOWN_RACES = ["white", "black", "asian", "native", "hawaiian", "other"]   # canonical vocabulary


def summarise(rows: pd.DataFrame) -> dict:
    """The distribution summary the report compares — also what `meps_reference.json` holds."""
    out = {"n": int(len(rows)), "categorical": {}, "flags": {}, "counts": {}}
    for c in CATEGORICAL + ["agey1x"]:
        values = rows[c] if c != "agey1x" else pd.cut(rows[c], [17, 29, 44, 64, 74, 85]).astype(str)
        out["categorical"][c] = {str(k): float(v) for k, v in values.value_counts(normalize=True).sort_index().items()}
    for c in FLAGS:
        out["flags"][c] = float(rows[c].mean())
    for c in COUNTS:
        v = rows[c].where(rows[c] >= 0)
        out["counts"][c] = {"mean": float(v.mean()), "any": float((v > 0).mean()),
                            "p50": float(v.quantile(.5)), "p90": float(v.quantile(.9))}
    return out


def build_reference(table: pd.DataFrame) -> dict:
    t = table[table.panel.isin(TRAIN_PANELS)].copy()
    for c in CATEGORICAL:
        t[c] = t[c].clip(lower=0).astype(int)              # the meps25-v1 rule (feature_matrix)
    ref = summarise(t)
    ref["source"] = "MEPS longitudinal panels 21-25, adults, unweighted (outcome-prediction-service M1 table)"
    # A typical adult, for per-patient explanations (FR-M8): the median of each number, the most
    # common category or flag value. Explanations ask "what if this one input were typical?".
    typical = {c: int(t[c].mode().iloc[0]) for c in CATEGORICAL + FLAGS}
    typical.update({c: int(t[c].where(t[c] >= 0).median()) for c in COUNTS + ["agey1x"]})
    ref["typical"] = {c: typical[c] for c in FEATURES}
    return ref


def _ratio(got: float, ref: float) -> float:
    """got / ref, where 0 / 0 is no change (1.0) and anything / 0 is unbounded."""
    if ref == 0:
        return 1.0 if got == 0 else float("inf")
    return got / ref


def _psi(ref: dict, got: dict) -> float:
    keys = set(ref) | set(got)
    eps = 1e-4
    return float(sum((got.get(k, 0) - ref.get(k, 0)) * math.log((got.get(k, 0) + eps) / (ref.get(k, 0) + eps))
                     for k in keys))


def unknown_codes(canon: Canonical) -> dict:
    p, e, cov = canon.person, canon.encounter, canon.coverage
    return {
        "race not recorded or not a known category": int((~p.race.isin(KNOWN_RACES)).sum()),
        "state not a US state (-> region 0)": int((~p.state.isin(to_contract.STATE_REGION)).sum()),
        "sex not male / female": int((~p.sex.isin(["M", "F"])).sum()),
        "encounter class not mapped": int((~e.encounter_class.isin(
            ["ambulatory", "wellness", "urgentcare", "virtual", "outpatient", "emergency", "inpatient", "home",
             "snf", "hospice"])).sum()),
        "coverage with no known payer type": int(cov.ownership.isna().sum()),
        "conditions with no description (no diagnosis flag possible)": int(canon.condition.description.fillna("").eq("").sum()),
    }


def report(rows: pd.DataFrame, warnings: pd.DataFrame, canon: Canonical, source: str,
           reference: dict | None = None) -> dict:
    ref = reference or json.loads(REFERENCE.read_text())
    got = summarise(rows)
    drift = []
    for c, dist in got["categorical"].items():
        psi = _psi(ref["categorical"][c], dist)
        drift.append({"feature": c, "kind": "categorical", "meps": ref["categorical"][c], "source": dist,
                      "statistic": f"PSI {psi:.2f}", "alert": psi > PSI_ALERT})
    for c, rate in got["flags"].items():
        r = ref["flags"][c]
        ratio = _ratio(rate, r)
        drift.append({"feature": c, "kind": "flag", "meps": r, "source": rate, "statistic": f"{ratio:.1f}x",
                      "alert": max(rate, r) >= 0.01 and (ratio > RATIO_ALERT or ratio < 1 / RATIO_ALERT)})
    for c, s in got["counts"].items():
        r = ref["counts"][c]
        ratio = _ratio(s["mean"], r["mean"])
        drift.append({"feature": c, "kind": "count", "meps": r, "source": s, "statistic": f"mean {ratio:.1f}x",
                      "alert": ratio > RATIO_ALERT or ratio < 1 / RATIO_ALERT})
    return {"source": source, "rows": int(len(rows)), "problems": to_contract.check(rows),
            "defaults": {str(k): int(v) for k, v in warnings.warning.value_counts().items()},
            "unknown_codes": unknown_codes(canon), "drift": drift,
            "alerts": [d["feature"] for d in drift if d["alert"]], "reference": ref["source"]}


def markdown(rep: dict) -> str:
    def fmt(v):
        if isinstance(v, dict) and "mean" in v:
            return f"mean {v['mean']:.1f}, any {v['any']:.0%}"
        if isinstance(v, dict):
            return ", ".join(f"{k}: {x:.0%}" for k, x in v.items())
        return f"{v:.1%}"
    lines = [f"# Data-quality report — {rep['source']}", "",
             f"{rep['rows']:,} contract rows. Reference: {rep['reference']}.", "",
             "## Missing and impossible values", "",
             f"Schema and range checks: {'pass' if not rep['problems'] else '; '.join(rep['problems'])}.", ""]
    lines += [f"- Default applied: {k} — {v:,} rows" for k, v in rep["defaults"].items()] or ["- No defaults applied."]
    lines += ["", "## Unknown codes", "", "| Check | Records |", "|---|---|"]
    lines += [f"| {k} | {v:,} |" for k, v in rep["unknown_codes"].items()]
    lines += ["", f"## Drift vs MEPS ({len(rep['alerts'])} alerts)", "",
              "| Feature | MEPS | This source | Statistic | Alert |", "|---|---|---|---|---|"]
    for d in sorted(rep["drift"], key=lambda d: not d["alert"]):
        lines.append(f"| `{d['feature']}` | {fmt(d['meps'])} | {fmt(d['source'])} | {d['statistic']} | {'**yes**' if d['alert'] else ''} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    from outcome_prediction.settings import processed_dir, reports_dir
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("reference")
    c = sub.add_parser("csv")
    c.add_argument("dir")
    c.add_argument("--year", type=int, default=2023)
    f = sub.add_parser("fhir")
    f.add_argument("url")
    f.add_argument("--year", type=int, default=2023)
    args = parser.parse_args(argv)
    if args.cmd == "reference":
        ref = build_reference(pd.read_csv(processed_dir() / "meps_hosp12.csv"))
        REFERENCE.write_text(json.dumps(ref, indent=1) + "\n")
        print(REFERENCE)
        return
    if args.cmd == "csv":
        from outcome_prediction.etl.extract import synthea_csv
        canon, name = synthea_csv.read(args.dir), f"synthea_csv_{args.year}"
        source = f"Synthea CSV ({Path(args.dir).parent.name}), year 1 = {args.year}"
    else:
        from fhir_clinical_client import FHIRClient

        from outcome_prediction.etl.extract import fhir
        client = FHIRClient(args.url)
        ids = [r["id"] for r in client._search_all("Patient", {"_elements": "id"})]
        canon, name = fhir.read(client, ids).canonical, f"fhir_{args.year}"
        source = f"FHIR ({args.url}), year 1 = {args.year}"
    rows, _, warnings = to_contract.scoring_rows(canon, pd.Timestamp(args.year, 12, 31), explain=True)
    rep = report(rows, warnings, canon, source)
    reports_dir().mkdir(parents=True, exist_ok=True)
    (reports_dir() / f"quality_{name}.json").write_text(json.dumps(rep, indent=1, default=str) + "\n")
    (reports_dir() / f"quality_{name}.md").write_text(markdown(rep))
    print(markdown(rep))


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
