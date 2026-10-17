"""Unit tests for the MEPS variable dictionary — a synthetic Stata file with known types.

Also guards the pandas private StataReader attributes the dictionary depends on: if a
pandas upgrade removes them, this fails in CI rather than the dictionary silently breaking.
"""
from __future__ import annotations

import pandas as pd

from outcome_prediction.meps.dictionary import storage_counts, variable_dictionary


def _write(tmp_path):
    df = pd.DataFrame({
        "SEX": pd.Series([1, 2, 2, -8], dtype="int8"),
        "AGEY1X": pd.Series([30, 85, -1, 40], dtype="int16"),
        "TOTEXPY1": pd.Series([0, 120000, 50, 7], dtype="int32"),
        "LONGWT": pd.Series([1.5, 2.5, 3.5, 4.5], dtype="float64"),
        "DUPERSID": ["2790001101", "2790001102", "2790001103", "2790001104"],
    })
    path = tmp_path / "synthetic.dta"
    df.to_stata(
        path, write_index=False,
        variable_labels={"SEX": "SEX", "AGEY1X": "AGE AS OF 12/31/Y1 (EDITED/IMPUTED)"},
        value_labels={"SEX": {1: "1 MALE", 2: "2 FEMALE", -8: "-8 DK"}},
    )
    return path


def test_storage_types_ranges_and_missing_codes(tmp_path):
    d = variable_dictionary(_write(tmp_path)).set_index("variable")

    assert d.loc["SEX", "storage"] == "int8"
    assert d.loc["AGEY1X", "storage"] == "int16"
    assert d.loc["TOTEXPY1", "storage"] == "int32"
    assert d.loc["LONGWT", "storage"] == "float64"
    assert d.loc["DUPERSID", "storage"] == "str10"

    assert d.loc["AGEY1X", "label"] == "AGE AS OF 12/31/Y1 (EDITED/IMPUTED)"
    assert (d.loc["AGEY1X", "min"], d.loc["AGEY1X", "max"]) == (30, 85)
    assert d.loc["AGEY1X", "negative_codes"] == "-1"
    assert d.loc["SEX", "negative_codes"] == "-8"


def test_value_labels_exclude_negative_codes(tmp_path):
    d = variable_dictionary(_write(tmp_path)).set_index("variable")
    assert d.loc["SEX", "value_labels"] == "1=1 MALE; 2=2 FEMALE"


def test_string_lengths_and_storage_counts(tmp_path):
    d = variable_dictionary(_write(tmp_path))
    row = d.set_index("variable").loc["DUPERSID"]
    assert (row["max_len"], row["n_unique"]) == (10, 4)
    assert storage_counts(d) == {"int8": 1, "int16": 1, "int32": 1, "float64": 1, "str10": 1}
