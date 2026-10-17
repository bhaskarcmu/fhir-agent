"""Data provenance and preservation (decisions.md O41, O42): the committed manifest, write-once
private mirrors, and the download fallback order. Fully offline — AHRQ is faked."""
from __future__ import annotations

import hashlib
import io
import re
import zipfile

import pytest

from outcome_prediction.meps import LONGITUDINAL_PANELS, download
from outcome_prediction.meps.download import ChecksumMismatch, SourceUnavailable, fetch
from outcome_prediction.meps.manifest import (
    MANIFEST_PATH, ManifestChange, load_manifest, snapshot,
)
from outcome_prediction.meps.mirror import (
    LocalMirror, MirrorError, from_uri, object_key, push, put, verify,
)

N = 999


def _zip(dta: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"h{N}.dta", dta)
    return buf.getvalue()


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


ORIGINAL_DTA = b"original stata bytes"
ORIGINAL_ZIP = _zip(ORIGINAL_DTA)


def _manifest() -> dict:
    return {"files": {f"h{N}": {
        "panel": None, "kind": "other", "retrieved_at": "2026-10-17T00:00:00+00:00",
        "data": {"url": f"https://example.invalid/h{N}dta.zip", "zip_name": f"h{N}dta.zip",
                 "zip_sha256": _sha(ORIGINAL_ZIP), "zip_bytes": len(ORIGINAL_ZIP),
                 "dta_name": f"h{N}.dta", "dta_sha256": _sha(ORIGINAL_DTA),
                 "dta_bytes": len(ORIGINAL_DTA)},
        "documentation": [{"url": "https://example.invalid/doc", "name": f"h{N}doc.shtml",
                           "sha256": _sha(b"doc"), "bytes": 3}],
    }}}


@pytest.fixture
def ahrq(monkeypatch):
    """What 'AHRQ' serves: bytes, or an exception to raise."""
    state = {"serve": ORIGINAL_ZIP, "calls": 0}

    def fake(url):
        state["calls"] += 1
        if isinstance(state["serve"], Exception):
            raise state["serve"]
        return state["serve"]

    monkeypatch.setattr(download, "_fetch_zip", fake)
    return state


@pytest.fixture
def mirror(tmp_path):
    m = LocalMirror(tmp_path / "mirror")
    put(m, object_key(_sha(ORIGINAL_ZIP), f"h{N}dta.zip"), ORIGINAL_ZIP)
    return m


# ── The committed manifest ────────────────────────────────────────────────────────────


def test_committed_manifest_pins_every_longitudinal_panel():
    files = load_manifest(MANIFEST_PATH)["files"]
    assert set(files) == {f"h{n}" for n in LONGITUDINAL_PANELS.values()}
    for key, entry in files.items():
        assert entry["panel"] == {f"h{n}": p for p, n in LONGITUDINAL_PANELS.items()}[key]
        assert re.fullmatch(r"[0-9a-f]{64}", entry["data"]["zip_sha256"])
        assert re.fullmatch(r"[0-9a-f]{64}", entry["data"]["dta_sha256"])
        assert {d["name"] for d in entry["documentation"]} == {f"{key}doc.shtml", f"{key}cb.pdf"}


def test_committed_manifest_matches_the_local_cache(meps_cache):
    """Where the real data is present, it is exactly what the manifest pins."""
    for key, entry in load_manifest(MANIFEST_PATH)["files"].items():
        path = meps_cache / entry["data"]["dta_name"]
        assert _sha(path.read_bytes()) == entry["data"]["dta_sha256"], key


# ── Fallback order and verification ──────────────────────────────────────────────────


def test_ahrq_first_and_original_zip_archived(tmp_path, ahrq):
    path = fetch(N, cache=tmp_path, manifest=_manifest(), mirrors=[])
    assert path.read_bytes() == ORIGINAL_DTA
    assert (tmp_path / "archive" / f"h{N}dta.zip").read_bytes() == ORIGINAL_ZIP


def test_archived_zip_is_reused_without_network(tmp_path, ahrq):
    fetch(N, cache=tmp_path, manifest=_manifest(), mirrors=[])
    (tmp_path / f"h{N}.dta").unlink()
    fetch(N, cache=tmp_path, manifest=_manifest(), mirrors=[])
    assert ahrq["calls"] == 1


def test_mirror_used_when_ahrq_is_down(tmp_path, ahrq, mirror):
    ahrq["serve"] = OSError("connection refused")
    assert fetch(N, cache=tmp_path, manifest=_manifest(), mirrors=[mirror]).read_bytes() == ORIGINAL_DTA


def test_changed_upstream_bytes_are_rejected_and_the_mirror_original_used(tmp_path, ahrq, mirror):
    ahrq["serve"] = _zip(b"a quietly corrected re-release")
    assert fetch(N, cache=tmp_path, manifest=_manifest(), mirrors=[mirror]).read_bytes() == ORIGINAL_DTA
    assert (tmp_path / "archive" / f"h{N}dta.zip").read_bytes() == ORIGINAL_ZIP


