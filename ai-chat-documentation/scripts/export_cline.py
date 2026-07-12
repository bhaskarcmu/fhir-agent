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


def stringify_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if not isinstance(content, list):
        return json.dumps(content, ensure_ascii=False, indent=2)

    sections: list[str] = []

    for block in content:
        if isinstance(block, str):
            sections.append(block)
            continue

        if not isinstance(block, dict):
            sections.append(json.dumps(block, ensure_ascii=False, indent=2))
            continue

        block_type = str(block.get("type", "")).lower()

        if block_type == "text":
            text = block.get("text", "")
            if text:
                sections.append(str(text))

        elif block_type == "thinking":
            # Deliberately omit private model reasoning from the readable export.
            sections.append("*[Model thinking block omitted]*")

        elif block_type == "tool_use":
            name = block.get("name", "tool")
            tool_input = block.get("input", {})
            sections.append(
                f"**Tool call: `{name}`**\n\n"
                f"```json\n{json.dumps(tool_input, ensure_ascii=False, indent=2)}\n```"
            )

        elif block_type == "tool_result":
            result = block.get("content", "")
            if isinstance(result, (dict, list)):
                result = json.dumps(result, ensure_ascii=False, indent=2)
            sections.append(f"**Tool result**\n\n```\n{result}\n```")

        else:
            sections.append(
                f"```json\n{json.dumps(block, ensure_ascii=False, indent=2)}\n```"
            )

    return "\n\n".join(section for section in sections if section).strip()


def metadata_title(metadata: Any, task_id: str) -> str:
    if isinstance(metadata, dict):
        for key in ("name", "title", "task", "description"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().splitlines()[0][:120]
    return f"Cline task {task_id}"


def safe_filename(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value[:70] or "cline-task"


def timestamp_from_task_id(task_id: str) -> dt.datetime | None:
    try:
        raw = int(task_id)
        if raw > 10_000_000_000:
            raw /= 1000
        return dt.datetime.fromtimestamp(raw, tz=dt.timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def markdown_escape_heading(value: str) -> str:
    return value.replace("\n", " ").replace("\r", " ").strip()


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

    # Loading first avoids archiving a file while Cline is part-way through writing it.
    try:
        messages = read_json(api_file)
    except (json.JSONDecodeError, OSError) as error:
        print(f"Skipping active or invalid task {task_id}: {error}", file=sys.stderr)
        return None

    if not isinstance(messages, list):
        print(f"Skipping task {task_id}: API history is not a list", file=sys.stderr)
        return None

    metadata: Any = {}
    if metadata_file.exists():
        try:
            metadata = read_json(metadata_file)
        except (json.JSONDecodeError, OSError):
            metadata = {}

    title = metadata_title(metadata, task_id)
    created = timestamp_from_task_id(task_id)
    year = str(created.year) if created else "unknown-year"
    month = f"{created.month:02d}" if created else "unknown-month"

    raw_destination = raw_root / year / month / task_id
    for source in (api_file, ui_file, metadata_file):
        if source.exists():
            atomic_copy(source, raw_destination / source.name)

    filename = f"{task_id}-{safe_filename(title)}.md"
    markdown_destination = markdown_root / year / month / filename
    markdown_destination.parent.mkdir(parents=True, exist_ok=True)

    output: list[str] = [
        f"# {markdown_escape_heading(title)}",
        "",
        f"- **Cline task ID:** `{task_id}`",
    ]

    if created:
        output.append(
            f"- **Approximate creation time:** "
            f"{created.strftime('%d %B %Y, %H:%M UTC')}"
        )

    output.extend(
        [
            f"- **Messages:** {len(messages)}",
            "",
            "---",
            "",
        ]
    )

    for number, message in enumerate(messages, start=1):
        if not isinstance(message, dict):
            continue

        role = str(message.get("role", "unknown")).lower()
        heading = {
            "user": "User",
            "assistant": "Cline",
            "system": "System",
        }.get(role, role.title() or "Message")

        content = stringify_content(message.get("content", ""))

        if not content:
            continue

        output.extend(
            [
                f"## {number}. {heading}",
                "",
                content,
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
        "This page is generated automatically. Select a conversation below to read "
        "it directly in GitHub.",
        "",
        f"**Archived conversations:** {len(records)}",
        "",
        "| Date | Conversation | Messages |",
        "|---|---|---:|",
    ]

    for record in records:
        date_text = "Unknown"
        if record["created"]:
            parsed = dt.datetime.fromisoformat(record["created"])
            date_text = parsed.strftime("%d %b %Y, %H:%M UTC")

        title = html.escape(record["title"]).replace("|", "\\|")
        lines.append(
            f"| {date_text} | [{title}]({record['path']}) | "
            f"{record['messages']} |"
        )

    lines.extend(
        [
            "",
            "## Archive notes",
            "",
            "- `markdown/` contains the readable GitHub versions.",
            "- `raw/` contains the original Cline JSON files.",
            "- Model thinking blocks are intentionally not reproduced in Markdown.",
            "- Tool calls and tool results may still contain project-sensitive data.",
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
        print(f"Cline tasks directory not found: {args.cline_tasks}", file=sys.stderr)
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
