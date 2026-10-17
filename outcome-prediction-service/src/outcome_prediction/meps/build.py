"""FR-D2: build the 12-month hospitalization modelling table from MEPS longitudinal panels.

Features come from calendar year 1 of each two-year panel; the label is any inpatient
discharge in calendar year 2 (`IPDISY2 > 0`). Logic reproduces the research prototype
exactly (docs/phase8/prototype-baseline.md §4.1, decisions.md O6) — do not change it here
before the reproduction is recorded; label variants belong to the lab (M10).

Two additions over the prototype, neither of which changes the output table:
  * each diagnosis flag's resolved source column is recorded per panel, because resolving
    by prefix is fragile across years (design.md §11, defect 6);
  * each file's PANEL values are checked against the panel it's meant to hold.

Usage:
    python -m outcome_prediction.meps.build
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from outcome_prediction.meps import LONGITUDINAL_PANELS
from outcome_prediction.meps.download import fetch
from outcome_prediction.settings import processed_dir

CORE = ["DUPERSID", "PANEL", "SEX", "RACETHX", "REGIONY1", "AGEY1X", "INSCOVY1",
        "POVCATY1", "IPDISY1", "IPNGTDY1", "ERTOTY1", "OBTOTVY1", "OPTOTVY1",
        "HHTOTDY1", "RXTOTY1", "TOTEXPY1", "IPDISY2", "LONGWT", "VARSTR", "VARPSU"]

# Self-reported "ever diagnosed" flags. Exact names drift by year (e.g. DIABDXY1_M18),
# so each is resolved by prefix.
DX = ["HIBPDX", "CHDDX", "ANGIDX", "MIDX", "OHRTDX", "STRKDX", "EMPHDX",
      "DIABDX", "ARTHDX", "ASTHDX", "CHOLDX"]

LABEL = "label_hosp_12m"
TABLE = "meps_hosp12.csv"
REPORT = "meps_hosp12_build_report.json"


class PanelMismatch(ValueError):
    """A file's PANEL column doesn't hold the panel it was loaded as."""


def resolve_dx_column(columns: list[str], prefix: str) -> tuple[str, list[str]]:
    """Prototype rule: the first (sorted) column starting with `prefix` and containing 'Y1'.
    Returns the chosen column and every candidate, so ambiguity is visible in the report."""
    candidates = sorted(c for c in columns if c.startswith(prefix) and "Y1" in c)
    if not candidates:
        raise KeyError(f"no year-1 column found for diagnosis prefix {prefix!r}")
    return candidates[0], candidates


def load_panel(dta: Path, panel: int) -> tuple[pd.DataFrame, dict]:
    df = pd.read_stata(dta, convert_categoricals=False)
    found = sorted(set(df["PANEL"].unique().tolist()))
    if found != [panel]:
        raise PanelMismatch(f"{dta.name} holds PANEL values {found}, expected [{panel}]")

    out = df[CORE].copy()
    resolved = {}
    for prefix in DX:
        col, candidates = resolve_dx_column(list(df.columns), prefix)
        out[prefix.lower()] = (df[col] == 1).astype(int)   # MEPS: 1 yes, 2 no, <0 missing
        resolved[prefix.lower()] = {"column": col, "candidates": candidates}
    return out, {"persons_in_file": len(df), "dx_columns": resolved}


def build(panels: dict[int, Path]) -> tuple[pd.DataFrame, dict]:
    """Concatenate panels, keep adults observed in both years, attach the label."""
    frames, report = [], {"panels": {}}
    for panel, dta in sorted(panels.items()):
        frame, info = load_panel(dta, panel)
        frames.append(frame)
        report["panels"][panel] = {"file": dta.name, **info}

    df = pd.concat(frames, ignore_index=True)
    # Adults on 12/31 of year 1, observed in both years (negatives are MEPS missing codes).
    df = df[(df.AGEY1X >= 18) & (df.IPDISY1 >= 0) & (df.IPDISY2 >= 0)].copy()
    df[LABEL] = (df.IPDISY2 > 0).astype(int)
    df = df.drop(columns=["IPDISY2"])
    df.columns = [c.lower() for c in df.columns]

    for panel, info in report["panels"].items():
        rows = df[df.panel == panel]
        info["adults_kept"] = len(rows)
        info["events"] = int(rows[LABEL].sum())
    report["total"] = {"rows": len(df), "columns": df.shape[1],
                       "events": int(df[LABEL].sum()), "rate": round(float(df[LABEL].mean()), 4)}
    return df, report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=None,
                        help="output directory (default: <data>/processed)")
    args = parser.parse_args(argv)

    panels = {panel: fetch(n) for panel, n in LONGITUDINAL_PANELS.items()}
    df, report = build(panels)

    out = args.out or processed_dir()
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / TABLE, index=False)
    (out / REPORT).write_text(json.dumps(report, indent=2) + "\n")

    for panel, info in report["panels"].items():
        print(f"panel {panel}  {info['file']:<9} persons {info['persons_in_file']:>6,}  "
              f"adults {info['adults_kept']:>6,}  events {info['events']:>4}")
    t = report["total"]
    print(f"({t['rows']}, {t['columns']}) events: {t['events']} rate: {t['rate']:.3f}")
    print(f"wrote {out / TABLE} and {out / REPORT}")


if __name__ == "__main__":
    main()
