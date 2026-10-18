"""FHIR (via `client/clinical`) → canonical tables (M6, FR-F2; design.md §7).

Reading only, like `synthea_csv.py`: every rule here translates what a FHIR server holds into
the canonical vocabulary; feature logic stays in `transform/to_contract.py`. What Synthea
v4.0.0's FHIR does and doesn't carry was checked in M5–M6 (O64, O65); where FHIR can't say what
the CSV says, the rule takes the best knowable substitute and records a note:

| Canonical | From | Substitute when FHIR lacks it |
|---|---|---|
| person | Patient (US Core race / ethnicity, address.state) | income: never in FHIR -> missing (to_contract defaults povcaty1, with a warning) |
| encounter | Encounter class + period; cost = billed total of its claims | office vs hospital outpatient, inpatient vs SNF, home health vs hospice: not separable -> counted as office / inpatient / home health |
| condition | Condition onset / abatement | onset missing -> recorded date |
| medication_fill | MedicationDispense, one row per fill | no dispenses -> one fill per pharmacy claim, priced at its billed amount |
| coverage | Coverage | none recorded -> the payer named on each claim, for that claim's service period |

`source_ref` is the FHIR `Type/id` of the record each row came from — the `basis` of a
RiskAssessment (FR-F4).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

import pandas as pd

from outcome_prediction.etl.canonical import COLUMNS, Canonical

RACE = {"White": "white", "Black or African American": "black", "Asian": "asian",
        "American Indian or Alaska Native": "native", "Native Hawaiian or Other Pacific Islander": "hawaiian"}
SETTING_CLASS = {"ambulatory": "ambulatory", "emergency": "emergency", "inpatient": "inpatient",
                 "home_health": "home", "virtual": "virtual", "short_stay": "outpatient",
                 "observation": "outpatient"}
GOVERNMENT_PAYERS = ("medicare", "medicaid", "dual eligible", "tricare", "veterans", "indian health")
NO_INSURANCE = ("no_insurance", "no insurance", "uninsured", "self-pay", "self pay")
POSTAL = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
          "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
          "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana",
          "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
          "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri",
          "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
          "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
          "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
          "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
          "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming"}

NOTE_FILLS_FROM_CLAIMS = "prescription fills counted from pharmacy claims (no dispense records)"
NOTE_COVERAGE_FROM_CLAIMS = "insurance taken from the payer on each claim (no coverage records)"
NOTE_NO_INCOME = "household income not recorded"


class CareHistoryClient(Protocol):
    """The `client/clinical` methods the extractor uses (FHIRClient implements them)."""
    def get_demographics(self, patient_id): ...
    def get_encounters(self, patient_id, since=None): ...
    def get_condition_history(self, patient_id): ...
    def get_medication_dispenses(self, patient_id): ...
    def get_care_costs(self, patient_id, since=None): ...
    def get_coverage(self, patient_id): ...


@dataclass
class Extract:
    canonical: Canonical
    notes: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=["person_id", "note"]))


def _ts(value) -> pd.Timestamp:
    """Timezone-naive UTC timestamp (canonical convention); NaT for None."""
    if value is None:
        return pd.NaT
    ts = pd.Timestamp(value)
    return ts.tz_convert("UTC").tz_localize(None) if ts.tzinfo else ts


def ownership(payer: str | None) -> str | None:
    if not payer:
        return None
    name = payer.lower()
    if any(n in name for n in NO_INSURANCE):
        return "NO_INSURANCE"
    return "GOVERNMENT" if any(g in name for g in GOVERNMENT_PAYERS) else "PRIVATE"


def _race(names: list[str]) -> str:
    return RACE.get(names[0], "other") if len(names) == 1 else "other"


def read(client: CareHistoryClient, patient_ids: list[str], since: date | None = None) -> Extract:
    """Canonical tables for these patients. `since` limits encounters and claims (server side);
    conditions and demographics are always read in full (diagnosis flags look back forever)."""
    rows = {name: [] for name in COLUMNS}
    notes = []
    for pid in patient_ids:
        d = client.get_demographics(pid)
        rows["person"].append({
            "person_id": pid, "birth_date": _ts(d.birth_date), "death_date": _ts(d.deceased_date),
            "sex": {"male": "M", "female": "F"}.get(d.gender), "race": _race(d.race),
            "ethnicity": "hispanic" if d.ethnicity == "Hispanic or Latino" else "nonhispanic",
            "state": POSTAL.get((d.state or "").upper(), d.state), "income": float("nan"),
            "source_ref": f"Patient/{pid}"})
        notes.append((pid, NOTE_NO_INCOME))

        costs = client.get_care_costs(pid, since=since)
        billed: dict[str, float] = {}
        for c in costs:
            if c.category != "pharmacy":
                for eid in c.encounter_ids:
                    billed[eid] = billed.get(eid, 0.0) + (c.billed or 0.0)
        for e in client.get_encounters(pid, since=since):
            rows["encounter"].append({
                "person_id": pid, "start": _ts(e.start), "stop": _ts(e.end),
                "encounter_class": SETTING_CLASS.get(e.setting, "other"), "cost": billed.get(e.id, 0.0),
                "source_ref": f"Encounter/{e.id}"})

        for c in client.get_condition_history(pid):
            rows["condition"].append({
                "person_id": pid, "start": _ts(c.onset_date or c.recorded_date), "stop": _ts(c.abatement_date),
                "code": c.code, "description": c.display, "source_ref": f"Condition/{c.id}"})

        dispenses = client.get_medication_dispenses(pid)
        if dispenses:
            for x in dispenses:
                at = _ts(x.dispensed_at)
                rows["medication_fill"].append({
                    "person_id": pid, "start": at, "stop": at, "code": x.code, "description": x.display,
                    "dispenses": 1.0, "unit_cost": float("nan"), "total_cost": float("nan"),
                    "source_ref": f"MedicationDispense/{x.id}"})
        else:
            for c in costs:
                if c.category == "pharmacy":
                    at = _ts(c.service_start)
                    rows["medication_fill"].append({
                        "person_id": pid, "start": at, "stop": at,
                        "code": (c.medication_codes or [""])[0], "description": "", "dispenses": 1.0,
                        "unit_cost": c.billed, "total_cost": c.billed,
                        "source_ref": f"ExplanationOfBenefit/{c.id}"})
            notes.append((pid, NOTE_FILLS_FROM_CLAIMS))

        coverage = client.get_coverage(pid)
        if coverage:
            for c in coverage:
                rows["coverage"].append({
                    "person_id": pid, "start": _ts(c.start), "stop": _ts(c.end),
                    "ownership": ownership(c.payer or c.plan_type), "payer": c.payer or c.plan_type,
                    "source_ref": f"Coverage/{c.id}"})
        else:
            for c in costs:
                rows["coverage"].append({
                    "person_id": pid, "start": _ts(c.service_start), "stop": _ts(c.service_end),
                    "ownership": ownership(c.payer), "payer": c.payer,
                    "source_ref": f"ExplanationOfBenefit/{c.id}"})
            notes.append((pid, NOTE_COVERAGE_FROM_CLAIMS))

    tables = {}
    for name, cols in COLUMNS.items():
        t = pd.DataFrame(rows[name], columns=cols)
        for c in ("start", "stop", "birth_date", "death_date"):
            if c in t:
                t[c] = pd.to_datetime(t[c])
        for c in ("cost", "income", "dispenses", "unit_cost", "total_cost"):
            if c in t:
                t[c] = t[c].astype(float)
        tables[name] = t
    return Extract(Canonical(**tables), pd.DataFrame(notes, columns=["person_id", "note"]))
