"""Model artifacts: write, verify, load (design.md §8; decisions.md O17, O18).

    models/<model_id>/
      model.joblib        gradient boosting (release model, all panels)
      comparison.joblib   logistic regression comparison model (O18)
      metadata.json       contract, features, data checksums, versions, validation metrics,
                          training-score quantiles (for percentiles)
      MANIFEST.sha256     sha256 of every other file; verified BEFORE anything is deserialised

joblib/pickle loading executes code, so integrity comes first: a missing, changed or unlisted
file means the artifact is refused, not loaded.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np

MODEL = "model.joblib"
COMPARISON = "comparison.joblib"
METADATA = "metadata.json"
MANIFEST = "MANIFEST.sha256"


class ArtifactIntegrityError(RuntimeError):
    """The artifact directory doesn't match its manifest; it must not be loaded."""


@dataclass(frozen=True)
class Artifact:
    path: Path
    model: object
    comparison: object
    metadata: dict


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_artifact(directory: Path, model, comparison, metadata: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=False)   # never overwrite an existing artifact
    joblib.dump(model, directory / MODEL)
    joblib.dump(comparison, directory / COMPARISON)
    (directory / METADATA).write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    lines = [f"{_sha256(directory / name)}  {name}" for name in sorted((MODEL, COMPARISON, METADATA))]
    (directory / MANIFEST).write_text("\n".join(lines) + "\n")
    return directory


def verify_artifact(directory: Path) -> None:
    manifest = directory / MANIFEST
    if not manifest.exists():
        raise ArtifactIntegrityError(f"{directory}: no {MANIFEST}")
    listed = {}
    for line in manifest.read_text().splitlines():
        digest, _, name = line.partition("  ")
        if not digest or not name or "/" in name or name.startswith("."):
            raise ArtifactIntegrityError(f"{directory}: malformed manifest line {line!r}")
        listed[name] = digest

    present = {p.name for p in directory.iterdir() if p.is_file() and p.name != MANIFEST}
    if unlisted := present - listed.keys():
        raise ArtifactIntegrityError(f"{directory}: files not in manifest: {sorted(unlisted)}")
    if missing := {MODEL, COMPARISON, METADATA} - listed.keys():
        raise ArtifactIntegrityError(f"{directory}: manifest omits required {sorted(missing)}")
    for name, digest in listed.items():
        path = directory / name
        if not path.exists():
            raise ArtifactIntegrityError(f"{directory}: {name} listed but missing")
        if _sha256(path) != digest:
            raise ArtifactIntegrityError(f"{directory}: {name} does not match its manifest checksum")


def load_artifact(directory: Path) -> Artifact:
    verify_artifact(directory)
    return Artifact(
        path=directory,
        model=joblib.load(directory / MODEL),
        comparison=joblib.load(directory / COMPARISON),
        metadata=json.loads((directory / METADATA).read_text()),
    )


def score_quantiles(scores: np.ndarray) -> list[float]:
    """101 quantiles (0th..100th) of the training population's scores."""
    return np.quantile(scores, np.linspace(0, 1, 101)).tolist()


def risk_percentile(score: float, quantiles: list[float]) -> int:
    """Percentile (0–100) of `score` within the training population: the highest quantile
    at or below it. Scores outside the training range clamp to 0 or 100."""
    index = np.searchsorted(np.asarray(quantiles), score, side="right") - 1
    return int(np.clip(index, 0, 100))
