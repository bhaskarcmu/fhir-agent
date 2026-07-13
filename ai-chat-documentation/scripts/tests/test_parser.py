import tempfile
import unittest
from pathlib import Path

import helpers as h
from archive_ai.parser import parse_session


def _parse(records, **kw):
    tmp = Path(tempfile.mkdtemp())
    path = h.write_jsonl(tmp / "sess-abc.jsonl", records, **kw)
    return parse_session(path)


class ParserTest(unittest.TestCase):
    def test_multi_turn_order_and_pairing(self):
        conv = _parse([
            h.ai_title("Fix the gateway"),
            h.user_prompt("First question", 0),
            h.assistant_text("First answer", 1),
            h.user_prompt("Second question", 2),
            h.assistant_text("Second answer", 3),
        ])
        self.assertEqual(conv.id, "sess-abc")
        self.assertEqual(conv.title, "Fix the gateway")
        self.assertEqual(len(conv.turns), 2)
        self.assertEqual(conv.turns[0].prompt, "First question")
        self.assertEqual(conv.turns[0].response, "First answer")
        self.assertEqual(conv.turns[1].prompt, "Second question")
        self.assertEqual(conv.status, "complete")

    def test_thinking_and_toolresult_never_become_turns(self):
        conv = _parse([
            h.user_prompt("Do a thing", 0),
            h.assistant_thinking("secret internal reasoning", 1),
            h.assistant_tool_use("Bash", {"command": "ls -la"}, "t1", 1),
            h.tool_result("t1", "file listing output", 2),
            h.assistant_text("Done.", 3),
        ])
        self.assertEqual(len(conv.turns), 1)
        turn = conv.turns[0]
        self.assertEqual(turn.response, "Done.")
        self.assertNotIn("internal reasoning", turn.response or "")
        self.assertEqual(len(turn.tool_events), 1)
        self.assertEqual(turn.tool_events[0].name, "Bash")
        self.assertEqual(turn.tool_events[0].input_summary, "ls -la")
        self.assertEqual(turn.tool_events[0].result_summary, "file listing output")

    def test_incomplete_trailing_turn(self):
        conv = _parse([
            h.user_prompt("Answered", 0),
            h.assistant_text("Yes", 1),
            h.user_prompt("Never answered", 2),
        ])
        self.assertEqual(len(conv.turns), 2)
        self.assertEqual(conv.turns[1].status, "incomplete")
        self.assertIsNone(conv.turns[1].response)
        self.assertEqual(conv.status, "incomplete")

    def test_prompt_containing_xml_regex_and_fences_is_literal(self):
        tricky = "Refactor <task>\\s*(.*?)\\s*</task> and keep ```py\ncode\n``` intact"
        conv = _parse([h.user_prompt(tricky, 0), h.assistant_text("ok", 1)])
        self.assertEqual(len(conv.turns), 1)
        self.assertEqual(conv.turns[0].prompt, tricky)

    def test_truncated_final_line_is_tolerated(self):
        conv = _parse(
            [h.user_prompt("Question", 0), h.assistant_text("Answer", 1)],
            trailing_partial=True,
        )
        self.assertEqual(len(conv.turns), 1)
        self.assertEqual(conv.turns[0].response, "Answer")

    def test_response_without_prompt_yields_no_turn(self):
        conv = _parse([h.assistant_text("orphan response", 1)])
        self.assertEqual(len(conv.turns), 0)
        self.assertEqual(conv.status, "empty")

    def test_sidechain_records_ignored(self):
        conv = _parse([
            h.sidechain_prompt("subagent prompt", 0),
            h.user_prompt("real prompt", 1),
            h.assistant_text("real answer", 2),
        ])
        self.assertEqual(len(conv.turns), 1)
        self.assertEqual(conv.turns[0].prompt, "real prompt")

    def test_noise_records_and_meta_user_ignored(self):
        records = h.noise() + [
            h.user_prompt("system injected", 0, meta=True),
            h.user_prompt("real", 1),
            h.assistant_text("ans", 2),
        ]
        conv = _parse(records)
        self.assertEqual(len(conv.turns), 1)
        self.assertEqual(conv.turns[0].prompt, "real")

    def test_title_falls_back_to_first_prompt_line(self):
        conv = _parse([h.user_prompt("A clear ask\nmore detail", 0), h.assistant_text("x", 1)])
        self.assertEqual(conv.title, "A clear ask")


if __name__ == "__main__":
    unittest.main()
