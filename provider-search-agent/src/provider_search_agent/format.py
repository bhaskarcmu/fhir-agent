"""Terminal formatting for the provider search agent."""

from __future__ import annotations

DIVIDER = "─" * 68


def header(query: str) -> str:
    return f"🔎 {query}"


def error_block(message: str) -> str:
    return f"⚠️  {message}"