def test_no_matching_source_fails_loudly_and_caches_nothing(tmp_path, ahrq):
    ahrq["serve"] = _zip(b"different")
    with pytest.raises(SourceUnavailable) as exc:
        fetch(N, cache=tmp_path, manifest=_manifest(), mirrors=[LocalMirror(tmp_path / "empty")])
    message = str(exc.value)
    assert "AHRQ: served sha256" in message and "rejected" in message
    assert "empty" in message                                   # the mirror attempt is reported
    assert not (tmp_path / f"h{N}.dta").exists()
    assert not (tmp_path / "archive" / f"h{N}dta.zip").exists()


def test_missing_mirror_configuration_is_named_in_the_error(tmp_path, ahrq):
    ahrq["serve"] = OSError("down")
    with pytest.raises(SourceUnavailable, match="no private mirrors configured"):
        fetch(N, cache=tmp_path, manifest=_manifest(), mirrors=[])


def test_cached_dta_not_matching_manifest_is_refused(tmp_path, ahrq):
    (tmp_path / f"h{N}.dta").write_bytes(b"something else")
    with pytest.raises(ChecksumMismatch, match="meps-manifest.json"):
        fetch(N, cache=tmp_path, manifest=_manifest(), mirrors=[])


def test_unmanifested_files_keep_the_simple_behaviour(tmp_path, ahrq):
    path = fetch(N, cache=tmp_path, manifest={"files": {}}, mirrors=[])
    assert path.read_bytes() == ORIGINAL_DTA
    assert (tmp_path / "checksums.json").exists()


# ── Mirrors are write-once and content-addressed ─────────────────────────────────────


def test_put_is_write_once(tmp_path):
    m = LocalMirror(tmp_path)
    key = object_key(_sha(b"a"), "f.zip")
    assert put(m, key, b"a") is True
    assert put(m, key, b"a") is False                 # identical: no-op
    with pytest.raises(MirrorError, match="refusing to overwrite"):
        put(m, key, b"b")
    assert m.get(key) == b"a"


def test_object_keys_are_content_addressed_and_safe():
    assert object_key("ab" * 32, "h252dta.zip") == f"meps/sha256/{'ab' * 32}/h252dta.zip"
    for bad in ("../x", "a/b", ".hidden"):
        with pytest.raises(ValueError):
            object_key("ab" * 32, bad)


def test_from_uri(tmp_path):
    assert isinstance(from_uri(f"file://{tmp_path}"), LocalMirror)
    with pytest.raises(ValueError):
        from_uri("s3://bucket")


def test_push_verifies_against_manifest_then_uploads_everything(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / f"h{N}dta.zip").write_bytes(ORIGINAL_ZIP)
    (archive / f"h{N}doc.shtml").write_bytes(b"doc")
    m = LocalMirror(tmp_path / "mirror")

    log = push(_manifest(), archive, [m])

    assert len(log) == 2 and all(line.startswith("uploaded") for line in log)
    assert verify(_manifest(), [m]) == []
    assert all(line.startswith("present") for line in push(_manifest(), archive, [m]))


def test_push_refuses_archive_bytes_that_dont_match_the_manifest(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / f"h{N}dta.zip").write_bytes(b"tampered")
    with pytest.raises(MirrorError, match="does not match the manifest"):
        push(_manifest(), archive, [LocalMirror(tmp_path / "mirror")])


def test_verify_reports_missing_and_corrupted_objects(tmp_path, mirror):
    key = object_key(_sha(ORIGINAL_ZIP), f"h{N}dta.zip")
    (mirror.root / key).write_bytes(b"bit rot")
    problems = verify(_manifest(), [mirror])
    assert len(problems) == 2
    assert any(f"h{N}dta.zip" in p and "!= manifest" in p for p in problems)        # corrupted zip
    assert any(f"h{N}doc.shtml" in p and "unreadable" in p for p in problems)       # never pushed


# ── Snapshot: adopting changed data is deliberate ────────────────────────────────────


def _fake_fetch(zip_bytes):
    return lambda url: zip_bytes if url.endswith("dta.zip") else f"doc for {url}".encode()


def test_snapshot_records_data_and_documentation(tmp_path):
    entry = snapshot(N, {"files": {}}, archive=tmp_path, fetch_bytes=_fake_fetch(ORIGINAL_ZIP))
    assert entry["data"]["zip_sha256"] == _sha(ORIGINAL_ZIP)
    assert entry["data"]["dta_sha256"] == _sha(ORIGINAL_DTA)
    assert [d["name"] for d in entry["documentation"]] == [f"h{N}doc.shtml", f"h{N}cb.pdf"]
    assert (tmp_path / f"h{N}dta.zip").read_bytes() == ORIGINAL_ZIP


def test_snapshot_refuses_changed_data_unless_accepted(tmp_path):
    changed = _fake_fetch(_zip(b"re-release"))
    with pytest.raises(ManifestChange, match="--accept-change"):
        snapshot(N, _manifest(), archive=tmp_path, fetch_bytes=changed)
    entry = snapshot(N, _manifest(), archive=tmp_path, fetch_bytes=changed, accept_change=True)
    assert entry["data"]["dta_sha256"] == _sha(b"re-release")

