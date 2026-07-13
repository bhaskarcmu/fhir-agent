"""Git publishing: auto-commit and auto-push to the archive branch.

Strictly scoped: all git runs through ``git -C <archive worktree>`` and stage
only the archive subdir. Structurally incapable of opening a PR or touching
another branch. On push failure the local commit is kept for retry; never
force-pushes.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class PublishError(RuntimeError):
    pass


@dataclass
class PublishResult:
    status: str  # "noop" | "pushed" | "push_failed"
    commit: str | None = None
    detail: str = ""


class Publisher:
    def __init__(self, worktree: Path, subdir: str, branch: str, remote: str = "origin"):
        self.worktree = Path(worktree)
        self.subdir = subdir
        self.branch = branch
        self.remote = remote

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(self.worktree), *args],
            capture_output=True, text=True, check=check,
        )

    def current_branch(self) -> str:
        return self._git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

    def _has_upstream(self) -> bool:
        return self._git(
            "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False
        ).returncode == 0

    def _staged_empty(self) -> bool:
        # diff --cached --quiet exits 0 when there is nothing staged.
        return self._git("diff", "--cached", "--quiet", check=False).returncode == 0

    def publish(self, commit_message: str) -> PublishResult:
        if not self.worktree.exists():
            raise PublishError(f"Archive worktree missing: {self.worktree}")
        actual = self.current_branch()
        if actual != self.branch:
            raise PublishError(
                f"Refusing to publish: on branch '{actual}', expected '{self.branch}'."
            )

        self._git("add", "--", self.subdir)
        if self._staged_empty():
            return PublishResult(status="noop", detail="no changes to commit")

        self._git("commit", "-m", commit_message)
        commit = self._git("rev-parse", "HEAD").stdout.strip()

        # Converge with remote AFTER committing: rebase requires a clean tree,
        # and the pipeline has already written the regenerated files. This
        # replays our archive commit onto the latest upstream so we never push
        # diverged history; on genuine conflict, abort and keep the local commit
        # for manual resolution / next-run retry.
        if self._has_upstream():
            rebase = self._git("pull", "--rebase", self.remote, self.branch, check=False)
            if rebase.returncode != 0:
                self._git("rebase", "--abort", check=False)
                raise PublishError(
                    f"Rebase conflict while pulling {self.remote}/{self.branch}; "
                    f"local commit {commit[:8]} kept. Resolve manually before publishing."
                )

        push = self._git("push", self.remote, self.branch, check=False)
        if push.returncode != 0:
            return PublishResult(
                status="push_failed", commit=commit,
                detail=(push.stderr or push.stdout).strip(),
            )
        return PublishResult(status="pushed", commit=commit)
