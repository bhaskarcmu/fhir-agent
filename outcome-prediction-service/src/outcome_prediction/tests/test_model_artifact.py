"""Unit tests for artifact integrity (O17): anything that doesn't match the manifest is
refused before deserialisation."""
from __future__ import annotations

import pytest
from sklearn.linear_model import LogisticRegression

from outcome_prediction.model.artifact import (
    COMPARISON, MANIFEST, METADATA, MODEL, ArtifactIntegrityError, load_artifact,
    risk_percentile, write_artifact,
)


@pytest.fixture
def artifact(tmp_path):
    model = LogisticRegression().fit([[0], [1], [2], [3]], [0, 0, 1, 1])
    comparison = LogisticRegression().fit([[0], [3]], [0, 1])
    return write_artifact(tmp_path / "gbm-test", model, comparison, {"model_id": "gbm-test"})


def test_round_trip(artifact):
    loaded = load_artifact(artifact)
    assert loaded.metadata == {"model_id": "gbm-test"}
    assert loaded.model.predict([[3]])[0] == 1
    assert loaded.comparison.predict([[0]])[0] == 0


def test_existing_directory_is_never_overwritten(artifact):
    with pytest.raises(FileExistsError):
        write_artifact(artifact, None, None, {})


@pytest.mark.parametrize("name", [MODEL, COMPARISON, METADATA])
def test_changed_file_is_refused(artifact, name):
    path = artifact / name
    path.write_bytes(path.read_bytes() + b"\x00")
    with pytest.raises(ArtifactIntegrityError, match="does not match"):
        load_artifact(artifact)


def test_missing_file_is_refused(artifact):
    (artifact / COMPARISON).unlink()
    with pytest.raises(ArtifactIntegrityError, match="listed but missing"):
        load_artifact(artifact)


def test_unlisted_file_is_refused(artifact):
    (artifact / "extra.joblib").write_bytes(b"anything")
    with pytest.raises(ArtifactIntegrityError, match="not in manifest"):
        load_artifact(artifact)


def test_missing_manifest_is_refused(artifact):
    (artifact / MANIFEST).unlink()
    with pytest.raises(ArtifactIntegrityError, match="no MANIFEST"):
        load_artifact(artifact)


def test_manifest_cannot_point_outside_the_directory(artifact):
    manifest = artifact / MANIFEST
    manifest.write_text(manifest.read_text() + "0" * 64 + "  ../elsewhere.joblib\n")
    with pytest.raises(ArtifactIntegrityError, match="malformed"):
        load_artifact(artifact)


def test_manifest_must_list_required_files(artifact):
    manifest = artifact / MANIFEST
    kept = [line for line in manifest.read_text().splitlines() if not line.endswith(COMPARISON)]
    manifest.write_text("\n".join(kept) + "\n")
    (artifact / COMPARISON).unlink()
    with pytest.raises(ArtifactIntegrityError, match="omits required"):
        load_artifact(artifact)


@pytest.mark.parametrize("score, expected", [
    (-0.1, 0), (0.0, 0), (0.004, 0), (0.005, 1), (0.5, 50), (0.995, 99), (1.0, 100), (1.7, 100),
])
def test_risk_percentile(score, expected):
    quantiles = [i / 100 - 0.005 if i else 0.0 for i in range(101)]   # 0, .005, .015, ..., .995
    quantiles[-1] = 1.0
    assert risk_percentile(score, quantiles) == expected
