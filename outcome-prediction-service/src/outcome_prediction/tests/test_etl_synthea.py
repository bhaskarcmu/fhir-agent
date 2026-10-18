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
