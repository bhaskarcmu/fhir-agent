import subprocess
import tempfile
import unittest
from pathlib import Path

from archive_ai.publisher import Publisher, PublishError

BRANCH = "ai-chat-history"
SUBDIR = "ai-chat-documentation"


def git(cwd, *args, check=True):
    return subprocess.run(["git", "-C", str(cwd), *args],
                          capture_output=True, text=True, check=check)


def make_repo_with_remote() -> tuple[Path, Path]:
    """A work repo on ``ai-chat-history`` with an offline bare remote as origin."""
    root = Path(tempfile.mkdtemp())
    remote = root / "remote.git"
    work = root / "work"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", BRANCH, str(work)], check=True, capture_output=True)
    git(work, "config", "user.email", "test@example.com")
    git(work, "config", "user.name", "Test")
    git(work, "remote", "add", "origin", str(remote))
    (work / SUBDIR).mkdir()
    (work / SUBDIR / ".keep").write_text("", encoding="utf-8")
    git(work, "add", "-A")
    git(work, "commit", "-m", "init")
    git(work, "push", "-u", "origin", BRANCH)
    return work, remote


class PublisherTest(unittest.TestCase):
    def test_commit_and_push_then_noop_on_rerun(self):
        work, remote = make_repo_with_remote()
        pub = Publisher(work, SUBDIR, BRANCH)

        (work / SUBDIR / "INDEX.md").write_text("hello", encoding="utf-8")
        result = pub.publish("Archive test")
        self.assertEqual(result.status, "pushed")
        self.assertTrue(result.commit)
        # remote actually received the commit
        remote_log = subprocess.run(
            ["git", "-C", str(remote), "log", "-1", "--format=%s", BRANCH],
            capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(remote_log, "Archive test")

        # No changes -> no new commit.
        again = pub.publish("Archive test 2")
        self.assertEqual(again.status, "noop")

    def test_only_archive_subdir_is_staged(self):
        work, _ = make_repo_with_remote()
        pub = Publisher(work, SUBDIR, BRANCH)
        (work / SUBDIR / "INDEX.md").write_text("x", encoding="utf-8")
        (work / "outside.txt").write_text("should not be committed", encoding="utf-8")
        pub.publish("Archive only subdir")
        tracked = git(work, "ls-files").stdout.split()
        self.assertIn(f"{SUBDIR}/INDEX.md", tracked)
        self.assertNotIn("outside.txt", tracked)

    def test_refuses_wrong_branch(self):
        work, _ = make_repo_with_remote()
        git(work, "checkout", "-b", "main")
        pub = Publisher(work, SUBDIR, BRANCH)
        (work / SUBDIR / "INDEX.md").write_text("x", encoding="utf-8")
        with self.assertRaises(PublishError):
            pub.publish("should refuse")

    def test_rebase_conflict_aborts_keeps_local_commit_and_does_not_push(self):
        work, remote = make_repo_with_remote()
        clone = Path(tempfile.mkdtemp()) / "clone"
        subprocess.run(["git", "clone", str(remote), str(clone)], check=True, capture_output=True)
        git(clone, "checkout", BRANCH)
        git(clone, "config", "user.email", "test@example.com")
        git(clone, "config", "user.name", "Test")
        (clone / SUBDIR).mkdir(parents=True, exist_ok=True)
        (clone / SUBDIR / "INDEX.md").write_text("remote change\n", encoding="utf-8")
        git(clone, "add", "-A")
        git(clone, "commit", "-m", "remote archive change")
        git(clone, "push", "origin", BRANCH)

        (work / SUBDIR / "INDEX.md").write_text("local archive change\n", encoding="utf-8")
        pub = Publisher(work, SUBDIR, BRANCH)

        # commit-then-rebase: the local archive commit is created, then rebasing
        # onto the diverged remote conflicts -> abort + raise.
        with self.assertRaises(PublishError):
            pub.publish("Archive test")

        # Local archive commit is retained (init + archive = 2) for retry.
        self.assertEqual(git(work, "rev-list", "--count", "HEAD").stdout.strip(), "2")
        self.assertIn("local archive change", (work / SUBDIR / "INDEX.md").read_text(encoding="utf-8"))
        # Remote was not overwritten.
        remote_index = subprocess.run(
            ["git", "-C", str(remote), "show", f"{BRANCH}:{SUBDIR}/INDEX.md"],
            capture_output=True, text=True, check=True).stdout
        self.assertEqual(remote_index, "remote change\n")

    def test_updates_existing_tracked_file_across_runs(self):
        # Steady state: modifying an already-tracked archive file must still
        # publish. This is the case the pull-before-commit ordering broke.
        work, remote = make_repo_with_remote()
        pub = Publisher(work, SUBDIR, BRANCH)
        (work / SUBDIR / "INDEX.md").write_text("v1\n", encoding="utf-8")
        self.assertEqual(pub.publish("run1").status, "pushed")
        (work / SUBDIR / "INDEX.md").write_text("v2\n", encoding="utf-8")
        self.assertEqual(pub.publish("run2").status, "pushed")
        remote_index = subprocess.run(
            ["git", "-C", str(remote), "show", f"{BRANCH}:{SUBDIR}/INDEX.md"],
            capture_output=True, text=True, check=True).stdout
        self.assertEqual(remote_index, "v2\n")

    def test_missing_worktree_raises(self):
        pub = Publisher(Path("/nonexistent/worktree"), SUBDIR, BRANCH)
        with self.assertRaises(PublishError):
            pub.publish("nope")


if __name__ == "__main__":
    unittest.main()
