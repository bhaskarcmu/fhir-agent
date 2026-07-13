"""Render the normalised model to readable Markdown and the index.

Ordering guarantee: title -> per-turn prompt/response -> collapsed tool detail
-> metadata. Large tool output never precedes the response.
"""

from __future__ import annotations

from datetime import datetime

from .model import Conversation

INCOMPLETE = "*[Claude has not completed this turn yet.]*"


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


def render_index(conversations: list[Conversation], markdown_subpath: str) -> str:
    """Render INDEX.md. ``markdown_subpath`` is the dir prefix for links."""
    ordered = sorted(
        conversations,
        key=lambda c: c.updated_at or datetime.min.replace(tzinfo=None),
        reverse=True,
    )
    lines = [
        "# AI Conversation Index",
        "",
        f"{len(ordered)} archived conversation(s), newest first.",
        "",
        "| Updated | Assistant | Conversation | Turns | Status |",
        "|---|---|---|---:|---|",
    ]
    for conv in ordered:
        link = f"{markdown_subpath}/{conv.id}.md"
        title = conv.title.replace("|", "\\|")
        lines.append(
            f"| {_fmt(conv.updated_at)} | Claude Code | [{title}]({link}) "
            f"| {len(conv.turns)} | {conv.status.capitalize()} |"
        )
    lines.append("")
    return "\n".join(lines)
