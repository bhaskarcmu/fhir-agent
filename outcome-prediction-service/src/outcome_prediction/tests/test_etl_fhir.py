"""M6: the FHIR extractor, CSV ↔ FHIR parity (FR-F3), basis (FR-F4) and leakage on the FHIR path.

Offline: the FHIR side replays responses recorded from HAPI v7.2.0 loaded with the same Synthea
v4.0.0 run as the CSV fixture (`fixtures/fhir_recording.json`; how: `record_fhir_fixture.py`).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pandas as pd
import pytest
from fhir_clinical_client import FHIRClient

from outcome_prediction.etl import parity
from outcome_prediction.etl.extract import fhir, synthea_csv
from outcome_prediction.etl.transform import to_contract
from outcome_prediction.model import FEATURES, LABEL

FIXTURES = Path(__file__).parent / "fixtures"
RECORDING = json.loads((FIXTURES / "fhir_recording.json").read_text())
LINK = RECORDING["link"]                                     # FHIR ID -> Synthea (CSV) ID
SINCE = pd.Timestamp(RECORDING["since"]).date()


class Replay(FHIRClient):
    """Answers from the recording; `extra` adds resources to the first page of a search."""

    def __init__(self, extra: dict[str, list[dict]] | None = None):
        super().__init__("http://gateway.test:8000")
        self.extra = extra or {}

    def _request(self, path, method="GET", body=None):
        if path not in RECORDING["responses"]:
            raise AssertionError(f"unrecorded request: {path}")
        response = copy.deepcopy(RECORDING["responses"][path])
        for prefix, resources in self.extra.items():
            if path.startswith(prefix):
                response.setdefault("entry", []).extend({"resource": r} for r in resources)
        return 200, response


@pytest.fixture(scope="module")
def extract() -> fhir.Extract:
    return fhir.read(Replay(), list(LINK), since=SINCE)


@pytest.fixture(scope="module")
def ctx(extract) -> parity.Context:
    return parity.context(synthea_csv.read(FIXTURES / "synthea_csv"), extract, LINK, 2023)


# ── the extractor ────────────────────────────────────────────────────────────────────

def test_extractor_builds_canonical_tables_with_fhir_refs(extract):
    c = extract.canonical
    assert set(c.person.person_id) == set(LINK)
    assert set(c.person.sex) <= {"M", "F"} and set(c.person.state) == {"Arizona"}
    assert c.person.income.isna().all()                                  # FHIR never carries income
    assert c.encounter.source_ref.str.match(r"^Encounter/\w+$").all()
    assert c.condition.source_ref.str.startswith("Condition/").all()
    assert c.medication_fill.source_ref.str.startswith("ExplanationOfBenefit/").all()
    assert set(c.coverage.ownership.dropna()) <= {"PRIVATE", "GOVERNMENT", "NO_INSURANCE"}
    assert (c.encounter.cost > 0).any()


def test_extractor_notes_what_it_had_to_substitute(extract):
    notes = set(extract.notes.note)
    assert {fhir.NOTE_NO_INCOME, fhir.NOTE_FILLS_FROM_CLAIMS, fhir.NOTE_COVERAGE_FROM_CLAIMS} <= notes


@pytest.mark.parametrize("payer, owner", [("Medicare", "GOVERNMENT"), ("Dual Eligible", "GOVERNMENT"),
                                          ("NO_INSURANCE", "NO_INSURANCE"), ("Aetna", "PRIVATE"), (None, None)])
def test_payer_ownership(payer, owner):
    assert fhir.ownership(payer) == owner


def test_dispenses_are_used_when_recorded():
    """Real EHRs often have MedicationDispense; then fills come from it, not from claims."""
    pid = next(iter(LINK))
    dispense = {"resourceType": "MedicationDispense", "id": "d1", "status": "completed",
                "medicationCodeableConcept": {"coding": [{"code": "197361"}]},
                "whenHandedOver": "2023-05-01T10:00:00+00:00"}
    out = fhir.read(Replay({f"/MedicationDispense?patient={pid}": [dispense]}), [pid], since=SINCE)
    assert list(out.canonical.medication_fill.source_ref) == ["MedicationDispense/d1"]
    assert fhir.NOTE_FILLS_FROM_CLAIMS not in set(out.notes.note)


# ── parity (FR-F3) ───────────────────────────────────────────────────────────────────

def test_parity_holds_with_every_difference_explained(ctx):
    result = parity.compare(ctx)
    assert result["holds"], parity.markdown(result)
    assert {"sex", "racethx", "regiony1", "agey1x", "ipdisy1", "ertoty1", *to_contract.FLAGS} <= set(result["identical"])
    assert {d["feature"] for d in result["differences"]} <= set(parity.EXPLAINED)


def test_parity_fails_on_an_unexplained_difference(ctx):
    rows = ctx.fhir_rows.copy()
    rows.iloc[0, rows.columns.get_loc("ertoty1")] += 3                  # nothing explains ER visits
    result = parity.compare(parity.Context(ctx.year, ctx.csv, ctx.csv_rows, rows, ctx.fhir_warnings, ctx.fhir))
    assert not result["holds"] and result["unexplained"] == ["ertoty1"]


def test_parity_rejects_different_people(extract):
    with pytest.raises(ValueError, match="different people"):
        parity.context(synthea_csv.read(FIXTURES / "synthea_csv"), extract, {**LINK, next(iter(LINK)): "someone-else"}, 2023)


# ── leakage on the FHIR path (prd.md §9 criterion 5) ─────────────────────────────────

def test_records_after_as_of_change_no_feature_on_the_fhir_path():
    as_of = pd.Timestamp("2023-06-30")
    pid = next(iter(LINK))
    later = "2023-09-01T10:00:00+00:00"
    extra = {
        f"/Encounter?patient={pid}": [{"resourceType": "Encounter", "id": "late", "status": "finished",
                                       "class": {"code": "IMP"}, "period": {"start": later, "end": "2023-09-09T10:00:00+00:00"}}],
        f"/Condition?patient={pid}": [{"resourceType": "Condition", "id": "late", "onsetDateTime": later,
                                       "code": {"coding": [{"code": "38341003", "display": "Hypertension"}]}}],
        f"/ExplanationOfBenefit?patient={pid}": [{"resourceType": "ExplanationOfBenefit", "id": "late",
                                                  "type": {"coding": [{"code": "pharmacy"}]},
                                                  "item": [{"servicedPeriod": {"start": later, "end": later},
                                                            "productOrService": {"coding": [{"system": "rxnorm", "code": "1"}]}}],
                                                  "insurance": [{"focal": True, "coverage": {"display": "Aetna"}}],
                                                  "total": [{"category": {"coding": [{"code": "submitted"}]},
                                                             "amount": {"value": 9999.0, "currency": "USD"}}]}],
    }
    base = to_contract.scoring_rows(fhir.read(Replay(), list(LINK), since=SINCE).canonical, as_of)
    leaked = to_contract.scoring_rows(fhir.read(Replay(extra), list(LINK), since=SINCE).canonical, as_of)
    pd.testing.assert_frame_equal(leaked, base)
    later_rows = to_contract.scoring_rows(fhir.read(Replay(extra), list(LINK), since=SINCE).canonical,
                                          pd.Timestamp("2023-12-31")).set_index("patient_ref")
    assert later_rows.loc[pid, "ipdisy1"] >= 1 and later_rows.loc[pid, "hibpdx"] == 1   # the records do count later


# ── basis (FR-F4) and warnings ────────────────────────────────────────────────────────

def test_every_feature_value_cites_the_records_behind_it(extract):
    rows, basis, warnings = to_contract.scoring_rows(extract.canonical, pd.Timestamp("2023-12-31"), explain=True)
    recorded = {f"{e['resource']['resourceType']}/{e['resource']['id']}"
                for body in RECORDING["responses"].values() for e in body.get("entry", [])}
    recorded |= {f"Patient/{pid}" for pid in LINK}
    assert set(basis.source_ref) <= recorded                              # every cited record exists
    counts = [c for c in FEATURES if c not in ("sex", "racethx", "regiony1", "agey1x", "povcaty1", "inscovy1")]
    for _, row in rows.iterrows():
        cited = set(basis[basis.patient_ref == row.patient_ref].feature)
        assert {c for c in counts if row[c] > 0} <= cited, row.patient_ref
    assert set(warnings.patient_ref) == set(rows.patient_ref)            # income defaulted for everyone
    assert set(warnings.warning) == {to_contract.WARN_INCOME}
    assert (rows.povcaty1 == to_contract.DEFAULT_POVCAT).all()


def test_missing_income_is_the_documented_default_not_high_income():
    canon = synthea_csv.read(FIXTURES / "synthea_csv")
    person = canon.person.assign(income=float("nan"))
    rows = to_contract.training_rows(type(canon)(**{**canon.tables(), "person": person}), 2023)
    assert (rows.povcaty1 == 4).all()
    assert LABEL in rows


# ── data-quality report (FR-T6) ──────────────────────────────────────────────────────

from outcome_prediction.etl import quality  # noqa: E402


def test_meps_reference_covers_every_feature():
    ref = json.loads(quality.REFERENCE.read_text())
    covered = set(ref["categorical"]) | set(ref["flags"]) | set(ref["counts"])
    assert covered == set(FEATURES) and ref["n"] > 40_000


def test_a_source_identical_to_the_reference_has_no_drift(extract):
    rows, _, warnings = to_contract.scoring_rows(extract.canonical, pd.Timestamp("2023-12-31"), explain=True)
    rep = quality.report(rows, warnings, extract.canonical, "self", reference={**quality.summarise(rows), "source": "self"})
    assert rep["alerts"] == [] and all(d["statistic"] in ("PSI 0.00", "1.0x", "mean 1.0x") or "nan" in d["statistic"]
                                       for d in rep["drift"])


def test_fhir_report_shows_defaults_unknowns_and_drift(extract):
    rows, _, warnings = to_contract.scoring_rows(extract.canonical, pd.Timestamp("2023-12-31"), explain=True)
    rep = quality.report(rows, warnings, extract.canonical, "FHIR fixture")
    assert rep["problems"] == []
    assert rep["defaults"] == {to_contract.WARN_INCOME: len(rows)}
    assert set(rep["unknown_codes"].values()) == {0}
    assert {"regiony1", "chddx"} <= set(rep["alerts"])         # one simulated state; Synthea's coronary rate
    assert "Drift vs MEPS" in quality.markdown(rep)


def test_unknown_codes_are_counted(extract):
    c = extract.canonical
    odd = type(c)(**{**c.tables(), "person": c.person.assign(state="Ontario", race="martian")})
    found = quality.unknown_codes(odd)
    assert found["state not a US state (-> region 0)"] == len(c.person)
    assert found["race not recorded or not a known category"] == len(c.person)
