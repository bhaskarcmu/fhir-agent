"""FR-D1: download MEPS Stata files, verify them, and cache them.

Each file arrives as https://meps.ahrq.gov/data_files/pufs/h{n}/h{n}dta.zip containing
h{n}.dta (the folder-less URL form returns 404).

**Files in the committed manifest** (meps-manifest.json — decisions.md O41, O42) are verified
against it: the original zip must have the recorded SHA-256 wherever it came from, and so must
the extracted .dta. Sources are tried in order — the local archive, AHRQ, then each configured
private mirror (OUTCOME_PREDICTION_MEPS_MIRRORS, see meps.mirror). Bytes that don't match are
rejected, never cached: if AHRQ republishes a file, the original comes from a mirror until the
manifest is deliberately updated (meps.manifest snapshot --accept-change).

**Files not in the manifest** (e.g. event files before they're added) keep the simpler
behaviour: the first download's SHA-256 is recorded in <cache>/checksums.json and verified on
every later use.

Usage:
    python -m outcome_prediction.meps.download            # all longitudinal panels
    python -m outcome_prediction.meps.download 252 241    # specific file numbers
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from outcome_prediction.meps import LONGITUDINAL_PANELS
from outcome_prediction.meps.manifest import entry_for, load_manifest
from outcome_prediction.meps.mirror import ENV as MIRRORS_ENV
from outcome_prediction.meps.mirror import Mirror, configured_mirrors, object_key
from outcome_prediction.settings import meps_cache_dir

URL = "https://meps.ahrq.gov/data_files/pufs/h{n}/h{n}dta.zip"
CHECKSUMS = "checksums.json"
TIMEOUT_S = 120


class ChecksumMismatch(RuntimeError):
    """A cached file doesn't match the manifest, or the checksum recorded at download time."""


class SourceUnavailable(RuntimeError):
    """No source (archive, AHRQ, mirrors) could supply bytes matching the manifest."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fetch_zip(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=TIMEOUT_S) as resp:
        return resp.read()


def _extract_dta(zip_bytes: bytes, member: str) -> bytes:
    """Read one named member's bytes. Never ZipFile.extract(): we write to a path we choose,
    so a hostile member name can't escape the cache directory."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = {name.lower(): name for name in zf.namelist()}
        if member.lower() not in names:
            raise FileNotFoundError(f"{member} not in archive (found: {sorted(zf.namelist())})")
        return zf.read(names[member.lower()])


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)


def _obtain_zip(entry: dict, archive: Path, mirrors: list[Mirror]) -> bytes:
    """The original zip, verified against the manifest, from the first source that has it."""
    name, expected = entry["data"]["zip_name"], entry["data"]["zip_sha256"]
    cached = archive / name
    if cached.exists() and _sha256(cached.read_bytes()) == expected:
        return cached.read_bytes()

    sources = [("AHRQ", lambda: _fetch_zip(entry["data"]["url"]))]
    sources += [(m.uri, lambda m=m: m.get(object_key(expected, name))) for m in mirrors]
    attempts = []
    for label, get in sources:
        try:
            data = get()
        except Exception as exc:  # noqa: BLE001 — any failure means "try the next source"
            attempts.append(f"  {label}: {exc.__class__.__name__}: {exc}")
            continue
        if _sha256(data) != expected:
            attempts.append(f"  {label}: served sha256 {_sha256(data)[:12]}…, manifest expects "
                            f"{expected[:12]}… — rejected")
            continue
        _write_atomic(cached, data)
        return data
    hint = "" if mirrors else f"\n  (no private mirrors configured — set {MIRRORS_ENV})"
    raise SourceUnavailable(f"no source could supply {name} matching the manifest:\n"
                            + "\n".join(attempts) + hint)


def _fetch_manifested(file_number: int, entry: dict, cache: Path, mirrors: list[Mirror]) -> Path:
    name = f"h{file_number}.dta"
    path, expected = cache / name, entry["data"]["dta_sha256"]
    if path.exists():
        if _sha256(path.read_bytes()) != expected:
            raise ChecksumMismatch(f"{path} does not match meps-manifest.json ({expected[:12]}…). "
                                   f"Delete it to re-fetch, or investigate the change.")
        return path
    data = _extract_dta(_obtain_zip(entry, cache / "archive", mirrors), name)
    if _sha256(data) != expected:
        raise ChecksumMismatch(f"{name} extracted from a verified zip does not match the manifest "
                               f"— the manifest itself is inconsistent")
    _write_atomic(path, data)
    return path


def _load_checksums(cache: Path) -> dict:
    path = cache / CHECKSUMS
    return json.loads(path.read_text()) if path.exists() else {}


def _save_checksums(cache: Path, checksums: dict) -> None:
    (cache / CHECKSUMS).write_text(json.dumps(checksums, indent=2, sort_keys=True) + "\n")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fetch_unmanifested(file_number: int, cache: Path) -> Path:
    name = f"h{file_number}.dta"
    path = cache / name
    checksums = _load_checksums(cache)

    if path.exists():
        recorded = checksums.get(name, {}).get("sha256")
        actual = _sha256(path.read_bytes())
        if recorded is None:
            # Present but never recorded (e.g. copied in by hand): record it now.
            checksums[name] = {"sha256": actual, "source_url": None, "recorded_at": _now()}
            _save_checksums(cache, checksums)
        elif recorded != actual:
            raise ChecksumMismatch(
                f"{path} has sha256 {actual}, but {recorded} was recorded when it was "
                f"downloaded. Delete the file to re-download, or investigate the change."
            )
        return path

    url = URL.format(n=file_number)
    data = _extract_dta(_fetch_zip(url), name)
    _write_atomic(path, data)
    checksums[name] = {"sha256": _sha256(data), "source_url": url, "recorded_at": _now()}
    _save_checksums(cache, checksums)
    return path


def fetch(file_number: int, cache: Path | None = None, *, manifest: dict | None = None,
          mirrors: list[Mirror] | None = None) -> Path:
    """Return the path to a verified h{n}.dta, obtaining it if absent."""
    cache = cache or meps_cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    entry = entry_for(load_manifest() if manifest is None else manifest, file_number)
    if entry is None:
        return _fetch_unmanifested(file_number, cache)
    return _fetch_manifested(file_number, entry, cache,
                             configured_mirrors() if mirrors is None else mirrors)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="*", type=int,
                        help="MEPS file numbers (default: all two-year longitudinal panels)")
    args = parser.parse_args(argv)
    for n in args.files or LONGITUDINAL_PANELS.values():
        path = fetch(n)
        print(f"h{n}.dta  {path.stat().st_size:>12,} bytes  {path}")


if __name__ == "__main__":
    main()
