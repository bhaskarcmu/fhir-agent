"""Model definitions shared by training, evaluation, the lab (M3) and the service (M7).

Everything here reproduces the research prototype (docs/phase8/prototype-baseline.md §4.2):
change nothing before a new contract version or a promoted round says so (decisions.md O6, O33).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CONTRACT_VERSION = "meps25-v1"
LABEL = "label_hosp_12m"

# Columns of the modelling table that are identifiers, survey design or the label.
NON_FEATURES = ("dupersid", "panel", LABEL, "longwt", "varstr", "varpsu")

# The meps25-v1 feature contract, in model-matrix order (design.md §3). Must match exactly.
FEATURES = [
    "sex", "racethx", "regiony1", "agey1x", "inscovy1", "povcaty1",
    "ipdisy1", "ipngtdy1", "ertoty1", "obtotvy1", "optotvy1", "hhtotdy1", "rxtoty1", "totexpy1",
    "hibpdx", "chddx", "angidx", "midx", "ohrtdx", "strkdx", "emphdx",
    "diabdx", "arthdx", "asthdx", "choldx",
]
CATEGORICAL = ["sex", "racethx", "regiony1", "inscovy1", "povcaty1"]

# Temporal validation split (FR-M3).
TRAIN_PANELS = (21, 22, 23, 24, 25)
TEST_PANELS = (26, 27)

GBM_PARAMS = {"max_iter": 300, "learning_rate": 0.05, "random_state": 0}
COMPARISON_PARAMS = {"max_iter": 1000}


class ContractMismatch(ValueError):
    """The table's feature columns don't match the meps25-v1 contract."""


def feature_matrix(table: pd.DataFrame) -> pd.DataFrame:
    """The 25 contract features in contract order. Categoricals are clipped at 0 (negative
    MEPS missing codes become category 0) and cast to int, as in the prototype."""
    found = [c for c in table.columns if c not in NON_FEATURES]
    if found != FEATURES:
        raise ContractMismatch(f"table features {found} != {CONTRACT_VERSION} contract {FEATURES}")
    X = table[FEATURES].copy()
    for col in CATEGORICAL:
        X[col] = X[col].clip(lower=0).astype(int)
    return X


def comparison_matrix(table: pd.DataFrame) -> np.ndarray:
    """Comparison-model inputs: age, and any year-1 inpatient stay."""
    return np.c_[table["agey1x"], table["ipdisy1"] > 0]


def categorical_indices() -> list[int]:
    return [FEATURES.index(c) for c in CATEGORICAL]


def split_masks(table: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    panel = table["panel"].to_numpy()
    return np.isin(panel, TRAIN_PANELS), np.isin(panel, TEST_PANELS)
