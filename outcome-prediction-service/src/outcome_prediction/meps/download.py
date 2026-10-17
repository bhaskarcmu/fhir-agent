"""FR-D1: download MEPS Stata files from AHRQ, cache them, and record checksums.

Each file arrives as https://meps.ahrq.gov/data_files/pufs/h{n}/h{n}dta.zip containing
h{n}.dta (the folder-less URL form returns 404). The extracted .dta's SHA-256 is recorded
in <cache>/checksums.json on first download and verified on every later use, so a
silently changed or corrupted file fails loudly instead of shifting the numbers.

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
from outcome_prediction.settings import meps_cache_dir

URL = "https://meps.ahrq.gov/data_files/pufs/h{n}/h{n}dta.zip"
CHECKSUMS = "checksums.json"
TIMEOUT_S = 120


class ChecksumMismatch(RuntimeError):
    """A cached file no longer matches the checksum recorded when it was downloaded."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_checksums(cache: Path) -> dict:
    path = cache / CHECKSUMS
    return json.loads(path.read_text()) if path.exists() else {}


def _save_checksums(cache: Path, checksums: dict) -> None:
    (cache / CHECKSUMS).write_text(json.dumps(checksums, indent=2, sort_keys=True) + "\n")


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


def fetch(file_number: int, cache: Path | None = None) -> Path:
    """Return the path to h{n}.dta, downloading it if absent; verify its checksum either way."""
    cache = cache or meps_cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
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
    tmp = path.with_suffix(".dta.part")
    tmp.write_bytes(data)
    tmp.replace(path)
    checksums[name] = {"sha256": _sha256(data), "source_url": url, "recorded_at": _now()}
    _save_checksums(cache, checksums)
    return path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
