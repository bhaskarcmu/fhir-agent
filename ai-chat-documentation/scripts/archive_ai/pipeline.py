"""Regeneration pipeline: discover -> parse -> redact -> render -> write.

Every run reprocesses all live sessions and rebuilds INDEX.md from the manifest.
Identity/retention rules (see manifest.py):

* rename  — a live session whose title changed gets its old markdown removed and
  the new-named file written (git records a rename).
* delete  — a session removed from the source is *retained*: its files are kept
  and it stays in the index, flagged archived.
* exclude — a session in exclusions.txt is never archived, and any prior archive
  of it is purged (privacy overrides retention).

Robustness: tolerant of legacy/malformed manifest entries (missing fields), and
self-heals a retained entry whose markdown was deleted by regenerating it from
the redacted raw copy — or drops the entry if unrecoverable, so INDEX never
points at a missing file.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import discovery, manifest as manifest_mod
from .config import SOURCE_NAME, Config
from .parser import parse_session
from .redactor import Redactor
from .renderer import markdown_filename, render_index, render_markdown
from .writer import atomic_write


@dataclass
class PipelineResult:
    sessions_processed: int = 0
    sessions_excluded: int = 0
    sessions_retained: int = 0
    sessions_healed: int = 0
    sessions_dropped: int = 0
    files_written: int = 0
    redactions: Counter = field(default_factory=Counter)


def run(config: Config, now: datetime | None = None) -> PipelineResult:
    now = now or datetime.now(timezone.utc)
    sessions = discovery.find_sessions(config)
    exclusions = config.load_exclusions()
    redactor = Redactor.from_file(config.patterns_file)
    manifest = manifest_mod.load(config.manifest_path)
    result = PipelineResult()

    md_dir, raw_dir = config.markdown_dir, config.raw_dir

    # Privacy overrides retention: purge any prior archive of excluded sessions.
    for sid in list(manifest):
        if sid in exclusions:
            prev = manifest.pop(sid)
            _remove_archive_file(md_dir, prev.get("md_filename"))
            _remove_archive_file(raw_dir, prev.get("raw_filename") or f"{sid}.jsonl")

    live_ids: set[str] = set()
    for path in sessions:
        sid = path.stem
        if sid in exclusions:
            result.sessions_excluded += 1
            continue

        conv = parse_session(path)
        live_ids.add(sid)
        title_r = redactor.redact(conv.title)
        md_name = markdown_filename(sid, title_r)

        prev = manifest.get(sid)
        if prev and prev.get("md_filename") and prev["md_filename"] != md_name:
            _remove_archive_file(md_dir, prev["md_filename"])  # rename cleanup

        raw_text = path.read_text(encoding="utf-8", errors="replace")
        atomic_write(raw_dir / f"{sid}.jsonl", redactor.redact(raw_text))
        atomic_write(md_dir / md_name, redactor.redact(render_markdown(conv)))
        result.files_written += 2
        result.sessions_processed += 1

        manifest[sid] = {
            "title": title_r,
            "md_filename": md_name,
            "raw_filename": f"{sid}.jsonl",
            "created_at": _iso(conv.created_at),
            "updated_at": _iso(conv.updated_at),
            "turns": len(conv.turns),
            "status": conv.status,
            "present": True,
            "archived_at": (prev or {}).get("archived_at") or now.isoformat(),
            "source_deleted_at": None,
        }

    # Retention: sessions no longer in the source are kept, just marked absent.
    for sid, entry in manifest.items():
        if sid not in live_ids and entry.get("present", True):
            entry["present"] = False
            entry["source_deleted_at"] = now.isoformat()

    # Self-heal: regenerate any entry whose markdown is missing from its retained
    # raw copy; drop entries that are unrecoverable so INDEX has no broken links.
    result.sessions_healed, result.sessions_dropped = _heal_missing_markdown(config, manifest, redactor)
    result.sessions_retained = sum(1 for e in manifest.values() if not e.get("present", True))

    manifest_mod.save(config.manifest_path, manifest)
    atomic_write(config.index_path, redactor.redact(render_index(manifest, f"markdown/{SOURCE_NAME}")))
    result.files_written += 2  # manifest + index
    result.redactions = redactor.counts
    return result


def commit_message(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"Archive Claude Code conversations: {now.strftime('%Y-%m-%d %H:%M UTC')}"


# --- helpers -----------------------------------------------------------

def _heal_missing_markdown(config: Config, manifest: dict, redactor: Redactor) -> tuple[int, int]:
    """Ensure every manifest entry's markdown exists.

    If the markdown is missing but the (redacted) raw copy is present, re-render
    it from raw. If neither exists, drop the entry so INDEX cannot link to a
    missing file. Returns ``(healed, dropped)``.
    """
    md_dir, raw_dir = config.markdown_dir, config.raw_dir
    healed = dropped = 0
    for sid in list(manifest):
        entry = manifest[sid]
        name = entry.get("md_filename")
        if name and (md_dir / Path(name).name).is_file():
            continue  # markdown present and named
        raw_path = raw_dir / (entry.get("raw_filename") or f"{sid}.jsonl")
        if raw_path.is_file():
            conv = parse_session(raw_path)  # raw copy is already redacted
            new_name = markdown_filename(sid, entry.get("title") or conv.title)
            atomic_write(md_dir / new_name, redactor.redact(render_markdown(conv)))
            entry["md_filename"] = new_name
            entry.setdefault("raw_filename", f"{sid}.jsonl")
            healed += 1
        else:
            manifest.pop(sid, None)  # unrecoverable
            dropped += 1
    return healed, dropped


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _remove_archive_file(directory: Path, filename: str | None) -> None:
    """Delete ``directory/<basename(filename)>`` only if it is an existing file.

    Tolerates missing/empty/legacy filenames and never touches a directory, so a
    malformed manifest entry cannot crash the run.
    """
    if not filename:
        return
    name = Path(filename).name
    if not name or name in (".", ".."):
        return
    target = directory / name
    if target.is_file():
        target.unlink()
