"""Unit tests for the MEPS dataset build — synthetic panels only."""
from __future__ import annotations

import pytest

from outcome_prediction.meps.build import (
    LABEL, PanelMismatch, build, load_panel, resolve_dx_column,
)
from outcome_prediction.tests.conftest import person

# The 25 features in the contract's column order (design.md §3), preceded by the IDs and
# followed by the survey design variables, flags and label — the prototype's exact layout.
EXPECTED_COLUMNS = [
    "dupersid", "panel", "sex", "racethx", "regiony1", "agey1x", "inscovy1", "povcaty1",
    "ipdisy1", "ipngtdy1", "ertoty1", "obtotvy1", "optotvy1", "hhtotdy1", "rxtoty1",
    "totexpy1", "longwt", "varstr", "varpsu", "hibpdx", "chddx", "angidx", "midx",
    "ohrtdx", "strkdx", "emphdx", "diabdx", "arthdx", "asthdx", "choldx", LABEL,
]


def test_keeps_adults_observed_in_both_years(write_panel):
    dta = write_panel("h1.dta", [
        person("A", 21, age=18),
        person("B", 21, age=17),               # child: excluded
        person("C", 21, ipdis1=-1),            # year-1 count missing: excluded
        person("D", 21, ipdis2=-1),            # year-2 count missing: excluded
        person("E", 21, age=85),
    ])
    df, _ = build({21: dta})
    assert sorted(df.dupersid) == ["A", "E"]


def test_label_is_any_year2_discharge_and_year2_count_is_dropped(write_panel):
    dta = write_panel("h1.dta", [
        person("A", 21, ipdis2=0), person("B", 21, ipdis2=1), person("C", 21, ipdis2=3),
    ])
    df, _ = build({21: dta})
    assert dict(zip(df.dupersid, df[LABEL])) == {"A": 0, "B": 1, "C": 1}
    assert "ipdisy2" not in df.columns


def test_dx_flags_recode_meps_yes_no_and_missing(write_panel):
    dta = write_panel("h1.dta", [
        person("YES", 21, dx={"HIBPDXY1": 1}),
        person("NO", 21, dx={"HIBPDXY1": 2}),
        person("INAPPLICABLE", 21, dx={"HIBPDXY1": -1}),
        person("DONT_KNOW", 21, dx={"HIBPDXY1": -8}),
    ])
    df, _ = build({21: dta})
    assert dict(zip(df.dupersid, df.hibpdx)) == {
        "YES": 1, "NO": 0, "INAPPLICABLE": 0, "DONT_KNOW": 0}


def test_drifted_dx_column_is_resolved_and_reported(write_panel):
    dta = write_panel("h1.dta", [person("A", 23, dx={"DIABDXY1": 1})],
                      rename={"DIABDXY1": "DIABDXY1_M18"})
    df, info = load_panel(dta, 23)
    assert df.diabdx.tolist() == [1]
    assert info["dx_columns"]["diabdx"] == {
        "column": "DIABDXY1_M18", "candidates": ["DIABDXY1_M18"]}


def test_resolve_dx_column_picks_first_sorted_and_reports_all_candidates():
    chosen, candidates = resolve_dx_column(
        ["DIABDXY2", "DIABDXY1_M18", "DIABDXY1", "SEX"], "DIABDX")
    assert chosen == "DIABDXY1"
    assert candidates == ["DIABDXY1", "DIABDXY1_M18"]


def test_resolve_dx_column_raises_when_absent():
    with pytest.raises(KeyError, match="CHDDX"):
        resolve_dx_column(["SEX", "CHDDXY2"], "CHDDX")


def test_wrong_panel_in_file_is_rejected(write_panel):
    dta = write_panel("h1.dta", [person("A", 24)])
    with pytest.raises(PanelMismatch, match=r"\[24\], expected \[21\]"):
        load_panel(dta, 21)


def test_output_layout_and_report(write_panel):
    p21 = write_panel("h1.dta", [person("A", 21, ipdis2=1), person("B", 21, age=10)])
    p22 = write_panel("h2.dta", [person("C", 22), person("D", 22)])
    df, report = build({21: p21, 22: p22})

    assert list(df.columns) == EXPECTED_COLUMNS
    assert report["panels"][21] | {"dx_columns": None} == {
        "file": "h1.dta", "persons_in_file": 2, "adults_kept": 1, "events": 1,
        "dx_columns": None}
    assert report["panels"][22]["adults_kept"] == 2
    assert report["total"] == {"rows": 3, "columns": 31, "events": 1, "rate": 0.3333}
