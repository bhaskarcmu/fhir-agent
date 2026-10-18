"""Canonical tables → `meps25-v1` contract rows (design.md §3, §6).

Two modes, one feature code path (`contract_rows`):

- **scoring** (`scoring_rows`) — features from the 12 months ending at `as_of`, computed only from
  what was knowable at `as_of` (`canonical.as_of_view`); no label.
- **training** (`training_rows`) — the same, with `as_of` = 31 December of year 1, plus the year-2
  label. Only the label reads records after `as_of`.

`prototype_training_rows` keeps the research prototype's mapping **as-is**
(`prototype-baseline.md` §6.3), defects marked `DEFECT`, as the recorded reference (O6) and as the
code the leakage test must catch. It is never used to build rows for a model.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from outcome_prediction.etl.canonical import Canonical, as_of_view
from outcome_prediction.model import CATEGORICAL, FEATURES, LABEL

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


def _guideline(year: int) -> int:
    """The year's guideline; outside the table, the nearest year in it."""
    return POVERTY_GUIDELINE[min(max(year, min(POVERTY_GUIDELINE)), max(POVERTY_GUIDELINE))]


def _poverty_category(income: pd.Series, year: int) -> pd.Series:
    ratio = income / _guideline(year) * 100
    return pd.Series(np.select([ratio < 100, ratio < 125, ratio < 200, ratio < 400], [1, 2, 3, 4], 5),
                     index=income.index)


def _per_person(index: pd.Index, values: pd.Series) -> pd.Series:
    return values.reindex(index, fill_value=0)


def prototype_training_rows(canon: Canonical, year: int) -> pd.DataFrame:
    """The prototype's rows, as-is (reference only): adults alive at the end of `year`, year-2 label."""
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


# ── the fixed mapping: one code path for both modes (design.md §6, §11) ─────────────────────

MONTH_DAYS = 30.4375
UNKNOWN_REGION = 0                      # contract: 0 if the state is unknown or not a US state
# meps25-v1 requires povcaty1, but FHIR never carries income. Default to MEPS's median category
# (4, "middle income") with a warning — not the mode (5, the lowest-risk group), which would
# quietly understate risk (O66). meps-portable-v2 models need no default (O53).
DEFAULT_POVCAT = 4
WARN_INCOME = "povcaty1 defaulted to 4 (middle income): household income not recorded"
WARN_SEX = "sex not recorded as male or female"


def encode_categoricals(rows: pd.DataFrame) -> pd.DataFrame:
    """The one categorical rule for both modes (§11.4): MEPS codes as integers, never negative."""
    for c in CATEGORICAL:
        rows[c] = rows[c].fillna(0).clip(lower=0).astype("int64")
    return rows


def _fill_rate(med: pd.DataFrame) -> pd.Series:
    """Fills per month for each record: the rate of the latest ended record of the same person
    and drug (only ended records — their totals are known), else 1."""
    months = (med.stop - med.start).dt.total_seconds() / 86_400 / MONTH_DAYS
    ended = med[med.dispenses.notna() & (months >= 1)].assign(rate=lambda d: d.dispenses / months[d.index])
    last = ended.sort_values("stop").groupby(["person_id", "code"]).rate.last()
    keys = pd.MultiIndex.from_frame(med[["person_id", "code"]])
    return pd.Series(last.reindex(keys).to_numpy(), index=med.index).fillna(1.0)


