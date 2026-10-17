"""FR-M1–M4: evaluate the validation models, refit on all panels, and write the release artifact.

One command produces both the evaluation reports and the artifact, so the metrics stored in
the artifact's metadata always come from the same run and code as the artifact itself.

Usage:
    python -m outcome_prediction.model.train
    # -> models/<model_id>/{model.joblib, comparison.joblib, metadata.json, MANIFEST.sha256}
    # -> <data>/reports/{metrics.json, model_report.md}
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

from outcome_prediction.model import (
    CATEGORICAL, COMPARISON_PARAMS, CONTRACT_VERSION, FEATURES, GBM_PARAMS, LABEL, TEST_PANELS,
    TRAIN_PANELS, feature_matrix,
)
from outcome_prediction.model.artifact import score_quantiles, write_artifact
from outcome_prediction.model.evaluate import evaluate, summary_line, write_reports
from outcome_prediction.model.fit import fit_release
from outcome_prediction.settings import SERVICE_ROOT, meps_cache_dir, models_dir, processed_dir, reports_dir

METRICS_PROVENANCE = (
    "Validation metrics come from models trained on panels 21-25 and tested on panels 26-27. "
    "This artifact's models are refit on all panels; their own held-out performance is unknown "
    "by construction (docs/phase8/design.md §11, defect 5).")


def _git_commit() -> dict:
    def run(*args):
        return subprocess.run(["git", *args], cwd=SERVICE_ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    try:
        return {"commit": run("rev-parse", "HEAD"),
                "dirty": bool(run("status", "--porcelain", "--", "."))}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def _raw_checksums() -> dict:
    path = meps_cache_dir() / "checksums.json"
    if not path.exists():
        return {}
    return {name: entry["sha256"] for name, entry in json.loads(path.read_text()).items()}


def model_id_for(table_sha256: str) -> str:
    """Deterministic: the same training table always yields the same model ID."""
    return f"gbm-{CONTRACT_VERSION}-{table_sha256[:12]}"


def build_metadata(table: pd.DataFrame, table_sha256: str, metrics: dict, quantiles: list[float]) -> dict:
    return {
        "model_id": model_id_for(table_sha256),
        "contract_version": CONTRACT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "outcome": "any inpatient discharge in the 12 months after the feature year",
        "label": LABEL,
        "features": FEATURES,
        "categorical": CATEGORICAL,
        "gbm_params": GBM_PARAMS,
        "comparison_params": COMPARISON_PARAMS,
        "comparison_inputs": ["agey1x", "ipdisy1 > 0"],
        "training": {"panels": sorted(int(p) for p in table["panel"].unique()),
                     "rows": int(len(table)), "events": int(table[LABEL].sum()),
                     "table_sha256": table_sha256, "raw_file_sha256": _raw_checksums()},
        "training_score_quantiles": quantiles,
        "validation_metrics": {
            "provenance": METRICS_PROVENANCE,
            "train_panels": list(TRAIN_PANELS), "test_panels": list(TEST_PANELS),
            "gbm": {k: metrics["gbm"][k] for k in ("auroc", "auroc_ci95", "auprc", "auprc_ci95",
                                                    "brier", "mean_predicted", "auroc_survey_weighted")},
            "comparison": {k: metrics["comparison"][k] for k in ("auroc", "auroc_ci95", "auprc",
                                                                  "auprc_ci95", "brier", "mean_predicted")},
        },
        "versions": {"python": platform.python_version(), "scikit-learn": sklearn.__version__,
                     "pandas": pd.__version__, "numpy": np.__version__, "joblib": joblib.__version__},
        "git": _git_commit(),
    }


def train(table_path: Path, models: Path, reports: Path) -> tuple[Path, dict]:
    table_sha256 = hashlib.sha256(table_path.read_bytes()).hexdigest()
    directory = models / model_id_for(table_sha256)
    if directory.exists():   # checked before any (slow) training
        raise FileExistsError(f"{directory} exists — artifacts are never overwritten; delete it "
                              f"deliberately to rebuild from the same table")
    table = pd.read_csv(table_path)

    metrics = evaluate(table)
    release = fit_release(table)
    quantiles = score_quantiles(release.gbm.predict_proba(feature_matrix(table))[:, 1])
    metadata = build_metadata(table, table_sha256, metrics, quantiles)
    write_artifact(directory, release.gbm, release.comparison, metadata)
    write_reports(metrics, reports, metadata["model_id"])
    return directory, metrics


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--table", type=Path, default=None,
                        help="modelling table CSV (default: <data>/processed/meps_hosp12.csv)")
    args = parser.parse_args(argv)

    directory, metrics = train(args.table or processed_dir() / "meps_hosp12.csv",
                               models_dir(), reports_dir())
    print(f"temporal test AUROC {metrics['gbm']['auroc']:.3f}")
    print(summary_line("comparison", metrics["comparison"]))
    print(summary_line("gbm", metrics["gbm"]))
    print(f"artifact {directory}")
    print(f"reports  {reports_dir()}")
    print("features", FEATURES)


if __name__ == "__main__":
    main()
