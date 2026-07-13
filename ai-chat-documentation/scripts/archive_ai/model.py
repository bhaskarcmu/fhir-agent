"""Normalised conversation model shared by parser and renderer.

The renderer consumes only these types; it never inspects raw Claude Code
records. Keeping the model importer-agnostic is what allows other assistants to
be added later without touching the renderer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def parse_ts(value: str | None) -> datetime | None:
    """Parse a Claude Code ISO-8601 timestamp (``...Z``) to an aware datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class ToolEvent:
    name: str
    input_summary: str | None = None
    result_summary: str | None = None
    timestamp: datetime | None = None


@dataclass
class Turn:
    index: int
    prompt: str
    response: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    tool_events: list[ToolEvent] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "complete" if (self.response and self.response.strip()) else "incomplete"


@dataclass
class Conversation:
    id: str
    source: str
    title: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    turns: list[Turn] = field(default_factory=list)

    @property
    def status(self) -> str:
        if not self.turns:
            return "empty"
        return "complete" if all(t.status == "complete" for t in self.turns) else "incomplete"