def contract_rows(view: Canonical, as_of: pd.Timestamp, explain: bool = False):
    """Features for adults alive at `as_of`, from the 12 months ending at `as_of`.

    `view` must already be `as_of_view(canon, as_of)`: nothing dated after `as_of`, running
    records truncated, values only known at a record's end set to unknown.

    With `explain=True`, returns `(rows, basis, warnings)`: `basis` lists, per patient and
    feature, the `source_ref` of every record that contributed (FR-F4 — a RiskAssessment's
    `basis`); `warnings` lists defaults applied.
    """
    basis = []

    def cite(feature: str, records: pd.DataFrame) -> None:
        if explain and len(records):
            basis.append(pd.DataFrame({"patient_ref": records.person_id.to_numpy(), "feature": feature,
                                       "source_ref": records.source_ref.to_numpy()}))

    hi = pd.Timestamp(as_of).normalize() + pd.Timedelta(days=1)            # exclusive
    lo = hi - pd.DateOffset(years=1)
    p = view.person[view.person.death_date.isna()].copy()                  # alive at as_of
    p["age"] = ((hi - pd.Timedelta(days=1) - p.birth_date).dt.days / 365.25).astype(int)
    p = p[p.age >= 18].set_index("person_id")
    ids = p.index

    out = pd.DataFrame(index=ids)
    people = p.reset_index()
    for f in ("sex", "racethx", "regiony1", "agey1x", "povcaty1"):
        cite(f, people)
    out["sex"] = p.sex.map({"M": 1, "F": 2})
    out["racethx"] = np.where(p.ethnicity == "hispanic", 1, p.race.map(RACE).fillna(5))
    out["regiony1"] = p.state.map(STATE_REGION).fillna(UNKNOWN_REGION)    # §11.3 fixed
    out["agey1x"] = p.age.clip(upper=85)

    cov = view.coverage[view.coverage.person_id.isin(ids)]
    cov = cov[(cov.start < hi) & (cov.stop >= lo)]
    cite("inscovy1", cov)
    owners = cov.groupby("person_id").ownership.agg(set)
    owners = owners.reindex(ids).apply(lambda s: s if isinstance(s, set) else set())
    out["inscovy1"] = owners.map(lambda s: 1 if "PRIVATE" in s else 2 if "GOVERNMENT" in s else 3)
    out["povcaty1"] = _poverty_category(p.income, pd.Timestamp(as_of).year).where(p.income.notna(), DEFAULT_POVCAT)

    enc = view.encounter[view.encounter.person_id.isin(ids)]
    w = enc[enc.start >= lo]
    cls = w.encounter_class
    ip = w[cls == "inpatient"]
    cite("ipdisy1", ip)
    cite("ipngtdy1", ip)
    cite("ertoty1", w[cls == "emergency"])
    cite("obtotvy1", w[cls.isin(OFFICE_CLASSES)])
    cite("optotvy1", w[cls == "outpatient"])
    cite("hhtotdy1", w[cls == "home"])
    out["ipdisy1"] = _per_person(ids, ip.groupby("person_id").size())
    nights = ((ip.stop - ip.start).dt.total_seconds() / 86_400).round()   # a running stay: nights so far
    out["ipngtdy1"] = _per_person(ids, nights.groupby(ip.person_id).sum())
    out["ertoty1"] = _per_person(ids, w[cls == "emergency"].groupby("person_id").size())
    out["obtotvy1"] = _per_person(ids, w[cls.isin(OFFICE_CLASSES)].groupby("person_id").size())
    out["optotvy1"] = _per_person(ids, w[cls == "outpatient"].groupby("person_id").size())
    home = w[cls == "home"]
    out["hhtotdy1"] = _per_person(ids, home.start.dt.normalize().groupby(home.person_id).nunique())

    # Prescriptions (§11.1 fixed). Ended by as_of: the recorded fills, prorated into the window.
    # Still running: the total isn't known yet, so estimate the fills elapsed inside the window at
    # the fill rate of the same person's last ENDED record of the same drug (90-day supplies are
    # common), else one a month; priced at the per-fill cost, which is known at the start.
    med = view.medication_fill[view.medication_fill.person_id.isin(ids)]
    known = med.dispenses.notna()
    frac = _overlap_fraction(med.start, med.stop, lo, hi)
    elapsed = (med.stop.clip(upper=hi) - med.start.clip(lower=lo)).dt.total_seconds().clip(lower=0) / 86_400
    est = np.ceil(elapsed / MONTH_DAYS * _fill_rate(med)).where(elapsed > 0, 0)
    fills = (med.dispenses * frac).where(known, est)
    cost = (med.total_cost * frac).where(known, est * med.unit_cost)
    cite("rxtoty1", med[fills > 0])
    cite("totexpy1", pd.concat([w[w.cost.fillna(0) > 0], med[cost.fillna(0) > 0]]))
    out["rxtoty1"] = _per_person(ids, fills.groupby(med.person_id).sum()).round()
    enc_cost = _per_person(ids, w.cost.fillna(0).groupby(w.person_id).sum())  # a running stay's claim: unknown
    out["totexpy1"] = (enc_cost + _per_person(ids, cost.groupby(med.person_id).sum())).round()

    cond = view.condition[view.condition.person_id.isin(ids)]
    desc = cond.description.str.lower()
    for flag, pattern in DX_PATTERNS.items():
        hits = cond[desc.str.contains(pattern, regex=True)]
        cite(flag, hits)
        out[flag] = ids.isin(hits.person_id.unique()).astype(int)

    warnings = pd.concat([pd.DataFrame({"patient_ref": ids[p.income.isna().to_numpy()], "warning": WARN_INCOME}),
                          pd.DataFrame({"patient_ref": ids[out.sex.isna().to_numpy()], "warning": WARN_SEX})],
                         ignore_index=True)
    out = encode_categoricals(out[FEATURES].copy()).astype("int64")
    out.index.name = "patient_ref"
    rows = out.reset_index()
    if not explain:
        return rows
    cols = ["patient_ref", "feature", "source_ref"]
    return rows, (pd.concat(basis, ignore_index=True) if basis else pd.DataFrame(columns=cols)), warnings


def scoring_rows(canon: Canonical, as_of: pd.Timestamp, explain: bool = False):
    """Scoring mode: features as of `as_of`, no label. Applies the as-of boundary itself, so a
    caller can't pass records from after `as_of` by mistake. `explain` as in `contract_rows`."""
    return contract_rows(as_of_view(canon, as_of), as_of, explain=explain)


def training_rows(canon: Canonical, year: int) -> pd.DataFrame:
    """Training mode: scoring-mode features as of 31 December of `year`, plus the year-2 label —
    the only thing read from after that date."""
    as_of = pd.Timestamp(year, 12, 31)
    rows = scoring_rows(canon, as_of)
    lo, hi = _year(year + 1)
    e = canon.encounter
    stays = e[(e.encounter_class == "inpatient") & (e.start >= lo) & (e.start < hi)].person_id.unique()
    rows[LABEL] = rows.patient_ref.isin(stays).astype("int64")
    return rows


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
