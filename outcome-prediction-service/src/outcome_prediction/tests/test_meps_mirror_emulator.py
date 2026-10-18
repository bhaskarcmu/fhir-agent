"""gs:// mirrors against a real GCS emulator (fake-gcs-server — decisions.md O43): the actual
google-cloud-storage client, HTTP and the generation precondition, end to end — first with
synthetic bytes, then with the real MEPS originals in the populated emulator bucket.

The emulator comes from the `gcs_emulator` fixture (conftest): a running one if
STORAGE_EMULATOR_HOST answers, otherwise a container started for the session. Nothing to set
up by hand, locally or in CI (O44).
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest

storage = pytest.importorskip("google.cloud.storage", reason="needs the [gcs] extra")

from outcome_prediction.meps import download  # noqa: E402
from outcome_prediction.meps.download import fetch  # noqa: E402
from outcome_prediction.meps.manifest import load_manifest  # noqa: E402
from outcome_prediction.meps.mirror import (  # noqa: E402
    MirrorError, from_uri, object_key, push, put, verify,
)
from outcome_prediction.tests.test_meps_provenance import (  # noqa: E402,F401 — `ahrq` is a fixture
    N, ORIGINAL_DTA, ORIGINAL_ZIP, _manifest, _sha, ahrq,
)
from outcome_prediction.tests.conftest import GCS_EMULATOR_IMAGE  # noqa: E402


@pytest.fixture(scope="module")
def bucket(gcs_emulator):
    """A fresh, uniquely named bucket per test module — synthetic tests never touch the shared
    MEPS bucket."""
    name = f"phase8-test-{uuid.uuid4().hex[:12]}"
    storage.Client(project="local").create_bucket(name)
    return name


def test_write_once_is_enforced_by_the_server(bucket):
    m = from_uri(f"gs://{bucket}/write-once")
    key = object_key(_sha(b"a"), "f.zip")
    assert put(m, key, b"a") is True
    assert put(m, key, b"a") is False          # server returned 412; content identical
    with pytest.raises(MirrorError, match="refusing to overwrite"):
        put(m, key, b"b")
    assert m.get(key) == b"a"


def test_push_then_verify_round_trip(bucket, tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / f"h{N}dta.zip").write_bytes(ORIGINAL_ZIP)
    (archive / f"h{N}doc.shtml").write_bytes(b"doc")
    m = from_uri(f"gs://{bucket}/round-trip")

    assert all(line.startswith("uploaded") for line in push(_manifest(), archive, [m]))
    assert verify(_manifest(), [m]) == []
    assert all(line.startswith("present") for line in push(_manifest(), archive, [m]))


def test_verify_reports_objects_missing_from_the_bucket(bucket):
    problems = verify(_manifest(), [from_uri(f"gs://{bucket}/empty-prefix")])
    assert len(problems) == 2 and all("unreadable" in p for p in problems)


def test_fetch_falls_back_to_the_bucket_when_ahrq_is_down(bucket, tmp_path, ahrq):
    m = from_uri(f"gs://{bucket}/fallback")
    put(m, object_key(_sha(ORIGINAL_ZIP), f"h{N}dta.zip"), ORIGINAL_ZIP)
    ahrq["serve"] = OSError("down")
    assert fetch(N, cache=tmp_path, manifest=_manifest(), mirrors=[m]).read_bytes() == ORIGINAL_DTA


def test_fetch_rejects_changed_upstream_and_uses_the_bucket_original(bucket, tmp_path, ahrq):
    import io
    import zipfile
    m = from_uri(f"gs://{bucket}/changed")
    put(m, object_key(_sha(ORIGINAL_ZIP), f"h{N}dta.zip"), ORIGINAL_ZIP)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"h{N}.dta", b"quiet re-release")
    ahrq["serve"] = buf.getvalue()
    assert fetch(N, cache=tmp_path, manifest=_manifest(), mirrors=[m]).read_bytes() == ORIGINAL_DTA


# ── Housekeeping ─────────────────────────────────────────────────────────────────────


def test_fixture_image_matches_docker_compose():
    compose = (Path(__file__).resolve().parents[4] / "docker-compose.yml").read_text()
    assert re.search(r"image:\s*" + re.escape(GCS_EMULATOR_IMAGE) + r"\s*$", compose, re.M), (
        f"docker-compose.yml's gcs-emulator image differs from the test fixture's {GCS_EMULATOR_IMAGE}")


# ── The real MEPS originals in the populated emulator bucket ─────────────────────────


def test_populated_bucket_holds_every_longitudinal_data_zip(meps_emulator_bucket):
    from outcome_prediction.meps.mirror import verify as verify_mirror
    from outcome_prediction.tests.conftest import LONGITUDINAL_KEYS
    assert verify_mirror(load_manifest(), [meps_emulator_bucket], include_docs=False,
                         keys=LONGITUDINAL_KEYS) == []


def test_a_real_panel_restores_from_the_bucket_with_ahrq_down(meps_emulator_bucket, tmp_path, monkeypatch):
    """Panel 25 (HC-234, the smallest) into an empty cache, with AHRQ unreachable."""
    def ahrq_down(url):
        raise OSError("AHRQ unreachable (simulated)")
    monkeypatch.setattr(download, "_fetch_zip", ahrq_down)

    path = fetch(234, tmp_path, mirrors=[meps_emulator_bucket])

    assert _sha(path.read_bytes()) == load_manifest()["files"]["h234"]["data"]["dta_sha256"]
