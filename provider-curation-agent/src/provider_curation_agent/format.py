"""Terminal formatting for the provider curation agent."""

from __future__ import annotations

DIVIDER = "─" * 68


def header(states: list[str], run_id: str) -> str:
    return f"📋 Ingestion run: {', '.join(states)}\n   Run id: {run_id}"


def error_block(message: str) -> str:
    return f"⚠️  {message}"
