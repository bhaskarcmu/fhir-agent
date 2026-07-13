"""Fixture builders that mimic Claude Code JSONL records."""

from __future__ import annotations

import json
from pathlib import Path

_T = "2026-07-13T10:{:02d}:00.000Z"


def ts(minute: int) -> str:
    return _T.format(minute)


def user_prompt(text: str, minute: int = 0, meta: bool = False) -> dict:
    return {
        "type": "user", "timestamp": ts(minute), "promptSource": "sdk", "isMeta": meta,
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    }


def assistant_text(text: str, minute: int = 1) -> dict:
    return {
        "type": "assistant", "timestamp": ts(minute),
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
    }


def assistant_thinking(text: str, minute: int = 1) -> dict:
    return {
        "type": "assistant", "timestamp": ts(minute),
        "message": {"role": "assistant", "content": [{"type": "thinking", "thinking": text}]},
    }


def assistant_tool_use(name: str, tool_input: dict, tid: str, minute: int = 1) -> dict:
    return {
        "type": "assistant", "timestamp": ts(minute),
        "message": {"role": "assistant",
                    "content": [{"type": "tool_use", "id": tid, "name": name, "input": tool_input}]},
    }


def tool_result(tid: str, content: str, minute: int = 1) -> dict:
    return {
        "type": "user", "timestamp": ts(minute), "toolUseResult": {"stdout": content},
        "message": {"role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": tid, "content": content}]},
    }


def sidechain_prompt(text: str, minute: int = 0) -> dict:
    rec = user_prompt(text, minute)
    rec["isSidechain"] = True
    return rec


def ai_title(title: str) -> dict:
    return {"type": "ai-title", "aiTitle": title}


def custom_title(title: str) -> dict:
    return {"type": "custom-title", "customTitle": title}


def noise() -> list[dict]:
    return [
        {"type": "queue-operation", "operation": "enqueue", "timestamp": ts(0)},
        {"type": "attachment", "timestamp": ts(0), "attachment": {"type": "x"}},
        {"type": "file-history-snapshot", "messageId": "m"},
        {"type": "pr-link", "prNumber": 1},
        {"type": "last-prompt", "lastPrompt": "..."},
    ]


def write_jsonl(path: Path, records: list[dict], trailing_partial: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r) for r in records]
    text = "\n".join(lines) + "\n"
    if trailing_partial:
        text += '{"type": "assistant", "message": {"content": [{"type": "te'  # cut off
    path.write_text(text, encoding="utf-8")
    return path
