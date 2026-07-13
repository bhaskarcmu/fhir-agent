"""Persistent archive state, keyed by session id.

The manifest is committed alongside the archive. It serves two jobs that plain
full-regeneration cannot:

1. Rename cleanup — it remembers each session's *previous* markdown filename, so
   when a title changes the old file can be removed (not left as a duplicate).
2. Retention + index — sessions deleted from the Claude Code source are kept
   here (marked ``present: false``) so their archived files are retained and
   still listed in INDEX.md for future access.

This is *state/identity* tracking, not a content-hash incremental cache — the
archive content itself is still regenerated every run.
"""

from __future__ import annotations

import json
from pathlib import Path

from .writer import atomic_write


def load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save(path: Path, manifest: dict) -> None:
    atomic_write(path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
