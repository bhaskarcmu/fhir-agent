import unittest

from archive_ai.model import Conversation, ToolEvent, Turn, parse_ts
from archive_ai.renderer import (
    INCOMPLETE,
    markdown_filename,
    render_index,
    render_markdown,
    slugify,
)


def _conv():
    return Conversation(
        id="sess-1", source="claude-code", title="Improve gateway",
        created_at=parse_ts("2026-07-13T10:42:00Z"),
        updated_at=parse_ts("2026-07-13T11:18:00Z"),
        turns=[
            Turn(index=1, prompt="Review the config", response="The config...",
                 tool_events=[ToolEvent("Read", "gateway/kong.yaml")]),
            Turn(index=2, prompt="Implement it", response=None),
        ],
    )


class RenderMarkdownTest(unittest.TestCase):
    def test_section_ordering(self):
        md = render_markdown(_conv())
        pos = {s: md.index(s) for s in
               ["# Improve gateway", "### Prompt", "### Claude response",
                "<details>", "## Archive metadata"]}
        self.assertLess(pos["# Improve gateway"], pos["### Prompt"])
        self.assertLess(pos["### Claude response"], pos["<details>"])
        self.assertLess(pos["<details>"], pos["## Archive metadata"])

    def test_incomplete_marker_and_status(self):
        md = render_markdown(_conv())
        self.assertIn(INCOMPLETE, md)
        self.assertIn("**Status:** Incomplete", md)

    def test_tool_details_collapsed_after_response(self):
        md = render_markdown(_conv())
        self.assertIn("<summary>Execution details — 1 tool event</summary>", md)
        self.assertIn("- **Read** `gateway/kong.yaml`", md)
        self.assertGreater(md.index("gateway/kong.yaml"), md.index("The config..."))


class SlugTest(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(slugify("Implement Auto-Pushes of AI Chats!"),
                         "implement-auto-pushes-of-ai-chats")
        self.assertEqual(slugify("  multiple   spaces  "), "multiple-spaces")
        self.assertEqual(slugify(""), "untitled")
        self.assertEqual(slugify("‹redacted:anthropic-key›"), "redacted-anthropic-key")

    def test_markdown_filename_has_title_and_short_id(self):
        self.assertEqual(
            markdown_filename("b19190df-fadc-43a7", "Gateway Work"),
            "gateway-work-b19190df.md",
        )

    def test_slugify_truncates(self):
        self.assertLessEqual(len(slugify("word " * 40)), 60)


class RenderIndexTest(unittest.TestCase):
    def _manifest(self, present=True):
        return {
            "sess-1": {
                "title": "Improve gateway",
                "md_filename": "improve-gateway-sess-1.md",
                "updated_at": "2026-07-13T11:18:00+00:00",
                "turns": 2, "status": "complete", "present": present,
            }
        }

    def test_rows_and_link(self):
        idx = render_index(self._manifest(), "markdown/claude-code")
        self.assertIn("| Updated | Assistant | Conversation | Turns | Status |", idx)
        self.assertIn("[Improve gateway](markdown/claude-code/improve-gateway-sess-1.md)", idx)
        self.assertIn("Claude Code", idx)

    def test_archived_sessions_marked(self):
        idx = render_index(self._manifest(present=False), "markdown/claude-code")
        self.assertIn("archived (source deleted)", idx)

    def test_present_sessions_not_marked(self):
        idx = render_index(self._manifest(present=True), "markdown/claude-code")
        self.assertNotIn("archived (source deleted)", idx)

    def test_escapes_pipes_in_title(self):
        m = {"x": {"title": "a | b", "md_filename": "a-b-x.md",
                   "updated_at": None, "turns": 1, "status": "complete", "present": True}}
        idx = render_index(m, "markdown/claude-code")
        self.assertIn("a \\| b", idx)

    def test_newest_first(self):
        m = {
            "old": {"title": "Old", "md_filename": "old-old.md",
                    "updated_at": "2026-07-01T00:00:00+00:00", "turns": 1,
                    "status": "complete", "present": True},
            "new": {"title": "New", "md_filename": "new-new.md",
                    "updated_at": "2026-07-13T00:00:00+00:00", "turns": 1,
                    "status": "complete", "present": True},
        }
        idx = render_index(m, "markdown/claude-code")
        self.assertLess(idx.index("[New]"), idx.index("[Old]"))


if __name__ == "__main__":
    unittest.main()
