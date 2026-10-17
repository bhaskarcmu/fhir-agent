"""gs:// mirrors against a real GCS emulator (fake-gcs-server — decisions.md O43): the actual
google-cloud-storage client, HTTP and the generation precondition, end to end.

Self-skips unless STORAGE_EMULATOR_HOST points at a running emulator. Locally:
    docker compose --profile phase8 up -d --wait gcs-emulator
    STORAGE_EMULATOR_HOST=http://localhost:4443 pytest <this file>
CI starts the same image and sets the variable, so this runs on every PR.
"""
from __future__ import annotations

import os
import urllib.request
import uuid

import pytest

storage = pytest.importorskip("google.cloud.storage", reason="needs the [gcs] extra")

from outcome_prediction.meps.download import fetch  # noqa: E402
from outcome_prediction.meps.mirror import (  # noqa: E402
    MirrorError, from_uri, object_key, push, put, verify,
)
from outcome_prediction.tests.test_meps_provenance import (  # noqa: E402,F401 — `ahrq` is a fixture
    N, ORIGINAL_DTA, ORIGINAL_ZIP, _manifest, _sha, ahrq,
)


@pytest.fixture(scope="module")
def bucket():
    host = os.environ.get("STORAGE_EMULATOR_HOST")
    if not host:
        pytest.skip("STORAGE_EMULATOR_HOST not set — no GCS emulator to test against")
    try:
        urllib.request.urlopen(f"{host}/storage/v1/b", timeout=3)
    except OSError as exc:
        pytest.skip(f"GCS emulator not reachable at {host} ({exc.__class__.__name__})")
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
