import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import helpers as h
from archive_ai import cli
from archive_ai.config import Config
from archive_ai.renderer import markdown_filename
from test_publisher import make_repo_with_remote


def make_config(source: Path, work: Path) -> Config:
    return Config(
        projects_base=Path(tempfile.mkdtemp()),
        source_worktree="/workspaces/fhir-agent",
        conversation_dir_override=source,
        archive_worktree=work,
        archive_subdir="ai-chat-documentation",
        branch="ai-chat-history",
        remote="origin",
        debounce_seconds=1,
    )


class EndToEndTest(unittest.TestCase):
    def setUp(self):
        self.source = Path(tempfile.mkdtemp())
        h.write_jsonl(self.source / "sess-good.jsonl", [
            h.ai_title("Gateway work"),
            h.user_prompt("Review the config", 0),
            h.assistant_tool_use("Read", {"file_path": "gateway/kong.yaml"}, "t1", 1),
            h.tool_result("t1", "contents", 1),
            h.assistant_text("Looks fine.", 2),
            h.user_prompt("Now implement", 3),
            h.assistant_text("Implemented.", 4),
        ])
        h.write_jsonl(self.source / "sess-secret.jsonl", [
            h.user_prompt("my key is sk-ant-api03-SECRET1234567890abcdef please store it", 0),
            h.assistant_text("noted", 1),
        ])
        self.work, self.remote = make_repo_with_remote()
        self.config = make_config(self.source, self.work)
        self.base = self.work / "ai-chat-documentation"
        self.mdd = self.base / "markdown" / "claude-code"
        self.rawd = self.base / "raw" / "claude-code"

    def _run_sync(self):
        return cli.cmd_sync(self.config)

    def _remote_log(self):
        return subprocess.run(
            ["git", "-C", str(self.remote), "log", "--oneline", "ai-chat-history"],
            capture_output=True, text=True, check=True).stdout.strip().splitlines()

    def test_full_sync_slug_filenames_commit_and_idempotent(self):
        self.assertEqual(self._run_sync(), 0)
        md = self.mdd / markdown_filename("sess-good", "Gateway work")
        self.assertEqual(md.name, "gateway-work-sess-goo.md")
        self.assertTrue(md.exists())
        self.assertTrue((self.rawd / "sess-good.jsonl").exists())
        self.assertTrue((self.base / "manifests" / "claude-code.json").exists())

        text = md.read_text(encoding="utf-8")
        self.assertEqual(text.count("### Prompt"), 2)
        self.assertNotIn("contents", text.split("<details>")[0])
        self.assertIn("[Gateway work](markdown/claude-code/gateway-work-sess-goo.md)",
                      (self.base / "INDEX.md").read_text(encoding="utf-8"))

        self.assertEqual(len(self._remote_log()), 2)          # init + one archive commit
        self.assertEqual(self._run_sync(), 0)                 # rerun, no source change
        self.assertEqual(len(self._remote_log()), 2)          # -> no new commit

    def test_secret_redacted_in_markdown_raw_and_filename(self):
        self._run_sync()
        secret = "sk-ant-api03-SECRET1234567890abcdef"
        md = next(self.mdd.glob("*-sess-sec.md"))
        raw = self.rawd / "sess-secret.jsonl"
        self.assertNotIn(secret, md.read_text(encoding="utf-8"))
        self.assertNotIn(secret, raw.read_text(encoding="utf-8"))
        self.assertNotIn(secret, md.name)  # slug comes from the redacted title

    def test_rename_moves_markdown_and_updates_index(self):
        h.write_jsonl(self.source / "sess-ren.jsonl", [
            h.ai_title("Old Title"), h.user_prompt("hi", 0), h.assistant_text("yo", 1)])
        self._run_sync()
        old = self.mdd / markdown_filename("sess-ren", "Old Title")
        self.assertTrue(old.exists())

        with open(self.source / "sess-ren.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(h.custom_title("New Name")) + "\n")
        self._run_sync()

        new = self.mdd / markdown_filename("sess-ren", "New Name")
        self.assertTrue(new.exists())
        self.assertFalse(old.exists(), "old-named markdown must be removed on rename")
        idx = (self.base / "INDEX.md").read_text(encoding="utf-8")
        self.assertIn("[New Name]", idx)
        self.assertNotIn("[Old Title]", idx)

    def test_deleted_session_is_retained_and_indexed(self):
        self._run_sync()
        md = self.mdd / markdown_filename("sess-good", "Gateway work")
        self.assertTrue(md.exists())

        (self.source / "sess-good.jsonl").unlink()   # delete in "Claude Code"
        self._run_sync()

        self.assertTrue(md.exists(), "deleted session's markdown must be retained")
        self.assertTrue((self.rawd / "sess-good.jsonl").exists(), "raw must be retained")
        idx = (self.base / "INDEX.md").read_text(encoding="utf-8")
        self.assertIn("[Gateway work]", idx)
        self.assertIn("archived (source deleted)", idx)

    def _manifest_path(self):
        return self.base / "manifests" / "claude-code.json"

    def _write_manifest(self, data):
        self._manifest_path().parent.mkdir(parents=True, exist_ok=True)
        self._manifest_path().write_text(json.dumps(data), encoding="utf-8")

    def test_exclusion_purge_tolerates_legacy_entry_without_md_filename(self):
        # Regression (High): a malformed/legacy manifest entry lacking
        # md_filename must not crash the exclusion purge (was: unlink on a dir).
        self._write_manifest({"sess-secret": {"present": True, "raw_filename": "sess-secret.jsonl"}})
        self.rawd.mkdir(parents=True, exist_ok=True)
        (self.rawd / "sess-secret.jsonl").write_text("{}\n", encoding="utf-8")
        cfg_dir = self.base / "config"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / "exclusions.txt").write_text("sess-secret\n", encoding="utf-8")

        self.assertEqual(self._run_sync(), 0)  # must not raise
        self.assertFalse((self.rawd / "sess-secret.jsonl").exists())
        self.assertTrue(self.mdd.is_dir())  # directory intact, not unlinked
        self.assertNotIn("sess-secret", json.loads(self._manifest_path().read_text()))

    def test_heal_regenerates_missing_markdown_from_raw(self):
        # Regression (Medium): a retained entry whose markdown was deleted is
        # rebuilt from the redacted raw copy, so the INDEX link resolves.
        self._run_sync()
        md = self.mdd / markdown_filename("sess-good", "Gateway work")
        self.assertTrue(md.exists())

        (self.source / "sess-good.jsonl").unlink()  # delete source -> retained
        md.unlink()                                 # and lose the markdown
        self._run_sync()

        healed = self.mdd / markdown_filename("sess-good", "Gateway work")
        self.assertTrue(healed.exists(), "markdown must be regenerated from raw")
        self.assertIn("# Gateway work", healed.read_text(encoding="utf-8"))
        idx = (self.base / "INDEX.md").read_text(encoding="utf-8")
        link = f"markdown/claude-code/{healed.name}"
        self.assertIn(link, idx)
        self.assertTrue((self.base / link).exists(), "INDEX link must resolve")

    def test_heal_drops_unrecoverable_entry(self):
        # A retained entry with neither markdown nor raw is dropped (no broken link).
        self._run_sync()
        m = json.loads(self._manifest_path().read_text())
        m["ghost"] = {"title": "Ghost", "md_filename": "ghost-ghost.md",
                      "raw_filename": "ghost.jsonl", "updated_at": None,
                      "turns": 1, "status": "complete", "present": False}
        self._write_manifest(m)
        self._run_sync()
        after = json.loads(self._manifest_path().read_text())
        self.assertNotIn("ghost", after)
        self.assertNotIn("ghost-ghost.md", (self.base / "INDEX.md").read_text(encoding="utf-8"))

    def test_exclusion_prevents_and_purges_archive(self):
        self._run_sync()
        self.assertTrue(list(self.mdd.glob("*-sess-sec.md")))  # archived initially

        cfg_dir = self.base / "config"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / "exclusions.txt").write_text("sess-secret\n", encoding="utf-8")
        self._run_sync()

        self.assertFalse(list(self.mdd.glob("*-sess-sec.md")), "excluded md must be purged")
        self.assertFalse((self.rawd / "sess-secret.jsonl").exists(), "excluded raw must be purged")
        self.assertTrue((self.mdd / markdown_filename("sess-good", "Gateway work")).exists())


if __name__ == "__main__":
    unittest.main()
