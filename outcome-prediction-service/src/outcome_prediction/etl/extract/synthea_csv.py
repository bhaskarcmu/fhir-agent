"""Synthea CSV export → canonical tables (the reproduction and parity harness, O8).

Reading only: column renames, date parsing (Synthea writes ISO 8601 with a time zone; the
canonical tables are timezone-naive, `prototype-baseline.md` §6.2) and the payer join that turns
a payer ID into its ownership (GOVERNMENT / PRIVATE / NO_INSURANCE). Medications have no row ID
in the CSV, so their `source_ref` is the file and line number.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from outcome_prediction.etl.canonical import Canonical


def _dates(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, utc=True, format="ISO8601").dt.tz_localize(None)


def _read(csv_dir: Path, name: str, columns: list[str]) -> pd.DataFrame:
    return pd.read_csv(csv_dir / f"{name}.csv", usecols=columns, dtype=str, keep_default_na=False,
                       na_values=[""])


def read(csv_dir: Path | str) -> Canonical:
    csv_dir = Path(csv_dir)
    p = _read(csv_dir, "patients", ["Id", "BIRTHDATE", "DEATHDATE", "RACE", "ETHNICITY", "GENDER", "STATE", "INCOME"])
    person = pd.DataFrame({
        "person_id": p.Id, "birth_date": _dates(p.BIRTHDATE), "death_date": _dates(p.DEATHDATE),
        "sex": p.GENDER, "race": p.RACE, "ethnicity": p.ETHNICITY, "state": p.STATE,
        "income": pd.to_numeric(p.INCOME), "source_ref": "patients.csv/" + p.Id})

    payers = _read(csv_dir, "payers", ["Id", "OWNERSHIP"]).set_index("Id").OWNERSHIP
    t = _read(csv_dir, "payer_transitions", ["PATIENT", "START_DATE", "END_DATE", "PAYER"])
    coverage = pd.DataFrame({
        "person_id": t.PATIENT, "start": _dates(t.START_DATE), "stop": _dates(t.END_DATE),
        "ownership": t.PAYER.map(payers), "source_ref": "payer_transitions.csv#" + (t.index + 2).astype(str)})

    e = _read(csv_dir, "encounters", ["Id", "START", "STOP", "PATIENT", "ENCOUNTERCLASS", "TOTAL_CLAIM_COST"])
    encounter = pd.DataFrame({
        "person_id": e.PATIENT, "start": _dates(e.START), "stop": _dates(e.STOP),
        "encounter_class": e.ENCOUNTERCLASS, "cost": pd.to_numeric(e.TOTAL_CLAIM_COST),
        "source_ref": "encounters.csv/" + e.Id})

    c = _read(csv_dir, "conditions", ["START", "STOP", "PATIENT", "CODE", "DESCRIPTION"])
    condition = pd.DataFrame({
        "person_id": c.PATIENT, "start": _dates(c.START), "stop": _dates(c.STOP), "code": c.CODE,
        "description": c.DESCRIPTION, "source_ref": "conditions.csv#" + (c.index + 2).astype(str)})

    m = _read(csv_dir, "medications", ["START", "STOP", "PATIENT", "CODE", "DESCRIPTION", "BASE_COST",
                                       "DISPENSES", "TOTALCOST"])
    medication_fill = pd.DataFrame({
        "person_id": m.PATIENT, "start": _dates(m.START), "stop": _dates(m.STOP), "code": m.CODE,
        "description": m.DESCRIPTION, "dispenses": pd.to_numeric(m.DISPENSES),
        "unit_cost": pd.to_numeric(m.BASE_COST), "total_cost": pd.to_numeric(m.TOTALCOST),
        "source_ref": "medications.csv#" + (m.index + 2).astype(str)})

    return Canonical(person=person, coverage=coverage, encounter=encounter, condition=condition,
                     medication_fill=medication_fill)
