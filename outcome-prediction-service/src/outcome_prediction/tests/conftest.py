"""Shared fixtures. Unit tests use tiny synthetic Stata files shaped like MEPS — no real
MEPS data is needed in CI. Tests that need the real MEPS cache self-skip without it
(decisions.md O17), same pattern as provider-registry-service's DB-backed tests.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from outcome_prediction.meps import LONGITUDINAL_PANELS
from outcome_prediction.settings import meps_cache_dir

DX_Y1 = ["HIBPDXY1", "CHDDXY1", "ANGIDXY1", "MIDXY1", "OHRTDXY1", "STRKDXY1",
         "EMPHDXY1", "DIABDXY1", "ARTHDXY1", "ASTHDXY1", "CHOLDXY1"]


def person(dupersid: str, panel: int, *, age=50, ipdis1=0, ipdis2=0, dx=None) -> dict:
    """One synthetic MEPS person. `dx` maps a DX_Y1 column to its raw MEPS code
    (1 yes, 2 no, negative = missing); unlisted flags default to 2 (no)."""
    row = {
        "DUPERSID": dupersid, "PANEL": panel, "SEX": 1, "RACETHX": 2, "REGIONY1": 3,
        "AGEY1X": age, "INSCOVY1": 1, "POVCATY1": 4, "IPDISY1": ipdis1, "IPNGTDY1": 0,
        "ERTOTY1": 0, "OBTOTVY1": 3, "OPTOTVY1": 0, "HHTOTDY1": 0, "RXTOTY1": 5,
        "TOTEXPY1": 1200, "IPDISY2": ipdis2, "LONGWT": 1000.5, "VARSTR": 1, "VARPSU": 1,
    }
    row.update({col: 2 for col in DX_Y1})
    row.update(dx or {})
    return row


@pytest.fixture
def write_panel(tmp_path):
    """Write synthetic people to a .dta file; optionally rename columns to mimic
    year-to-year drift (e.g. DIABDXY1 -> DIABDXY1_M18)."""
    def _write(name: str, people: list[dict], rename: dict | None = None) -> Path:
        df = pd.DataFrame(people)
        int_cols = [c for c in df.columns if c not in ("DUPERSID", "LONGWT")]
        df[int_cols] = df[int_cols].astype("int32")
        if rename:
            df = df.rename(columns=rename)
        path = tmp_path / name
        df.to_stata(path, write_index=False)
        return path
    return _write


@pytest.fixture(scope="session")
def meps_cache() -> Path:
    """The real MEPS cache, or skip. Never downloads: tests must not hit the network."""
    cache = meps_cache_dir()
    missing = [f"h{n}.dta" for n in LONGITUDINAL_PANELS.values()
               if not (cache / f"h{n}.dta").exists()]
    if missing:
        pytest.skip(f"MEPS cache incomplete at {cache} (missing {', '.join(missing)}); "
                    f"run `python -m outcome_prediction.meps.download` to enable")
    return cache
