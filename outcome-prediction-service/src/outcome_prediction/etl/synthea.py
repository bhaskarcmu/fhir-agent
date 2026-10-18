"""Synthea harness (M4): generate a pinned population, build contract rows, score them.

    python -m outcome_prediction.etl.synthea generate        # Synthea v4.0.0, seed 42, 3,000 Arizona adults
    python -m outcome_prediction.etl.synthea rows [--csv DIR] [--year 2023]

Phase-local by design (O11): it downloads its own pinned Synthea release (verified by SHA-256)
into the gitignored data directory and passes every setting on the command line, so the shared
`data/synthea/synthea.properties` and `data/scripts/generate.sh` are untouched.

**Synthea results are never evidence of accuracy** (prd.md §3): the scores are a mechanical
pipeline check — the rows flow through the real model without errors and with plausible values.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path

import pandas as pd
from sklearn.metrics import roc_auc_score

from outcome_prediction.etl.extract import synthea_csv
from outcome_prediction.etl.transform import to_contract
from outcome_prediction.model import FEATURES, LABEL, feature_matrix
from outcome_prediction.settings import data_dir, models_dir, processed_dir, reports_dir

SYNTHEA_VERSION = "4.0.0"
SYNTHEA_URL = f"https://github.com/synthetichealth/synthea/releases/download/v{SYNTHEA_VERSION}/synthea-with-dependencies.jar"
SYNTHEA_SHA256 = "ed43c20ad40ba5c3bc724503a5af032715fe3c491620b766148e7c2361e6ecc1"

# The prototype's population (prototype-baseline.md §6.1), on the pinned release.
RUN = {"seed": 42, "population": 3000, "ages": "18-90", "end_date": "20241231", "state": "Arizona"}
CSV_FILES = ("patients.csv", "encounters.csv", "conditions.csv", "medications.csv", "payer_transitions.csv",
             "payers.csv")


def synthea_dir() -> Path:
    return data_dir() / "raw" / "synthea"


def run_dir() -> Path:
    return synthea_dir() / f"az-{RUN['population']}-s{RUN['seed']}"


def ensure_jar() -> Path:
    jar = synthea_dir() / f"synthea-{SYNTHEA_VERSION}.jar"
    if not jar.exists():
        jar.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(SYNTHEA_URL, jar)
    digest = hashlib.sha256(jar.read_bytes()).hexdigest()
    if digest != SYNTHEA_SHA256:
        raise RuntimeError(f"{jar}: sha256 {digest} != pinned {SYNTHEA_SHA256} — delete it and retry")
    return jar


def generate_command(jar: Path, out: Path, *, fhir: bool = False) -> list[str]:
    """CSV only by default: same seed, same patients with or without the FHIR export (checked in
    M4), so M6 can regenerate this population's FHIR when it needs it."""
    return ["java", "-Xmx6g", "-jar", str(jar), "-s", str(RUN["seed"]), "-cs", str(RUN["seed"]),
            "-p", str(RUN["population"]), "-a", RUN["ages"], "-e", RUN["end_date"],
            f"--exporter.baseDirectory={out}/", "--exporter.csv.export=true",
            f"--exporter.fhir.export={str(fhir).lower()}",
            f"--exporter.csv.included_files={','.join(CSV_FILES)}", RUN["state"]]


def generate(out: Path | None = None) -> Path:
    out = out or run_dir()
    subprocess.run(generate_command(ensure_jar(), out), check=True)
    return out / "csv"


def rows(csv_dir: Path, year: int) -> tuple[pd.DataFrame, dict]:
    """Contract rows for `year`, the sanity checks, and a pipeline-check score with M2's artifact."""
    r = to_contract.training_rows(synthea_csv.read(csv_dir), year)
    summary = {"csv": str(csv_dir), "year": year, "synthea": SYNTHEA_VERSION, "run": RUN,
               "adults": int(len(r)), "label_rate": float(r[LABEL].mean()),
               "problems": to_contract.check(r),
               "means": {c: float(r[c].mean()) for c in FEATURES},
               "median_totexpy1": float(r.totexpy1.median())}
    artifacts = sorted(models_dir().glob("gbm-meps25-v1-*"))
    if artifacts:
        from outcome_prediction.model.artifact import load_artifact
        a = load_artifact(artifacts[-1])
        p = a.model.predict_proba(feature_matrix(r[FEATURES]))[:, 1]
        summary["pipeline_check"] = {
            "artifact": artifacts[-1].name, "mean_predicted": float(p.mean()),
            "auroc": float(roc_auc_score(r[LABEL], p)) if r[LABEL].nunique() == 2 else None,
            "note": "mechanical pipeline check on simulated patients — never evidence of accuracy"}
    return r, summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("generate", help="run the pinned Synthea release (≈ 15 min, ≈ 4 GB of CSV)")
    r = sub.add_parser("rows", help="contract rows + sanity checks + pipeline-check score")
    r.add_argument("--csv", type=Path, default=None)
    r.add_argument("--year", type=int, default=2023)
    args = parser.parse_args(argv)
    if args.cmd == "generate":
        print(generate())
        return
    table, summary = rows(args.csv or run_dir() / "csv", args.year)
    processed_dir().mkdir(parents=True, exist_ok=True)
    reports_dir().mkdir(parents=True, exist_ok=True)
    table.to_csv(processed_dir() / f"synthea_rows_{args.year}.csv", index=False)
    (reports_dir() / f"synthea_{args.year}.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "means"}, indent=2))
    if summary["problems"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
