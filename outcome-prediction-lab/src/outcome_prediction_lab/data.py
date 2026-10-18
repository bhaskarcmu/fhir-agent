"""The lab's person-level table: the prototype's 56,360 adults, enriched with everything round 001
explores. One row per (panel, person); year-1 information only in features, year-2 only in labels.

Sources (all pinned in outcome-prediction-service/meps-manifest.json, verified by content):
  longitudinal panels  HC-202 … HC-252    base table, survey items, year-2 outcomes
  medical conditions   HC-190 … HC-241    year-1 ICD-10 (3-char) and CCSR codes
  prescribed medicines HC-188A … HC-239A  year-1 drug classes (Multum)
  hospital stays       HC-197D … HC-248D  year-2 admissions with reason and ER origin
"""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from outcome_prediction.meps import LONGITUDINAL_PANELS
from outcome_prediction.meps.build import build
from outcome_prediction.meps.download import fetch
from outcome_prediction.settings import processed_dir

from outcome_prediction_lab import knowledge

YEAR1 = {21: 2016, 22: 2017, 23: 2018, 24: 2019, 25: 2020, 26: 2021, 27: 2022}
CONDITIONS = {2016: "190", 2017: "199", 2018: "207", 2019: "214", 2020: "222", 2021: "231", 2022: "241"}
PRESCRIBED = {2016: "188a", 2017: "197a", 2018: "206a", 2019: "213a", 2020: "220a", 2021: "229a", 2022: "239a"}
STAYS = {2017: "197d", 2018: "206d", 2019: "213d", 2020: "220d", 2021: "229d", 2022: "239d", 2023: "248d"}

# Year-1 survey items from rounds 1–2 only: round 3 ends in year 2 for almost everyone
# (prototype-baseline.md §3.2). Not available in medical records — "survey-only" (FR-D6).
SURVEY = ["RTHLTH1", "RTHLTH2", "MNHLTH1", "MNHLTH2", "ADLHLP1", "IADLHP1", "ACTLIM1",
          "K6SUM2", "PHQ22", "VPCS2", "VMCS2", "EMPST1", "MARRYY1X", "EDUCYR", "HIDEG"]
# Known, checked gaps — set to missing for that panel instead of failing. Panel 21 (HC-202) used
# the SF-12v2 (PCS2/MCS2), a different instrument from the later VR-12, so it is NOT substituted.
# (Adult BMI, ADBMI2, was dropped altogether: absent from panels 21, 22, 24 and 26.)
KNOWN_GAPS = {21: {"VPCS2", "VMCS2"}}
# Year-1 coverage detail — available in claims, so "portable".
COVERAGE = ["MCREVY1", "MCDEVY1"]
# Year-2 outcomes for the new targets.
OUTCOMES_Y2 = ["ERTOTY2", "TOTEXPY2", "IPNGTDY2", "INSCOVY2", "DIED"]
DX_PREFIXES = ["HIBPDX", "CHDDX", "ANGIDX", "MIDX", "OHRTDX", "STRKDX", "EMPHDX",
               "DIABDX", "ARTHDX", "ASTHDX", "CHOLDX"]
TABLE = "lab_table.joblib"


def read_meps(file_id: str) -> pd.DataFrame:
    path = fetch(file_id)
    if path.suffix == ".ssp":                                   # SAS transport (HC-188A)
        df = pd.read_sas(path, format="xport", encoding="latin1")
        df.columns = [c.upper() for c in df.columns]
    else:
        df = pd.read_stata(path, convert_categoricals=False)
    df["PANEL"] = df["PANEL"].astype(int)
    df["DUPERSID"] = normalize_ids(df["DUPERSID"], df["PANEL"])
    return df


def normalize_ids(ids: pd.Series, panels: pd.Series) -> pd.Series:
    """MEPS person IDs changed format over the years: older files use 8 digits ('90001101'),
    later ones prefix the 2-digit panel ('2290001101') — even for the same person (e.g. Panel 22's
    2017 event files vs its longitudinal file). Normalise everything to the 10-digit form."""
    ids = ids.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    short = ids.str.len() == 8
    return ids.where(~short, panels.astype(int).map("{:02d}".format) + ids)


def _longitudinal_extras(panel: int, file_number: int) -> pd.DataFrame:
    df = read_meps(str(file_number))
    raw_dx = {}
    for prefix in DX_PREFIXES:
        col = sorted(c for c in df.columns if c.startswith(prefix) and "Y1" in c)[0]
        raw_dx[f"{prefix.lower()}_raw"] = df[col]
    wanted = SURVEY + COVERAGE + OUTCOMES_Y2
    missing = sorted(set(wanted) - set(df.columns) - KNOWN_GAPS.get(panel, set()))
    if missing:
        raise KeyError(f"panel {panel}: {missing} not found — check variable names before use")
    for gap in KNOWN_GAPS.get(panel, set()):
        df[gap] = np.nan
    out = pd.concat([df[["DUPERSID", "PANEL"]], df[wanted], pd.DataFrame(raw_dx)], axis=1)
    out.columns = [c.lower() for c in out.columns]
    return out


