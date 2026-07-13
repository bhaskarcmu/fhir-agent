import subprocess
import tempfile
import unittest
from pathlib import Path

import helpers as h
from archive_ai import cli, pipeline
from archive_ai.config import Config
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

    def _run_sync(self):
        return cli.cmd_sync(self.config)

    def test_full_sync_writes_commits_and_is_idempotent(self):
        rc = self._run_sync()
        self.assertEqual(rc, 0)
        md = self.work / "ai-chat-documentation" / "markdown" / "claude-code" / "sess-good.md"
        raw = self.work / "ai-chat-documentation" / "raw" / "claude-code" / "sess-good.jsonl"
        index = self.work / "ai-chat-documentation" / "INDEX.md"
        self.assertTrue(md.exists() and raw.exists() and index.exists())

        text = md.read_text(encoding="utf-8")
        self.assertEqual(text.count("### Prompt"), 2)          # both prompts once
        self.assertIn("Review the config", text)
        self.assertIn("Now implement", text)
        self.assertNotIn("contents", text.split("<details>")[0])  # tool output not before response
        self.assertIn("[Gateway work]", index.read_text(encoding="utf-8"))

        # exactly one commit landed on the remote
        log = subprocess.run(["git", "-C", str(self.remote), "log", "--oneline", "ai-chat-history"],
                             capture_output=True, text=True, check=True).stdout.strip().splitlines()
        self.assertEqual(len(log), 2)  # init + one archive commit

        # rerun with no source change -> no new commit
        self.assertEqual(self._run_sync(), 0)
        log2 = subprocess.run(["git", "-C", str(self.remote), "log", "--oneline", "ai-chat-history"],
                              capture_output=True, text=True, check=True).stdout.strip().splitlines()
        self.assertEqual(len(log2), 2)

    def test_secret_redacted_in_markdown_and_raw(self):
        self._run_sync()
        base = self.work / "ai-chat-documentation"
        md = (base / "markdown" / "claude-code" / "sess-secret.md").read_text(encoding="utf-8")
        raw = (base / "raw" / "claude-code" / "sess-secret.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("sk-ant-api03-SECRET1234567890abcdef", md)
        self.assertNotIn("sk-ant-api03-SECRET1234567890abcdef", raw)
        self.assertIn("‹redacted:anthropic-key›", md)

    def test_excluded_session_is_not_archived(self):
        cfg_dir = self.work / "ai-chat-documentation" / "config"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / "exclusions.txt").write_text("sess-secret\n", encoding="utf-8")
        self._run_sync()
        base = self.work / "ai-chat-documentation"
        self.assertFalse((base / "markdown" / "claude-code" / "sess-secret.md").exists())
        self.assertTrue((base / "markdown" / "claude-code" / "sess-good.md").exists())


if __name__ == "__main__":
    unittest.main()
