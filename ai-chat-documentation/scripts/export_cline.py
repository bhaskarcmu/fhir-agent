#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any


SENSITIVE_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    shutil.copy2(source, temporary)
    os.replace(temporary, destination)


def contains_obvious_secret(value: str) -> bool:
    return any(pattern.search(value) for pattern in SENSITIVE_PATTERNS)


def timestamp_from_task_id(task_id: str) -> dt.datetime | None:
    try:
        raw = int(task_id)
        if raw > 10_000_000_000:
            raw /= 1000
        return dt.datetime.fromtimestamp(raw, tz=dt.timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def safe_filename(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")[:70] or "cline-task"


def normalise_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()

    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)

    if value is None:
        return ""

    return str(value).strip()


def strip_cline_wrappers(text: str) -> str:
    """
    Remove Cline-specific wrappers and automatically injected context from a
    human-authored prompt.
    """
    text = text.strip()

    task_match = re.search(r"<task>\s*(.*?)\s*</task>", text, re.DOTALL)
    if task_match:
        return task_match.group(1).strip()

    cut_markers = (
        "\n# task_progress RECOMMENDED",
        "\n<environment_details>",
    )

    for marker in cut_markers:
        if marker in text:
            text = text.split(marker, 1)[0].rstrip()

    return text


def first_human_prompt(messages: list[Any]) -> str:
    for message in messages:
        if not isinstance(message, dict):
            continue

        if str(message.get("role", "")).lower() != "user":
            continue

        content = message.get("content", "")

        if isinstance(content, str):
            candidate = strip_cline_wrappers(content)
            if candidate and not candidate.startswith("["):
                return candidate

        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "text":
                    continue

                candidate = strip_cline_wrappers(
                    normalise_text(block.get("text", ""))
                )
                if candidate and not candidate.startswith("["):
                    return candidate

    return "Cline development task"


def prompt_title(prompt: str, task_id: str) -> str:
    first_line = prompt.strip().splitlines()[0] if prompt.strip() else ""
    first_line = re.sub(r"\s+", " ", first_line).strip()

    if not first_line:
        return f"Cline task {task_id}"

    return first_line[:120]


def extract_tool_calls(messages: list[Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    for message in messages:
        if not isinstance(message, dict):
            continue

        content = message.get("content")
        if not isinstance(content, list):
            continue

        for block in content:
            if not isinstance(block, dict):
                continue

            if block.get("type") != "tool_use":
                continue

            calls.append(
                {
                    "name": str(block.get("name", "tool")),
                    "input": block.get("input", {}),
                }
            )

    return calls


def extract_final_response(messages: list[Any]) -> str:
    """
    Prefer Cline's attempt_completion result. Fall back to the last meaningful
    assistant text block.
    """
    fallback_texts: list[str] = []

    for message in messages:
        if not isinstance(message, dict):
            continue

        if str(message.get("role", "")).lower() != "assistant":
            continue

        content = message.get("content", "")

        if isinstance(content, str):
            text = content.strip()
            if text:
                fallback_texts.append(text)
            continue

        if not isinstance(content, list):
            continue

        for block in content:
            if not isinstance(block, dict):
                continue

            block_type = str(block.get("type", "")).lower()

            if block_type == "text":
                text = normalise_text(block.get("text", ""))
                if text:
                    fallback_texts.append(text)

            if block_type == "tool_use":
                name = str(block.get("name", ""))
                tool_input = block.get("input", {})

                if name == "attempt_completion" and isinstance(tool_input, dict):
                    result = normalise_text(tool_input.get("result", ""))
                    if result:
                        return result

    return fallback_texts[-1] if fallback_texts else "*No final response found.*"


def files_inspected(tool_calls: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []

    for call in tool_calls:
        name = call["name"]
        tool_input = call["input"]

        if name not in {"read_file", "list_files", "search_files"}:
            continue

        if not isinstance(tool_input, dict):
            continue

        path = tool_input.get("path")
        if isinstance(path, str) and path not in paths:
            paths.append(path)

    return paths


def render_tool_details(tool_calls: list[dict[str, Any]]) -> str:
    visible_calls = [
        call for call in tool_calls
        if call["name"] != "attempt_completion"
    ]

    if not visible_calls:
        return ""

    inspected = files_inspected(visible_calls)

    lines = [
        "<details>",
        f"<summary>Execution details — {len(visible_calls)} tool call(s)</summary>",
        "",
    ]

    if inspected:
        lines.extend(
            [
                "### Files inspected",
                "",
            ]
        )
        lines.extend(f"- `{path}`" for path in inspected)
        lines.append("")

    lines.extend(
        [
            "### Tool activity",
            "",
        ]
    )

    for index, call in enumerate(visible_calls, start=1):
        name = call["name"]
        tool_input = call["input"]

        lines.extend(
            [
                f"#### {index}. `{name}`",
                "",
                "```json",
                json.dumps(tool_input, ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )

    lines.extend(
        [
            "</details>",
            "",
        ]
    )

    return "\n".join(lines)


def export_task(
    task_dir: Path,
    raw_root: Path,
    markdown_root: Path,
) -> dict[str, str] | None:
    task_id = task_dir.name
    api_file = task_dir / "api_conversation_history.json"
    ui_file = task_dir / "ui_messages.json"
    metadata_file = task_dir / "task_metadata.json"

    if not api_file.exists():
        return None

    try:
        messages = read_json(api_file)
    except (json.JSONDecodeError, OSError) as error:
        print(
            f"Skipping active or invalid task {task_id}: {error}",
            file=sys.stderr,
        )
        return None

    if not isinstance(messages, list):
        print(
            f"Skipping task {task_id}: API history is not a list",
            file=sys.stderr,
        )
        return None

    created = timestamp_from_task_id(task_id)
    year = str(created.year) if created else "unknown-year"
    month = f"{created.month:02d}" if created else "unknown-month"

    raw_destination = raw_root / year / month / task_id

    for source in (api_file, ui_file, metadata_file):
        if source.exists():
            atomic_copy(source, raw_destination / source.name)

    prompt = first_human_prompt(messages)
    title = prompt_title(prompt, task_id)
    final_response = extract_final_response(messages)
    tool_calls = extract_tool_calls(messages)

    filename = f"{task_id}-{safe_filename(title)}.md"
    markdown_destination = markdown_root / year / month / filename
    markdown_destination.parent.mkdir(parents=True, exist_ok=True)

    output = [
        f"# {title}",
        "",
        "## Prompt",
        "",
        prompt,
        "",
        "## Final response",
        "",
        final_response,
        "",
    ]

    tool_details = render_tool_details(tool_calls)
    if tool_details:
        output.append(tool_details.rstrip())
        output.append("")

    output.extend(
        [
            "---",
            "",
            "## Archive metadata",
            "",
            f"- **Cline task ID:** `{task_id}`",
        ]
    )

    if created:
        output.append(
            "- **Approximate creation time:** "
            f"{created.strftime('%d %B %Y, %H:%M UTC')}"
        )

    output.extend(
        [
            f"- **Stored API messages:** {len(messages)}",
            f"- **Recorded tool calls:** "
            f"{len([c for c in tool_calls if c['name'] != 'attempt_completion'])}",
            "",
            (
                "The complete original Cline records are retained in the "
                "corresponding `raw/` directory."
            ),
            "",
        ]
    )

    rendered = "\n".join(output).rstrip() + "\n"

    if contains_obvious_secret(rendered):
        raise RuntimeError(
            f"Possible credential detected in task {task_id}; refusing to export"
        )

    temporary = markdown_destination.with_suffix(".md.partial")
    temporary.write_text(rendered, encoding="utf-8")
    os.replace(temporary, markdown_destination)

    relative = markdown_destination.relative_to(markdown_root.parent)

    return {
        "task_id": task_id,
        "title": title,
        "created": created.isoformat() if created else "",
        "path": relative.as_posix(),
        "messages": str(len(messages)),
    }


def build_index(records: list[dict[str, str]], archive_root: Path) -> None:
    records.sort(
        key=lambda record: (record["created"], record["task_id"]),
        reverse=True,
    )

    lines = [
        "# Cline Conversation Archive",
        "",
        (
            "Open a conversation below to see the original prompt and Claude's "
            "final response. Execution details are collapsed by default."
        ),
        "",
        f"**Archived conversations:** {len(records)}",
        "",
        "| Date | Conversation |",
        "|---|---|",
    ]

    for record in records:
        date_text = "Unknown"

        if record["created"]:
            parsed = dt.datetime.fromisoformat(record["created"])
            date_text = parsed.strftime("%d %b %Y, %H:%M UTC")

        title = html.escape(record["title"]).replace("|", "\\|")
        lines.append(
            f"| {date_text} | [{title}]({record['path']}) |"
        )

    lines.extend(
        [
            "",
            "## Archive notes",
            "",
            "- `markdown/` contains the readable GitHub versions.",
            "- `raw/` contains the complete original Cline records.",
            "- Execution details are collapsed in each readable document.",
            "- Internal tool results are not repeated in the readable document.",
            "",
        ]
    )

    destination = archive_root / "INDEX.md"
    temporary = destination.with_suffix(".md.partial")
    temporary.write_text("\n".join(lines), encoding="utf-8")
    os.replace(temporary, destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cline-tasks", required=True, type=Path)
    parser.add_argument("--archive-root", required=True, type=Path)
    args = parser.parse_args()

    if not args.cline_tasks.is_dir():
        print(
            f"Cline tasks directory not found: {args.cline_tasks}",
            file=sys.stderr,
        )
        return 2

    raw_root = args.archive_root / "raw"
    markdown_root = args.archive_root / "markdown"

    raw_root.mkdir(parents=True, exist_ok=True)
    markdown_root.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, str]] = []

    for task_dir in sorted(args.cline_tasks.iterdir()):
        if not task_dir.is_dir():
            continue

        try:
            record = export_task(task_dir, raw_root, markdown_root)
            if record:
                records.append(record)
        except RuntimeError as error:
            print(error, file=sys.stderr)
            return 3

    build_index(records, args.archive_root)
    print(f"Exported {len(records)} Cline task(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
