"""Unit tests for MEPS download/caching — the network is replaced with in-memory zips."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest

from outcome_prediction.meps import download
from outcome_prediction.meps.download import ChecksumMismatch, fetch


def _zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


@pytest.fixture
def network(monkeypatch):
    """Serve canned zips by URL and count requests."""
    served: dict[str, bytes] = {}
    calls: list[str] = []

    def fake_fetch(url):
        calls.append(url)
        return served[url]

    monkeypatch.setattr(download, "_fetch_zip", fake_fetch)
    return served, calls


def test_downloads_extracts_and_records_checksum(tmp_path, network):
    served, calls = network
    served[download.URL.format(n=999)] = _zip({"h999.dta": b"stata-bytes"})

    path = fetch(999, cache=tmp_path)

    assert path == tmp_path / "h999.dta"
    assert path.read_bytes() == b"stata-bytes"
    recorded = json.loads((tmp_path / "checksums.json").read_text())["h999.dta"]
    assert recorded["sha256"] == hashlib.sha256(b"stata-bytes").hexdigest()
    assert recorded["source_url"] == "https://meps.ahrq.gov/data_files/pufs/h999/h999dta.zip"
    assert calls == [recorded["source_url"]]


def test_cached_file_is_verified_not_redownloaded(tmp_path, network):
    served, calls = network
    served[download.URL.format(n=999)] = _zip({"h999.dta": b"stata-bytes"})
    fetch(999, cache=tmp_path)

    fetch(999, cache=tmp_path)

    assert len(calls) == 1


def test_changed_cached_file_fails_loudly(tmp_path, network):
    served, _ = network
    served[download.URL.format(n=999)] = _zip({"h999.dta": b"stata-bytes"})
    fetch(999, cache=tmp_path)
    (tmp_path / "h999.dta").write_bytes(b"tampered")

    with pytest.raises(ChecksumMismatch):
        fetch(999, cache=tmp_path)


def test_unrecorded_cached_file_gets_recorded(tmp_path, network):
    _, calls = network
    (tmp_path / "h999.dta").write_bytes(b"copied-in-by-hand")

    fetch(999, cache=tmp_path)

    recorded = json.loads((tmp_path / "checksums.json").read_text())["h999.dta"]
    assert recorded["sha256"] == hashlib.sha256(b"copied-in-by-hand").hexdigest()
    assert calls == []


def test_member_lookup_is_by_exact_name_and_never_escapes_cache(tmp_path, network):
    served, _ = network
    cache = tmp_path / "cache"
    served[download.URL.format(n=999)] = _zip({"../escape.dta": b"x", "H999.DTA": b"real"})

    path = fetch(999, cache=cache)

    assert path.read_bytes() == b"real"            # matched case-insensitively
    assert not (tmp_path / "escape.dta").exists()  # the hostile member was never written


def test_archive_without_expected_member_raises(tmp_path, network):
    served, _ = network
    served[download.URL.format(n=999)] = _zip({"readme.txt": b"x"})

    with pytest.raises(FileNotFoundError, match="h999.dta"):
        fetch(999, cache=tmp_path)
    assert not (tmp_path / "h999.dta").exists()
