"""The committed MEPS data manifest (docs/phase8/decisions.md O41, O42).

``outcome-prediction-service/meps-manifest.json`` is committed to git — like a lock file for
data. For every MEPS file it records the source URLs and the SHA-256 of the original zip, the
extracted .dta, and the documentation snapshot (doc page + codebook PDF). The data itself is
never committed; the manifest is what makes "the same data" checkable years later.

``download.fetch`` refuses any bytes that don't match the manifest — from AHRQ or a mirror.
Adopting a new AHRQ release is therefore a deliberate, reviewed change:

    python -m outcome_prediction.meps.manifest snapshot                  # record (first time)
    python -m outcome_prediction.meps.manifest snapshot --accept-change  # re-record after AHRQ changed a file

Snapshot also keeps the original zips and documentation in the local archive
(<data>/raw/meps/archive/) so they can be pushed to the private mirrors (meps.mirror).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from outcome_prediction.meps import LONGITUDINAL_PANELS
from outcome_prediction.settings import SERVICE_ROOT, meps_cache_dir

MANIFEST_PATH = SERVICE_ROOT / "meps-manifest.json"
DATA_URL = "https://meps.ahrq.gov/data_files/pufs/h{n}/h{n}dta.zip"
DOC_URL = "https://meps.ahrq.gov/data_stats/download_data/pufs/h{n}/h{n}doc.shtml"
CODEBOOK_URL = "https://meps.ahrq.gov/data_stats/download_data/pufs/h{n}/h{n}cb.pdf"


class ManifestChange(RuntimeError):
    """AHRQ now serves different data bytes than the manifest records."""


def archive_dir() -> Path:
    return meps_cache_dir() / "archive"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_manifest(path: Path | None = None) -> dict:
    path = path or MANIFEST_PATH
    return json.loads(path.read_text()) if path.exists() else {"files": {}}


def save_manifest(manifest: dict, path: Path | None = None) -> None:
    (path or MANIFEST_PATH).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def entry_for(manifest: dict, file_number: int) -> dict | None:
    return manifest.get("files", {}).get(f"h{file_number}")


def _panel_for(file_number: int) -> int | None:
    return next((p for p, n in LONGITUDINAL_PANELS.items() if n == file_number), None)


def snapshot(file_number: int, manifest: dict, *, accept_change: bool = False,
             archive: Path | None = None, fetch_bytes=None) -> dict:
    """Download the original zip, doc page and codebook; archive them; return the manifest
    entry. Raises ManifestChange if the data differs from an existing entry, unless accepted."""
    from outcome_prediction.meps.download import _extract_dta, _fetch_zip

    fetch_bytes = fetch_bytes or _fetch_zip
    archive = archive or archive_dir()
    archive.mkdir(parents=True, exist_ok=True)

    zip_name, dta_name = f"h{file_number}dta.zip", f"h{file_number}.dta"
    zip_bytes = fetch_bytes(DATA_URL.format(n=file_number))
    dta_bytes = _extract_dta(zip_bytes, dta_name)
    data = {"url": DATA_URL.format(n=file_number), "zip_name": zip_name,
            "zip_sha256": sha256(zip_bytes), "zip_bytes": len(zip_bytes),
            "dta_name": dta_name, "dta_sha256": sha256(dta_bytes), "dta_bytes": len(dta_bytes)}

    previous = entry_for(manifest, file_number)
    if previous and not accept_change and (
            previous["data"]["zip_sha256"], previous["data"]["dta_sha256"]) != (
            data["zip_sha256"], data["dta_sha256"]):
        raise ManifestChange(
            f"AHRQ now serves different bytes for {zip_name} than the manifest records "
            f"(zip {previous['data']['zip_sha256'][:12]}… -> {data['zip_sha256'][:12]}…). "
            f"Investigate the release notes; re-run with --accept-change to adopt it.")

    docs = []
    for url in (DOC_URL.format(n=file_number), CODEBOOK_URL.format(n=file_number)):
        body = fetch_bytes(url)
        name = url.rsplit("/", 1)[1]
        (archive / name).write_bytes(body)
        docs.append({"url": url, "name": name, "sha256": sha256(body), "bytes": len(body)})
    (archive / zip_name).write_bytes(zip_bytes)

    return {"panel": _panel_for(file_number),
            "kind": "longitudinal" if _panel_for(file_number) else "other",
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data": data, "documentation": docs}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["snapshot"])
    parser.add_argument("files", nargs="*", type=int,
                        help="MEPS file numbers (default: all two-year longitudinal panels)")
    parser.add_argument("--accept-change", action="store_true",
                        help="adopt data that differs from the manifest (a deliberate, reviewed change)")
    args = parser.parse_args(argv)

    manifest = load_manifest()
    manifest.setdefault("files", {})
    manifest["description"] = (
        "MEPS public-use files used by Phase 8, by SHA-256. Data is never committed; "
        "download.fetch refuses bytes that don't match. See docs/phase8/decisions.md O41-O42.")
    for n in args.files or LONGITUDINAL_PANELS.values():
        entry = snapshot(n, manifest, accept_change=args.accept_change)
        manifest["files"][f"h{n}"] = entry
        d = entry["data"]
        print(f"h{n}: zip {d['zip_bytes']:>11,} B {d['zip_sha256'][:12]}…  "
              f"dta {d['dta_bytes']:>12,} B {d['dta_sha256'][:12]}…  "
              f"docs {sum(x['bytes'] for x in entry['documentation']):>11,} B")
    save_manifest(manifest)
    print(f"wrote {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
