"""Private mirrors of the original MEPS files (docs/phase8/decisions.md O41).

AHRQ stays the primary source; a mirror is the backstop for when AHRQ is unreachable, moves a
file, or republishes different bytes. Objects are **content-addressed** —
``meps/sha256/<sha256>/<original filename>`` — and **never overwritten**: putting an object
that already exists is a no-op if the bytes match and an error if they don't.

Mirrors are configured with OUTCOME_PREDICTION_MEPS_MIRRORS, a comma-separated list tried in
order, e.g.::

    OUTCOME_PREDICTION_MEPS_MIRRORS=gs://my-project-phase8-reference-data,file:///mnt/backup/meps

``gs://`` needs the optional dependency (``pip install -e "outcome-prediction-service[gcs]"``)
and Application Default Credentials. ``file://`` is a plain directory — used by the tests, and
usable as an extra offline copy.

Usage:
    python -m outcome_prediction.meps.mirror push      # upload everything in the manifest
    python -m outcome_prediction.meps.mirror verify    # re-download + hash every mirrored object
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

ENV = "OUTCOME_PREDICTION_MEPS_MIRRORS"


class MirrorError(RuntimeError):
    """A mirror holds different bytes under a content-addressed key, or can't be reached."""


def object_key(sha256: str, name: str) -> str:
    if "/" in name or name.startswith("."):
        raise ValueError(f"unsafe object name {name!r}")
    return f"meps/sha256/{sha256}/{name}"


class Mirror(Protocol):
    uri: str

    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def _create(self, key: str, data: bytes) -> bool:
        """Create `key` only if absent. Returns False if it already existed."""


def put(mirror: Mirror, key: str, data: bytes) -> bool:
    """Write-once put. True if uploaded, False if an identical object was already there."""
    if mirror._create(key, data):
        return True
    if hashlib.sha256(mirror.get(key)).hexdigest() != hashlib.sha256(data).hexdigest():
        raise MirrorError(f"{mirror.uri}: {key} exists with different content — refusing to overwrite")
    return False


class LocalMirror:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.uri = f"file://{self.root}"

    def _path(self, key: str) -> Path:
        return self.root / key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def _create(self, key: str, data: bytes) -> bool:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "xb") as f:      # exclusive create: never overwrites
                f.write(data)
        except FileExistsError:
            return False
        return True


class GcsMirror:
    """The client is created on first use, not at construction: a configured gs:// mirror
    without credentials must surface as one failed source in fetch's fallback list, not stop
    fetch from trying AHRQ at all."""

    def __init__(self, bucket: str, prefix: str = ""):
        self._bucket_name = bucket
        self._bucket = None
        self._prefix = prefix.strip("/")
        self.uri = f"gs://{bucket}/{self._prefix}".rstrip("/")

    def _blob(self, key: str):
        if self._bucket is None:
            try:
                from google.cloud import storage
            except ImportError as exc:
                raise MirrorError('gs:// mirrors need: pip install -e "outcome-prediction-service[gcs]"') from exc
            self._bucket = storage.Client().bucket(self._bucket_name)
        return self._bucket.blob(f"{self._prefix}/{key}" if self._prefix else key)

    def get(self, key: str) -> bytes:
        return self._blob(key).download_as_bytes()

    def exists(self, key: str) -> bool:
        return self._blob(key).exists()

    def _create(self, key: str, data: bytes) -> bool:
        from google.api_core.exceptions import PreconditionFailed
        try:
            # if_generation_match=0: succeed only if no live object exists — write-once.
            self._blob(key).upload_from_string(data, if_generation_match=0)
        except PreconditionFailed:
            return False
        return True


def from_uri(uri: str) -> Mirror:
    parsed = urlparse(uri.strip())
    if parsed.scheme == "file":
        return LocalMirror(Path(parsed.path))
    if parsed.scheme == "gs" and parsed.netloc:
        return GcsMirror(parsed.netloc, parsed.path)
    raise ValueError(f"unsupported mirror URI {uri!r} (use gs://bucket[/prefix] or file:///path)")


def configured_mirrors() -> list[Mirror]:
    return [from_uri(u) for u in os.environ.get(ENV, "").split(",") if u.strip()]


def _archived_files(manifest: dict) -> list[tuple[str, str]]:
    """(name, sha256) of every original file the manifest records: data zips and docs."""
    files = []
    for entry in manifest["files"].values():
        files.append((entry["data"]["zip_name"], entry["data"]["zip_sha256"]))
        files += [(doc["name"], doc["sha256"]) for doc in entry["documentation"]]
    return files


def push(manifest: dict, archive: Path, mirrors: list[Mirror]) -> list[str]:
    """Upload every manifest file from the local archive to every mirror. Each file is
    checked against the manifest first, so a mirror never receives unverified bytes."""
    log = []
    for name, sha in _archived_files(manifest):
        data = (archive / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != sha:
            raise MirrorError(f"{archive / name} does not match the manifest — not uploading")
        for mirror in mirrors:
            uploaded = put(mirror, object_key(sha, name), data)
            log.append(f"{'uploaded' if uploaded else 'present '}  {mirror.uri}/{object_key(sha, name)}")
    return log


def verify(manifest: dict, mirrors: list[Mirror]) -> list[str]:
    """Re-download and hash every manifest file on every mirror. Returns problems found."""
    problems = []
    for name, sha in _archived_files(manifest):
        for mirror in mirrors:
            key = object_key(sha, name)
            try:
                actual = hashlib.sha256(mirror.get(key)).hexdigest()
            except Exception as exc:  # noqa: BLE001 — report every failure, keep going
                problems.append(f"{mirror.uri}/{key}: unreadable ({exc.__class__.__name__})")
                continue
            if actual != sha:
                problems.append(f"{mirror.uri}/{key}: sha256 {actual} != manifest {sha}")
    return problems


def main(argv: list[str] | None = None) -> None:
    from outcome_prediction.meps.manifest import archive_dir, load_manifest

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["push", "verify"])
    args = parser.parse_args(argv)
    mirrors = configured_mirrors()
    if not mirrors:
        raise SystemExit(f"no mirrors configured — set {ENV} (see module docstring)")
    manifest = load_manifest()
    if args.command == "push":
        print(*push(manifest, archive_dir(), mirrors), sep="\n")
    else:
        problems = verify(manifest, mirrors)
        print(*(problems or [f"all {len(_archived_files(manifest))} files verified on "
                             f"{', '.join(m.uri for m in mirrors)}"]), sep="\n")
        if problems:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
