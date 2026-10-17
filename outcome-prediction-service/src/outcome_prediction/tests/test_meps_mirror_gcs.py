"""gs:// mirrors (decisions.md O41): write-once uploads via a generation precondition, use as a
fetch fallback, and no-credentials behaviour — against an in-memory fake bucket that raises the
library's real exceptions. Skipped without the [gcs] extra (CI installs it)."""
from __future__ import annotations

import pytest

from outcome_prediction.meps.download import SourceUnavailable, fetch
from outcome_prediction.meps.mirror import MirrorError, from_uri, object_key, put
from outcome_prediction.tests.test_meps_provenance import (  # noqa: F401 — `ahrq` is a fixture
    N, ORIGINAL_DTA, ORIGINAL_ZIP, _manifest, _sha, ahrq,
)


storage = pytest.importorskip("google.cloud.storage", reason="needs the [gcs] extra")
from google.api_core.exceptions import PreconditionFailed  # noqa: E402
from google.auth.exceptions import DefaultCredentialsError  # noqa: E402

from outcome_prediction.meps.mirror import GcsMirror  # noqa: E402


class _FakeBlob:
    def __init__(self, store, name):
        self.store, self.name = store, name

    def upload_from_string(self, data, if_generation_match=None):
        if if_generation_match == 0 and self.name in self.store:
            raise PreconditionFailed("object exists")
        self.store[self.name] = data

    def download_as_bytes(self):
        return self.store[self.name]

    def exists(self):
        return self.name in self.store


class _FakeBucket:
    def __init__(self):
        self.store = {}

    def blob(self, name):
        return _FakeBlob(self.store, name)


def _gcs(prefix=""):
    m = GcsMirror("phase8-test", prefix)
    m._bucket = _FakeBucket()
    return m


def test_gcs_put_is_write_once_via_generation_precondition():
    m = _gcs("archive")
    key = object_key(_sha(b"a"), "f.zip")
    assert put(m, key, b"a") is True
    assert put(m, key, b"a") is False
    with pytest.raises(MirrorError, match="refusing to overwrite"):
        put(m, key, b"b")
    assert list(m._bucket.store) == [f"archive/{key}"]
    assert m.uri == "gs://phase8-test/archive"


def test_gcs_mirror_serves_fetch_fallback(tmp_path, ahrq):
    m = _gcs()
    put(m, object_key(_sha(ORIGINAL_ZIP), f"h{N}dta.zip"), ORIGINAL_ZIP)
    ahrq["serve"] = OSError("down")
    assert fetch(N, cache=tmp_path, manifest=_manifest(), mirrors=[m]).read_bytes() == ORIGINAL_DTA


def test_gcs_mirror_without_credentials_never_blocks_ahrq(tmp_path, ahrq, monkeypatch):
    def no_credentials(*a, **k):
        raise DefaultCredentialsError("no ADC")
    monkeypatch.setattr(storage, "Client", no_credentials)

    m = from_uri("gs://phase8-test")                          # constructing needs no credentials
    assert fetch(N, cache=tmp_path, manifest=_manifest(), mirrors=[m]).read_bytes() == ORIGINAL_DTA

    (tmp_path / f"h{N}.dta").unlink()
    (tmp_path / "archive" / f"h{N}dta.zip").unlink()
    ahrq["serve"] = OSError("down")
    with pytest.raises(SourceUnavailable, match=r"gs://phase8-test: DefaultCredentialsError"):
        fetch(N, cache=tmp_path, manifest=_manifest(), mirrors=[m])
