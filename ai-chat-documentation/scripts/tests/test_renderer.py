import unittest

from archive_ai.model import Conversation, ToolEvent, Turn, parse_ts
from archive_ai.renderer import INCOMPLETE, render_index, render_markdown


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


class RendererTest(unittest.TestCase):
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

    def test_index_rows_and_link(self):
        idx = render_index([_conv()], "markdown/claude-code")
        self.assertIn("| Updated | Assistant | Conversation | Turns | Status |", idx)
        self.assertIn("[Improve gateway](markdown/claude-code/sess-1.md)", idx)
        self.assertIn("Claude Code", idx)

    def test_index_escapes_pipes_in_title(self):
        c = _conv()
        c.title = "a | b"
        idx = render_index([c], "markdown/claude-code")
        self.assertIn("a \\| b", idx)


if __name__ == "__main__":
    unittest.main()
