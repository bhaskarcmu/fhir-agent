"""The five canonical tables every source is read into (design.md §7).

Extractors (Synthea CSV now, FHIR in M6) only *read* into these tables; every feature rule lives in
`transform/to_contract.py`, so two sources that describe the same patients give the same contract
rows (FR-F3). Each table carries `source_ref` — the record it came from — so a prediction's
`basis` can point back at real records (FR-F4).

Dates are timezone-naive `datetime64`; a missing end date is `NaT`.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

COLUMNS = {
    "person": ["person_id", "birth_date", "death_date", "sex", "race", "ethnicity", "state", "income",
               "source_ref"],
    "coverage": ["person_id", "start", "stop", "ownership", "payer", "source_ref"],   # payer: e.g. "Medicare"
    "encounter": ["person_id", "start", "stop", "encounter_class", "cost", "source_ref"],
    "condition": ["person_id", "start", "stop", "code", "description", "source_ref"],
    "medication_fill": ["person_id", "start", "stop", "code", "description", "dispenses", "unit_cost",
                        "total_cost", "source_ref"],
}
DATE_COLUMNS = {"person": ["birth_date", "death_date"], "coverage": ["start", "stop"],
                "encounter": ["start", "stop"], "condition": ["start", "stop"],
                "medication_fill": ["start", "stop"]}


class CanonicalError(ValueError):
    """A canonical table is missing columns or has unparsed dates."""


@dataclass(frozen=True)
class Canonical:
    person: pd.DataFrame
    coverage: pd.DataFrame
    encounter: pd.DataFrame
    condition: pd.DataFrame
    medication_fill: pd.DataFrame

    def __post_init__(self):
        for name, cols in COLUMNS.items():
            table = getattr(self, name)
            if missing := [c for c in cols if c not in table.columns]:
                raise CanonicalError(f"{name}: missing columns {missing}")
            for c in DATE_COLUMNS[name]:
                if not pd.api.types.is_datetime64_any_dtype(table[c]) or getattr(table[c].dt, "tz", None):
                    raise CanonicalError(f"{name}.{c} must be timezone-naive datetime64")

    def tables(self) -> dict[str, pd.DataFrame]:
        return {name: getattr(self, name) for name in COLUMNS}


# Values that are only final once a record has ended — unknown while it is still running.
KNOWN_AT_END = {"encounter": ["cost"], "medication_fill": ["dispenses", "total_cost"]}


def as_of_view(canon: Canonical, as_of: pd.Timestamp) -> Canonical:
    """What was knowable at the end of day `as_of` (design.md §6, O10) — the scoring-mode boundary.

    Records starting after `as_of` are dropped. Records spanning it are truncated at `as_of`, and
    the values only known once they end (a prescription's total fills and cost, a stay's claim)
    become unknown — never extrapolated from their eventual end. A death after `as_of` is unknown.
    """
    cut = pd.Timestamp(as_of).normalize() + pd.Timedelta(days=1)          # exclusive
    person = canon.person[canon.person.birth_date < cut].copy()
    person.loc[person.death_date >= cut, "death_date"] = pd.NaT
    out = {"person": person}
    for name in ("coverage", "encounter", "condition", "medication_fill"):
        t = getattr(canon, name)
        t = t[t.start < cut].copy()
        running = t.stop.isna() | (t.stop >= cut)
        t.loc[running, "stop"] = cut
        for col in KNOWN_AT_END.get(name, []):
            t[col] = t[col].astype(float)
            t.loc[running, col] = float("nan")
        out[name] = t
    return Canonical(**out)
