"""Render the normalised model to readable Markdown, plus filename/index helpers.

Ordering guarantee for a conversation: title -> per-turn prompt/response ->
collapsed tool detail -> metadata. Markdown filenames are a slug of the
(effective, redacted) title plus a short session-id suffix for uniqueness and
rename tracking. INDEX.md is built from the manifest so it includes retained
(source-deleted) sessions.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from .model import Conversation, parse_ts

INCOMPLETE = "*[Claude has not completed this turn yet.]*"
ARCHIVED_NOTE = "archived (source deleted)"
_MIN = datetime.min.replace(tzinfo=timezone.utc)


def slugify(text: str, maxlen: int = 60) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    if len(s) > maxlen:
        s = s[:maxlen].rstrip("-")
    return s or "untitled"


def markdown_filename(session_id: str, title: str) -> str:
    """``<title-slug>-<short-id>.md`` — readable and collision-proof."""
    return f"{slugify(title)}-{session_id[:8]}.md"


def _fmt(dt: datetime | None) -> str:
    if dt is None:
        return "unknown"
    return dt.strftime("%-d %B %Y, %H:%M UTC")


def render_markdown(conv: Conversation) -> str:
    lines: list[str] = [f"# {conv.title}", ""]

    for turn in conv.turns:
        lines += [f"## Turn {turn.index}", "", "### Prompt", "", turn.prompt.strip(), ""]
        lines += ["### Claude response", ""]
        lines += [turn.response.strip() if turn.status == "complete" else INCOMPLETE, ""]

    tool_turns = [t for t in conv.turns if t.tool_events]
    if tool_turns:
        total = sum(len(t.tool_events) for t in tool_turns)
        noun = "event" if total == 1 else "events"
        lines += ["<details>", f"<summary>Execution details — {total} tool {noun}</summary>", ""]
        for turn in tool_turns:
            lines.append(f"### Turn {turn.index} activity")
            lines.append("")
            for ev in turn.tool_events:
                summary = f" `{ev.input_summary}`" if ev.input_summary else ""
                lines.append(f"- **{ev.name}**{summary}")
            lines.append("")
        lines += ["</details>", ""]

    lines += [
        "---",
        "",
        "## Archive metadata",
        "",
        "- **Source:** Claude Code",
        f"- **Session ID:** `{conv.id}`",
        f"- **Created:** {_fmt(conv.created_at)}",
        f"- **Last updated:** {_fmt(conv.updated_at)}",
        f"- **Turns:** {len(conv.turns)}",
        f"- **Status:** {conv.status.capitalize()}",
        "",
    ]
    return "\n".join(lines)


def render_index(manifest: dict, markdown_subpath: str) -> str:
    """Render INDEX.md from the manifest (newest first, retained sessions kept)."""
    entries = sorted(
        manifest.values(),
        key=lambda e: parse_ts(e.get("updated_at")) or _MIN,
        reverse=True,
    )
    lines = [
        "# AI Conversation Index",
        "",
        f"{len(entries)} archived conversation(s), newest first.",
        "",
        "| Updated | Assistant | Conversation | Turns | Status |",
        "|---|---|---|---:|---|",
    ]
    for e in entries:
        link = f"{markdown_subpath}/{e.get('md_filename', '')}"
        title = str(e.get("title", "")).replace("|", "\\|")
        status = str(e.get("status", "")).capitalize()
        if not e.get("present", True):
            status = f"{status} · {ARCHIVED_NOTE}"
        lines.append(
            f"| {_fmt(parse_ts(e.get('updated_at')))} | Claude Code | [{title}]({link}) "
            f"| {e.get('turns', 0)} | {status} |"
        )
    lines.append("")
    return "\n".join(lines)
