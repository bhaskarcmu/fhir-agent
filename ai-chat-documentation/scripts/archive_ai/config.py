"""Runtime configuration resolved from environment variables with defaults.

All paths and knobs live here so the rest of the package stays testable: tests
construct a Config pointing at temp directories instead of the real workspace.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

SOURCE_NAME = "claude-code"


def encode_cwd(path: str) -> str:
    """Encode a working-directory path the way Claude Code names project dirs.

    Every non-alphanumeric character becomes ``-`` so ``/workspaces/fhir-agent``
    -> ``-workspaces-fhir-agent`` and ``/workspaces/.ai-chat-history`` ->
    ``-workspaces--ai-chat-history``.
    """
    return re.sub(r"[^A-Za-z0-9]", "-", path)


@dataclass
class Config:
    # Where Claude Code stores sessions.
    projects_base: Path
    source_worktree: str
    conversation_dir_override: Path | None
    # Where the archive is written / committed.
    archive_worktree: Path
    archive_subdir: str
    branch: str
    remote: str
    # Behaviour.
    debounce_seconds: float

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Config":
        env = dict(os.environ if env is None else env)
        home = Path(env.get("HOME", str(Path.home())))
        override = env.get("CLAUDE_CONVERSATION_DIR")
        return cls(
            projects_base=Path(env.get("CLAUDE_PROJECTS_BASE", home / ".claude" / "projects")),
            source_worktree=env.get("ARCHIVE_SOURCE_WORKTREE", "/workspaces/fhir-agent"),
            conversation_dir_override=Path(override) if override else None,
            archive_worktree=Path(env.get("ARCHIVE_WORKTREE", "/workspaces/.ai-chat-history")),
            archive_subdir=env.get("ARCHIVE_SUBDIR", "ai-chat-documentation"),
            branch=env.get("ARCHIVE_BRANCH", "ai-chat-history"),
            remote=env.get("ARCHIVE_REMOTE", "origin"),
            debounce_seconds=float(env.get("AI_ARCHIVE_DEBOUNCE_SECONDS", "15")),
        )

    # --- derived paths -------------------------------------------------
    @property
    def archive_root(self) -> Path:
        return self.archive_worktree / self.archive_subdir

    @property
    def raw_dir(self) -> Path:
        return self.archive_root / "raw" / SOURCE_NAME

    @property
    def markdown_dir(self) -> Path:
        return self.archive_root / "markdown" / SOURCE_NAME

    @property
    def index_path(self) -> Path:
        return self.archive_root / "INDEX.md"

    @property
    def manifest_path(self) -> Path:
        return self.archive_root / "manifests" / f"{SOURCE_NAME}.json"

    @property
    def config_dir(self) -> Path:
        return self.archive_root / "config"

    @property
    def patterns_file(self) -> Path:
        return self.config_dir / "redaction-patterns.txt"

    @property
    def exclusions_file(self) -> Path:
        return self.config_dir / "exclusions.txt"

    @property
    def lock_file(self) -> Path:
        return self.archive_root / "logs" / "watcher.lock"

    def source_dir(self) -> Path:
        """The Claude Code project directory whose sessions we archive."""
        if self.conversation_dir_override is not None:
            return self.conversation_dir_override
        return self.projects_base / encode_cwd(self.source_worktree)

    def excluded_source_dir(self) -> Path:
        """The archive worktree's own project dir — never archive ourselves."""
        return self.projects_base / encode_cwd(str(self.archive_worktree))

    def load_exclusions(self) -> set[str]:
        return _read_lines(self.exclusions_file)


def _read_lines(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.add(line)
    return out