def _code_documents(panel: int, year: int) -> pd.DataFrame:
    """Per person: a space-separated 'document' of year-1 codes, plus simple counts and the
    knowledge-based scores. Suppressed codes (-15) are counted, never tokenised."""
    cond = read_meps(CONDITIONS[year])
    cond = cond[cond.PANEL == panel]
    icd = cond.ICD10CDX.astype(str).str.strip()
    cond = cond.assign(icd=icd)
    ccsr = pd.concat([cond[["DUPERSID"]].assign(ccsr=cond[c].astype(str).str.strip())
                      for c in ("CCSR1X", "CCSR2X", "CCSR3X")])
    ccsr = ccsr[ccsr.ccsr.str.match(r"^[A-Z]{3}\d{3}$")]

    rx = read_meps(PRESCRIBED[year])
    rx = rx[rx.PANEL == panel]
    rx = rx[pd.to_numeric(rx.TC1S1_1, errors="coerce") > 0].assign(
        rxc=lambda d: "rx" + pd.to_numeric(d.TC1S1_1).astype(int).astype(str))

    valid_icd = cond[cond.icd.str.match(r"^[A-Z]\d{2}$")]
    icd_sets = valid_icd.groupby("DUPERSID").icd.apply(set)
    know = pd.DataFrame.from_dict({pid: knowledge.scores(codes) for pid, codes in icd_sets.items()},
                                  orient="index")
    out = pd.DataFrame(index=pd.Index(sorted(set(cond.DUPERSID) | set(rx.DUPERSID)), name="dupersid"))
    out = out.join(know)
    out["n_icd"] = icd_sets.apply(len)
    out["n_ccsr_systems"] = ccsr.assign(sys=ccsr.ccsr.str[:3]).groupby("DUPERSID").sys.nunique()

    tokens = pd.concat([
        valid_icd.groupby("DUPERSID").icd.apply(lambda s: " ".join("icd" + c for c in sorted(set(s)))),
        ccsr.groupby("DUPERSID").ccsr.apply(lambda s: " ".join(sorted(set(s)))),
        rx.groupby("DUPERSID").rxc.apply(lambda s: " ".join(s)),          # repeats = fills: real TF
    ], axis=1).fillna("").agg(" ".join, axis=1).str.split().str.join(" ")
    out["tokens"] = tokens
    out["n_rx_classes"] = rx.groupby("DUPERSID").rxc.nunique()
    out["n_suppressed_codes"] = cond[cond.icd == "-15"].groupby("DUPERSID").size()
    out = out.reindex(columns=["tokens", "hfrs", "charlson_approx", "elixhauser_vw_approx",
                               "elixhauser_count_approx", "n_icd", "n_ccsr_systems", "n_rx_classes",
                               "n_suppressed_codes"])
    return out.reset_index().assign(panel=panel)


def _stay_labels(panel: int, year2: int) -> pd.DataFrame:
    """Year-2 ADMISSIONS (stay began in year 2 — unlike the prototype's label, which counts
    year-2 discharges and so includes stays admitted in year 1)."""
    s = read_meps(STAYS[year2])
    s = s[(s.PANEL == panel) & (pd.to_numeric(s.IPBEGYR, errors="coerce") == year2)]
    obstetric = s.RSNINHOS.isin([4, 5, 6])
    g = pd.DataFrame({
        "admit_y2": s.groupby("DUPERSID").size() > 0,
        "admit_nonobstetric_y2": s[~obstetric].groupby("DUPERSID").size() > 0,
        "admit_via_er_y2": s[s.EMERROOM == 1].groupby("DUPERSID").size() > 0,
    }).fillna(False)
    return g.reset_index().rename(columns={"DUPERSID": "dupersid"}).assign(panel=panel)


def build_lab_table(cache: Path | None = None, rebuild: bool = False) -> pd.DataFrame:
    path = (cache or processed_dir()) / TABLE
    if path.exists() and not rebuild:
        return joblib.load(path)

    base, _ = build({p: fetch(n) for p, n in LONGITUDINAL_PANELS.items()})
    base["dupersid"] = normalize_ids(base["dupersid"], base["panel"])
    parts_extra, parts_codes, parts_stays = [], [], []
    for panel, n in LONGITUDINAL_PANELS.items():
        parts_extra.append(_longitudinal_extras(panel, n))
        parts_codes.append(_code_documents(panel, YEAR1[panel]))
        parts_stays.append(_stay_labels(panel, YEAR1[panel] + 1))
    t = (base.merge(pd.concat(parts_extra), on=["dupersid", "panel"], how="left", validate="1:1")
             .merge(pd.concat(parts_codes), on=["dupersid", "panel"], how="left", validate="1:1")
             .merge(pd.concat(parts_stays), on=["dupersid", "panel"], how="left", validate="1:1"))

    fill0 = ["hfrs", "charlson_approx", "elixhauser_vw_approx", "elixhauser_count_approx", "n_icd",
             "n_ccsr_systems", "n_rx_classes", "n_suppressed_codes"]
    t[fill0] = t[fill0].fillna(0)
    t["tokens"] = t["tokens"].fillna("")
    for c in ("admit_y2", "admit_nonobstetric_y2", "admit_via_er_y2"):
        t[c] = t[c].fillna(False).astype(int)
    t = add_targets(t)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(t, path)
    return t


def add_targets(t: pd.DataFrame) -> pd.DataFrame:
    """Year-2 targets beyond the prototype's. High cost is ranked WITHIN each panel (top decile of
    year-2 spending), so inflation and COVID-era shifts between panels don't move the threshold."""
    t = t.copy()
    t["any_ed_y2"] = (t.ertoty2 > 0).astype(int)
    t["ed_visits_y2"] = t.ertoty2.clip(lower=0)
    t["cost_y2"] = t.totexpy2.clip(lower=0)
    t["high_cost_y2"] = (t.groupby("panel").cost_y2.rank(pct=True) > 0.9).astype(int)
    t["died_y2"] = (t.died == 1).astype(int)
    insured = t.inscovy1.isin([1, 2])
    t["lost_insurance_y2"] = np.where(insured, (t.inscovy2 == 3).astype(float), np.nan)
    return t
