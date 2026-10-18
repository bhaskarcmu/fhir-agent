"""Canonical tables → `meps25-v1` contract rows (design.md §3, §6).

This first version reproduces the research prototype's Synthea mapping **as-is**
(`prototype-baseline.md` §6.3), defects included, so the reproduction has a recorded reference
(O6). The defects are marked `DEFECT` and fixed in the next change (design.md §11).
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from outcome_prediction.etl.canonical import Canonical
from outcome_prediction.model import FEATURES, LABEL

# HHS poverty guideline, 1-person household (Synthea has no household size).
POVERTY_GUIDELINE = {2022: 13_590, 2023: 14_580, 2024: 15_060}

# US Census regions, MEPS codes: 1 Northeast, 2 Midwest, 3 South, 4 West.
REGION = {
    1: ["Connecticut", "Maine", "Massachusetts", "New Hampshire", "Rhode Island", "Vermont", "New Jersey",
        "New York", "Pennsylvania"],
    2: ["Illinois", "Indiana", "Michigan", "Ohio", "Wisconsin", "Iowa", "Kansas", "Minnesota", "Missouri",
        "Nebraska", "North Dakota", "South Dakota"],
    3: ["Delaware", "District of Columbia", "Florida", "Georgia", "Maryland", "North Carolina", "South Carolina",
        "Virginia", "West Virginia", "Alabama", "Kentucky", "Mississippi", "Tennessee", "Arkansas", "Louisiana",
        "Oklahoma", "Texas"],
    4: ["Arizona", "Colorado", "Idaho", "Montana", "Nevada", "New Mexico", "Utah", "Wyoming", "Alaska",
        "California", "Hawaii", "Oregon", "Washington"],
}
STATE_REGION = {state: code for code, states in REGION.items() for state in states}

RACE = {"white": 2, "black": 3, "asian": 4}            # anything else non-Hispanic -> 5

# Description patterns — stand-ins until M13's code lists (prototype-baseline.md §6.3).
DX_PATTERNS = {
    "hibpdx": r"hypertension",
    "chddx": r"ischemic heart disease|coronary artery",
    "angidx": r"angina",
    "midx": r"myocardial infarction",
    "ohrtdx": r"heart failure|atrial fibrillation|cardiomyopathy|valve|arrhythmia",
    "strkdx": r"stroke|cerebrovascular accident|cerebral infarction",
    "emphdx": r"emphysema|chronic obstructive",
    "diabdx": r"(?<!pre)diabetes",
    "arthdx": r"arthritis|osteoarthritis",
    "asthdx": r"asthma",
    "choldx": r"hyperlipidemia|hypercholesterolemia|hypertriglyceridemia",
}
OFFICE_CLASSES = ("ambulatory", "wellness", "urgentcare", "virtual")


def _year(y: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    """[start, end) of calendar year y."""
    return pd.Timestamp(y, 1, 1), pd.Timestamp(y + 1, 1, 1)


def _overlap_fraction(start: pd.Series, stop: pd.Series, lo: pd.Timestamp, hi: pd.Timestamp) -> pd.Series:
    """Share of each [start, stop] record that falls inside [lo, hi)."""
    span = (stop - start).dt.total_seconds()
    inside = (stop.clip(upper=hi) - start.clip(lower=lo)).dt.total_seconds().clip(lower=0)
    point = (start >= lo) & (start < hi)                 # zero-length records count if they start inside
    return pd.Series(np.where(span > 0, inside / span.where(span > 0, 1), point.astype(float)), index=start.index)


def _poverty_category(income: pd.Series, year: int) -> pd.Series:
    ratio = income / POVERTY_GUIDELINE[year] * 100
    return pd.Series(np.select([ratio < 100, ratio < 125, ratio < 200, ratio < 400], [1, 2, 3, 4], 5),
                     index=income.index)


def _per_person(index: pd.Index, values: pd.Series) -> pd.Series:
    return values.reindex(index, fill_value=0)


def training_rows(canon: Canonical, year: int) -> pd.DataFrame:
    """Contract rows for adults alive at the end of `year` (year 1), plus the year-2 label."""
    lo, hi = _year(year)
    end = hi - pd.Timedelta(days=1)                     # 12/31/Y
    p = canon.person
    p = p[(p.birth_date <= end) & (p.death_date.isna() | (p.death_date > end))].copy()
    p["age"] = ((end - p.birth_date).dt.days / 365.25).astype(int)
    p = p[p.age >= 18].set_index("person_id")
    ids = p.index

    out = pd.DataFrame(index=ids)
    out["sex"] = p.sex.map({"M": 1, "F": 2})
    out["racethx"] = np.where(p.ethnicity == "hispanic", 1, p.race.map(RACE).fillna(5))
    out["regiony1"] = p.state.map(STATE_REGION).fillna(3)    # DEFECT (§11.3): unknown state -> South
    out["agey1x"] = p.age.clip(upper=85)

    cov = canon.coverage[canon.coverage.person_id.isin(ids)]
    overlaps = (cov.start < hi) & (cov.stop.isna() | (cov.stop >= lo))
    owners = cov[overlaps].groupby("person_id").ownership.agg(set)
    owners = owners.reindex(ids).apply(lambda s: s if isinstance(s, set) else set())
    out["inscovy1"] = owners.map(lambda s: 1 if "PRIVATE" in s else 2 if "GOVERNMENT" in s else 3)
    out["povcaty1"] = _poverty_category(p.income, year)

    enc = canon.encounter[canon.encounter.person_id.isin(ids)]
    y1 = enc[(enc.start >= lo) & (enc.start < hi)]
    cls = y1.encounter_class
    ip = y1[cls == "inpatient"]
    out["ipdisy1"] = _per_person(ids, ip.groupby("person_id").size())
    nights = ((ip.stop - ip.start).dt.total_seconds() / 86_400).round()
    out["ipngtdy1"] = _per_person(ids, nights.groupby(ip.person_id).sum())
    out["ertoty1"] = _per_person(ids, y1[cls == "emergency"].groupby("person_id").size())
    out["obtotvy1"] = _per_person(ids, y1[cls.isin(OFFICE_CLASSES)].groupby("person_id").size())
    out["optotvy1"] = _per_person(ids, y1[cls == "outpatient"].groupby("person_id").size())
    home = y1[cls == "home"]
    out["hhtotdy1"] = _per_person(ids, home.start.dt.normalize().groupby(home.person_id).nunique())

    med = canon.medication_fill[canon.medication_fill.person_id.isin(ids)].copy()
    # DEFECT (§11.1): an open prescription is assumed to run to the end of YEAR 2, and DISPENSES —
    # a total known only once the prescription ends — is prorated across it. Year-1 fills and
    # spending therefore depend on data from after year 1.
    stop = med.stop.fillna(pd.Timestamp(year + 2, 1, 1) - pd.Timedelta(days=1))
    frac = _overlap_fraction(med.start, stop, lo, hi)
    out["rxtoty1"] = _per_person(ids, (med.dispenses * frac).groupby(med.person_id).sum()).round()
    rx_cost = _per_person(ids, (med.total_cost * frac).groupby(med.person_id).sum())
    out["totexpy1"] = (_per_person(ids, y1.groupby("person_id").cost.sum()) + rx_cost).round()

    cond = canon.condition[canon.condition.person_id.isin(ids) & (canon.condition.start <= end)]
    desc = cond.description.str.lower()
    for flag, pattern in DX_PATTERNS.items():
        hit = cond[desc.str.contains(pattern, regex=True)].person_id.unique()
        out[flag] = ids.isin(hit).astype(int)

    y2 = enc[(enc.start >= hi) & (enc.start < _year(year + 1)[1]) & (enc.encounter_class == "inpatient")]
    out[LABEL] = ids.isin(y2.person_id.unique()).astype(int)

    out = out[FEATURES + [LABEL]].astype("int64")
    out.index.name = "patient_ref"
    return out.reset_index()


# ── schema and sanity checks (prd.md §9, criterion 4 — never exact counts) ───────────────────

ALLOWED = {"sex": {1, 2}, "racethx": {1, 2, 3, 4, 5}, "regiony1": {0, 1, 2, 3, 4}, "inscovy1": {1, 2, 3},
           "povcaty1": {1, 2, 3, 4, 5}}
FLAGS = list(DX_PATTERNS)


def check(rows: pd.DataFrame) -> list[str]:
    """Problems with a frame of contract rows; empty means it passes."""
    problems = []
    got = [c for c in rows.columns if c in FEATURES]
    if got != FEATURES:
        problems.append(f"features {got} != meps25-v1 order {FEATURES}")
        return problems
    for c in FEATURES:
        if not pd.api.types.is_integer_dtype(rows[c]):
            problems.append(f"{c}: dtype {rows[c].dtype}, expected integer")
    for c, allowed in ALLOWED.items():
        if bad := set(rows[c].unique()) - allowed:
            problems.append(f"{c}: codes {sorted(bad)} outside {sorted(allowed)}")
    if not rows.agey1x.between(18, 85).all():
        problems.append("agey1x outside 18–85")
    for c in FLAGS:
        if not rows[c].isin([0, 1]).all():
            problems.append(f"{c}: not 0/1")
    for c in set(FEATURES) - set(ALLOWED) - set(FLAGS) - {"agey1x"}:
        if (rows[c] < 0).any():
            problems.append(f"{c}: negative values")
    return problems


def matches(pattern_flag: str, description: str) -> bool:
    return re.search(DX_PATTERNS[pattern_flag], description.lower()) is not None
