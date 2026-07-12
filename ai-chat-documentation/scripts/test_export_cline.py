#!/usr/bin/env python3
"""
Lightweight test (no external test framework required) for export_cline.py's
multi-turn extraction logic.

Run directly:
    python3 scripts/test_export_cline.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from export_cline import build_turns  # noqa: E402


def make_synthetic_messages() -> list[dict]:
    return [
        # Genuine human prompt #1, wrapped in <task>, plus injected noise.
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "<task>\nSummarize the repo architecture\n</task>"},
                {"type": "text", "text": "\n# task_progress RECOMMENDED\n\nSome reminder text.\n"},
                {"type": "text", "text": "<environment_details>\n# Current Time\nnow\n</environment_details>"},
            ],
            "ts": 1,
        },
        # Assistant does some tool calls (not a genuine prompt or response).
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "t1", "name": "read_file", "input": {"path": "README.md"}},
            ],
            "ts": 2,
        },
        # Tool result comes back as a "user" message - must NOT be treated as a prompt.
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "[read_file for 'README.md'] Result:\n1 | # Title\n"},
                {"type": "text", "text": "<environment_details>\n# Current Time\nnow\n</environment_details>"},
            ],
            "ts": 3,
        },
        # Assistant gives attempt_completion #1 - the response to prompt #1.
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "t2", "name": "attempt_completion", "input": {"result": "Here is the summary."}},
            ],
            "ts": 4,
        },
        # attempt_completion tool result + genuine feedback (prompt #2), plus noise.
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "[attempt_completion] Result: Done"},
                {"type": "text", "text": "The user has provided feedback on the results. Consider their input to continue the task, and then attempt completion again."},
                {"type": "text", "text": "<feedback>\nAlso mention third-party components\n</feedback>"},
                {"type": "text", "text": "\n# task_progress RECOMMENDED\n\nSome reminder text.\n"},
                {"type": "text", "text": "<environment_details>\n# Current Time\nnow\n</environment_details>"},
            ],
            "ts": 5,
        },
        # Assistant gives attempt_completion #2 - the response to prompt #2.
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "t3", "name": "attempt_completion", "input": {"result": "Here is the updated summary with third-party components."}},
            ],
            "ts": 6,
        },
    ]


def main() -> int:
    messages = make_synthetic_messages()
    turns = build_turns(messages)

    assert len(turns) == 2, f"Expected exactly 2 turns, got {len(turns)}: {turns}"

    assert turns[0]["prompt"] == "Summarize the repo architecture", turns[0]["prompt"]
    assert turns[0]["response"] == "Here is the summary.", turns[0]["response"]

    assert turns[1]["prompt"] == "Also mention third-party components", turns[1]["prompt"]
    assert turns[1]["response"] == "Here is the updated summary with third-party components.", turns[1]["response"]

    # Also verify an in-progress turn (no attempt_completion yet) is handled.
    in_progress_messages = messages + [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "<feedback>\nOne more thing please\n</feedback>"},
            ],
            "ts": 7,
        }
    ]
    in_progress_turns = build_turns(in_progress_messages)
    assert len(in_progress_turns) == 3
    assert in_progress_turns[2]["response"] is None

    print("OK: export_cline.build_turns produced exactly 2 complete turns "
          "(and correctly handled a 3rd, not-yet-completed turn).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
