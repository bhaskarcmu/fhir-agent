"""Locate the Claude Code session files to archive."""

from __future__ import annotations

from pathlib import Path

from .config import Config


class DiscoveryError(RuntimeError):
    pass


def find_sessions(config: Config) -> list[Path]:
    """Return the session ``.jsonl`` files for the configured source dir.

    Fails loudly if no source directory is found. Never returns files from the
    archive worktree's own project dir.
    """
    source = config.source_dir()
    if not source.exists():
        raise DiscoveryError(
            f"No Claude Code conversation directory at {source}. "
            f"Set CLAUDE_CONVERSATION_DIR to override."
        )
    excluded = config.excluded_source_dir().resolve()
    if source.resolve() == excluded:
        raise DiscoveryError(
            f"Refusing to archive the archive worktree's own conversations ({source})."
        )
    return sorted(source.glob("*.jsonl"))
