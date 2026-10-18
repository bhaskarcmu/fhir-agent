"""M4: the Synthea CSV harness — canonical tables, contract rows, schema and sanity checks.

Runs on the committed fixture (7 adults from a 20-patient Synthea v4.0.0 run, seed 42, columns
trimmed to what the extractor reads) — no download, no Java.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from outcome_prediction.etl import synthea
from outcome_prediction.etl.canonical import Canonical, CanonicalError
from outcome_prediction.etl.extract import synthea_csv
from outcome_prediction.etl.transform import to_contract
from outcome_prediction.model import FEATURES, LABEL

FIXTURE = Path(__file__).parent / "fixtures" / "synthea_csv"


@pytest.fixture(scope="module")
def canon() -> Canonical:
    return synthea_csv.read(FIXTURE)


def test_extractor_fills_every_canonical_table_with_naive_dates(canon):
    for name, table in canon.tables().items():
        assert len(table), name
        assert table.source_ref.notna().all(), name
    assert canon.coverage.ownership.isin(["PRIVATE", "GOVERNMENT", "NO_INSURANCE"]).all()


def test_canonical_tables_refuse_timezone_aware_dates(canon):
    bad = canon.encounter.assign(start=canon.encounter.start.dt.tz_localize("UTC"))
    with pytest.raises(CanonicalError, match="timezone-naive"):
        Canonical(**{**canon.tables(), "encounter": bad})


def test_training_rows_have_the_contract_schema(canon):
    rows = to_contract.training_rows(canon, 2023)
    assert list(rows.columns) == ["patient_ref", *FEATURES, LABEL]
    assert to_contract.check(rows) == []
    assert len(rows) == 7 and rows[LABEL].sum() == 2          # fixture chosen to include two 2024 stays


def test_check_reports_bad_codes_and_types(canon):
    rows = to_contract.training_rows(canon, 2023)
    rows.loc[0, "sex"] = 7
    rows["totexpy1"] = rows.totexpy1.astype(float)
    problems = to_contract.check(rows)
    assert any("sex" in p for p in problems) and any("totexpy1" in p for p in problems)


def test_population_is_adults_alive_at_the_end_of_year_1(canon):
    person = canon.person.copy()
    person.loc[0, "death_date"] = pd.Timestamp("2023-06-01")
    rows = to_contract.training_rows(Canonical(**{**canon.tables(), "person": person}), 2023)
    assert person.person_id[0] not in set(rows.patient_ref)


def test_coronary_pattern_never_matches_the_imaging_finding():
    """Regression (prototype-baseline.md §6.3): bare `coronary` matched this finding."""
    assert not to_contract.matches("chddx", "Abnormal findings diagnostic imaging heart+coronary circulat (finding)")
    assert to_contract.matches("chddx", "Coronary artery disease (disorder)")
    assert not to_contract.matches("diabdx", "Prediabetes (finding)")


def test_generation_is_pinned_and_phase_local(tmp_path):
    cmd = synthea.generate_command(tmp_path / "synthea.jar", tmp_path / "out")
    assert ["-s", "42"] == cmd[cmd.index("-s"):cmd.index("-s") + 2]
    assert "-c" not in cmd                                   # never the shared synthea.properties
    assert "--exporter.fhir.export=false" in cmd and "Arizona" == cmd[-1]


def test_a_tampered_synthea_jar_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTCOME_PREDICTION_DATA_DIR", str(tmp_path))
    jar = synthea.synthea_dir() / f"synthea-{synthea.SYNTHEA_VERSION}.jar"
    jar.parent.mkdir(parents=True)
    jar.write_bytes(b"not synthea")
    with pytest.raises(RuntimeError, match="sha256"):
        synthea.ensure_jar()


# ── scoring mode and the leakage test (design.md §6, §11; prd.md §9 criterion 5) ───────────────

def _future_variants(canon: Canonical, as_of: pd.Timestamp) -> dict[str, Canonical]:
    """The same patients as known at `as_of`, with everything after `as_of` changed three ways."""
    cut = as_of + pd.Timedelta(days=1)
    t = canon.tables()
    pid = t["person"].person_id.iloc[0]
    later = cut + pd.Timedelta(days=40)

    def add(name, **row):
        frame = t[name]
        extra = pd.DataFrame([{**{c: pd.NA for c in frame.columns}, "person_id": pid, "source_ref": "test", **row}])
        return pd.concat([frame, extra.astype(frame.dtypes.to_dict(), errors="ignore")], ignore_index=True)

    added = {**t,
             "encounter": add("encounter", start=later, stop=later + pd.Timedelta(days=3),
                              encounter_class="inpatient", cost=50_000.0),
             "condition": add("condition", start=later, description="Essential hypertension (disorder)"),
             "coverage": add("coverage", start=later, stop=later + pd.Timedelta(days=300), ownership="PRIVATE"),
             "medication_fill": add("medication_fill", start=later, stop=later + pd.Timedelta(days=90),
                                    code="999", dispenses=3.0, unit_cost=10.0, total_cost=30.0)}

    def rewrite(frame):
        frame = frame.copy()
        running = (frame.start < cut) & (frame.stop.isna() | (frame.stop >= cut))
        frame.loc[running, "stop"] = pd.Timestamp("2027-01-01")      # their end, learned later
        for col in ("dispenses", "total_cost", "cost"):
            if col in frame:
                frame.loc[running, col] = frame.loc[running, col] * 10
        return frame
    rewritten = {**t, **{n: rewrite(t[n]) for n in ("coverage", "encounter", "condition", "medication_fill")}}
    rewritten["person"] = t["person"].assign(death_date=t["person"].death_date.fillna(later))

    removed = {**t, **{n: t[n][t[n].start < cut] for n in ("coverage", "encounter", "condition", "medication_fill")}}
    return {k: Canonical(**v) for k, v in {"added": added, "rewritten": rewritten, "removed": removed}.items()}


@pytest.mark.parametrize("as_of", ["2023-06-30", "2023-12-31", "2022-02-15"])
def test_records_after_as_of_change_no_feature(canon, as_of):
    as_of = pd.Timestamp(as_of)
    base = to_contract.scoring_rows(canon, as_of)
    for name, variant in _future_variants(canon, as_of).items():
        pd.testing.assert_frame_equal(to_contract.scoring_rows(variant, as_of), base, obj=name)


def test_training_features_are_scoring_features_as_of_31_december(canon):
    rows = to_contract.training_rows(canon, 2023)
    pd.testing.assert_frame_equal(rows.drop(columns=LABEL), to_contract.scoring_rows(canon, pd.Timestamp("2023-12-31")))
    for variant in _future_variants(canon, pd.Timestamp("2023-12-31")).values():
        pd.testing.assert_frame_equal(to_contract.training_rows(variant, 2023)[FEATURES], rows[FEATURES])


def test_the_leakage_test_catches_the_prototype(canon):
    """Proof the test tests something: the reproduced prototype (§11.1) fails it."""
    base = to_contract.prototype_training_rows(canon, 2023)[FEATURES]
    rewritten = _future_variants(canon, pd.Timestamp("2023-12-31"))["rewritten"]
    leaked = to_contract.prototype_training_rows(rewritten, 2023)[FEATURES]
    changed = [c for c in FEATURES if not base[c].equals(leaked[c])]
    assert {"rxtoty1", "totexpy1"} <= set(changed)


def test_scoring_rows_have_no_label_and_pass_the_checks(canon):
    rows = to_contract.scoring_rows(canon, pd.Timestamp("2023-06-30"))
    assert LABEL not in rows and to_contract.check(rows) == []


def test_unknown_state_is_region_0_not_south(canon):
    person = canon.person.assign(state=["Ontario", *canon.person.state.iloc[1:]])
    moved = Canonical(**{**canon.tables(), "person": person})
    pid = person.person_id.iloc[0]
    fixed = to_contract.training_rows(moved, 2023).set_index("patient_ref")
    proto = to_contract.prototype_training_rows(moved, 2023).set_index("patient_ref")
    assert fixed.loc[pid, "regiony1"] == 0 and proto.loc[pid, "regiony1"] == 3


def test_one_categorical_rule_for_both_modes():
    rows = pd.DataFrame({c: [-1.0, 2.0, None] for c in to_contract.CATEGORICAL})
    out = to_contract.encode_categoricals(rows)
    assert all(out[c].tolist() == [0, 2, 0] and out[c].dtype == "int64" for c in to_contract.CATEGORICAL)


def test_a_running_prescription_is_estimated_from_its_own_past_rate():
    med = pd.DataFrame({"person_id": ["a", "a"], "code": ["x", "x"],
                        "start": pd.to_datetime(["2022-01-01", "2023-01-01"]),
                        "stop": pd.to_datetime(["2023-01-01", "2024-01-01"]),
                        "dispenses": [4.0, float("nan")]})
    rate = to_contract._fill_rate(med)
    assert rate.iloc[1] == pytest.approx(4 / (365 / to_contract.MONTH_DAYS), rel=1e-6)


def test_a_stay_spanning_as_of_counts_nights_so_far_and_no_final_claim(canon):
    as_of = pd.Timestamp("2023-06-30")
    pid = canon.person.person_id.iloc[0]

    def with_stay(stop, cost):
        stay = pd.DataFrame([{"person_id": pid, "start": pd.Timestamp("2023-06-27 10:00"), "stop": stop,
                              "encounter_class": "inpatient", "cost": cost, "source_ref": "test"}])
        return Canonical(**{**canon.tables(), "encounter": pd.concat([canon.encounter, stay], ignore_index=True)})
    short = to_contract.scoring_rows(with_stay(pd.Timestamp("2023-07-05"), 9_000.0), as_of).set_index("patient_ref")
    long = to_contract.scoring_rows(with_stay(pd.Timestamp("2023-09-30"), 90_000.0), as_of).set_index("patient_ref")
    pd.testing.assert_frame_equal(short, long)
    before = to_contract.scoring_rows(canon, as_of).set_index("patient_ref")
    assert short.loc[pid, "ipdisy1"] == before.loc[pid, "ipdisy1"] + 1
    assert short.loc[pid, "ipngtdy1"] == before.loc[pid, "ipngtdy1"] + 4       # 27 Jun 10:00 → 1 Jul 00:00
    assert short.loc[pid, "totexpy1"] == before.loc[pid, "totexpy1"]          # claim not final yet
