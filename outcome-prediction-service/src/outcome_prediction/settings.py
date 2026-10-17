"""Filesystem locations shared by every pipeline stage.

All generated data lives under one directory (gitignored). Override it with
OUTCOME_PREDICTION_DATA_DIR, e.g. to share a MEPS cache between worktrees.
"""
from __future__ import annotations

import os
from pathlib import Path

# outcome-prediction-service/ (this file is src/outcome_prediction/settings.py)
SERVICE_ROOT = Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    return Path(os.environ.get("OUTCOME_PREDICTION_DATA_DIR", SERVICE_ROOT / "data"))


def meps_cache_dir() -> Path:
    return data_dir() / "raw" / "meps"


def processed_dir() -> Path:
    return data_dir() / "processed"
