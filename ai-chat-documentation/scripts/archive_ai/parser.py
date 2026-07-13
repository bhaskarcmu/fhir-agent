"""Parse a Claude Code session ``.jsonl`` into the normalised model.

Classification is deterministic off typed fields — no regex prompt extraction:

* visible prompt  = ``type=="user"`` whose first content block is ``text``
* response        = following ``assistant`` ``text`` blocks, until next prompt
* tool event      = ``assistant`` ``tool_use`` paired to its ``tool_result``

Everything else (thinking, tool_result, queue-operation, attachment,
file-history-snapshot, ai-title/last-prompt/custom-title, pr-link, sidechains)
never starts a turn.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import SOURCE_NAME
from .model import Conversation, ToolEvent, Turn, parse_ts

_MAX_SUMMARY = 200


def parse_session(path: Path) -> Conversation:
    records = _read_records(path)
    session_id = path.stem
    title = _extract_title(records)

    turns: list[Turn] = []
    current: Turn | None = None
    pending_tools: dict[str, ToolEvent] = {}
    first_ts = last_ts = None

    for rec in records:
        rtype = rec.get("type")
        ts = parse_ts(rec.get("timestamp"))
        if ts is not None:
            first_ts = first_ts or ts
            last_ts = ts

        if rec.get("isSidechain"):
            continue

        if rtype == "user":
            blocks = _content_blocks(rec)
            first = blocks[0] if blocks else {}
            kind = first.get("type")
            if kind == "text" and not rec.get("isMeta"):
                text = _join_text(blocks)
                if text.strip():
                    current = Turn(index=len(turns) + 1, prompt=text, started_at=ts)
                    turns.append(current)
                    pending_tools = {}
                    continue
            if kind == "tool_result" and current is not None:
                tool = pending_tools.get(first.get("tool_use_id"))
                if tool is not None:
                    tool.result_summary = _summarise_result(first.get("content"))
            # any other user content is ignored
            continue

        if rtype == "assistant" and current is not None:
            parts: list[str] = []
            for block in _content_blocks(rec):
                btype = block.get("type")
                if btype == "text":
                    parts.append(block.get("text", ""))
                elif btype == "tool_use":
                    event = ToolEvent(
                        name=block.get("name", "tool"),
                        input_summary=_summarise_input(block.get("name"), block.get("input")),
                        timestamp=ts,
                    )
                    current.tool_events.append(event)
                    if block.get("id"):
                        pending_tools[block["id"]] = event
                # thinking blocks are intentionally dropped
            if parts:
                segment = "\n".join(parts)
                current.response = (
                    f"{current.response}\n\n{segment}" if current.response else segment
                ).strip() or None
            current.completed_at = ts
        # all other record types are ignored

    if not title and turns:
        title = _first_line(turns[0].prompt)

    return Conversation(
        id=session_id,
        source=SOURCE_NAME,
        title=title or session_id,
        created_at=first_ts,
        updated_at=last_ts,
        turns=turns,
    )


# --- helpers -----------------------------------------------------------

def _read_records(path: Path) -> list[dict]:
    """Read JSONL records, tolerating a partial final line (active session)."""
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue  # partial/corrupt line — skip, never fatal
        if isinstance(obj, dict):
            records.append(obj)
    return records


def _content_blocks(rec: dict) -> list[dict]:
    content = rec.get("message", {}).get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]
    return []


def _join_text(blocks: list[dict]) -> str:
    return "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()


def _extract_title(records: list[dict]) -> str | None:
    custom = ai = None
    for rec in records:
        if rec.get("type") == "custom-title" and rec.get("customTitle"):
            custom = rec["customTitle"]
        elif rec.get("type") == "ai-title" and rec.get("aiTitle"):
            ai = rec["aiTitle"]
    return custom or ai


def _first_line(text: str, limit: int = 80) -> str:
    line = text.strip().splitlines()[0] if text.strip() else ""
    return line[:limit].strip() or "Untitled conversation"


def _summarise_input(name: str | None, data) -> str | None:
    if not isinstance(data, dict):
        return None
    for key in ("command", "file_path", "path", "pattern", "query", "url", "description"):
        if data.get(key):
            return _clip(str(data[key]))
    try:
        return _clip(json.dumps(data, ensure_ascii=False))
    except (TypeError, ValueError):
        return None


def _summarise_result(content) -> str | None:
    if isinstance(content, list):
        text = " ".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    else:
        text = str(content) if content is not None else ""
    text = text.strip().replace("\n", " ")
    return _clip(text) if text else None


def _clip(text: str, limit: int = _MAX_SUMMARY) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "…"
