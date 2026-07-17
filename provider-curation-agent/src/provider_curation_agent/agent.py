#!/usr/bin/env python3
"""
Provider Curation Agent — orchestrates the deterministic ingestion pipeline and narrates
the result. NOT an MCP client (design.md §3.2 — ingestion is a batch/offline concern, out of
the MCP boundary that provider-search-agent uses for queries).

It is **non-authoritative**: it calls the deterministic ingestion pipeline to obtain the
AUTHORITATIVE run summary and only narrates it — it never writes to the registry, computes
record counts, or resolves anomalies itself. All ETL logic lives in
data/scripts/provider_ingest/ (design.md §6).

Usage:
  python3 -m provider_curation_agent --states NC,CA,MT
  python3 -m provider_curation_agent --states NC --no-llm   # deterministic, no API key needed

Environment:
  ANTHROPIC_API_KEY / CLAUDE_API_KEY   Anthropic key (optional; falls back to deterministic)
  DATABASE_URL                         Postgres connection string (required) — see tools.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .format import DIVIDER, error_block, header
from .summarize import render_summary
from .tools import TOOL_DEFINITIONS, IngestionClient, IngestionError, execute_tool

MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 1024

SYSTEM_PROMPT = """You summarize provider-registry ingestion runs for a data engineer.

Call run_provider_ingestion exactly once with the requested states to obtain the \
AUTHORITATIVE run result. Then summarize it:
- State how many records were added, updated, and flagged.
- Break down anomalies by type (missing_taxonomy, missing_coordinate, etc.) with counts.
- If any states were freshly fetched from NPPES this run, say so.
- Mention a couple of concrete example flags if any exist, for context.

You must NEVER invent record counts or anomaly flags not present in the tool result, and \
NEVER claim an anomaly was resolved or fixed — you only describe what was flagged. This is \
a read-only narrative layer; you do not write to the registry."""


def run_query(client, user_input: str, ingestion_client: IngestionClient, verbose: bool = True):
    """Run the tool-use loop. Returns (final_text, run_dict_or_None)."""
    import anthropic  # local import so --no-llm path needs no key/SDK at import time  # noqa: F401

    messages = [{"role": "user", "content": user_input}]
    run: dict | None = None

    while True:
        response = client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT, tools=TOOL_DEFINITIONS, messages=messages,
        )
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type == "tool_use":
                    if verbose:
                        print(f"  → {block.name}(…)")
                    result_str = execute_tool(block.name, block.input, ingestion_client)
                    if block.name == "run_provider_ingestion":
                        try:
                            run = json.loads(result_str)
                        except json.JSONDecodeError:
                            run = None
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": result_str})
            messages.append({"role": "user", "content": results})
            continue

        final_text = "".join(b.text for b in response.content if hasattr(b, "text"))
        return final_text, run


def summarize_ingestion(states: list[str], use_llm: bool, ingestion_client: IngestionClient) -> str:
    """Run ingestion then summarize. LLM narrative when available, deterministic otherwise."""
    anthropic_client = _anthropic_client() if use_llm else None

    if anthropic_client is None:
        # Deterministic path: get the authoritative run result, render it (no LLM required).
        run = ingestion_client.run(states)
        return header(states, run["run_id"]) + "\n" + DIVIDER + "\n" + render_summary(run)

    prompt = f"Run provider ingestion for these states and summarize the result: {states}"
    final_text, run = run_query(anthropic_client, prompt, ingestion_client)
    head = header(states, run["run_id"]) if run else "Run result unavailable"
    return head + "\n" + DIVIDER + "\n" + (final_text or render_summary(run or {}))


def _anthropic_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("CLAUDE_API_KEY", "")
    if not api_key:
        return None
    import anthropic
    return anthropic.Anthropic(api_key=api_key)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run and summarize a provider ingestion.")
    parser.add_argument("--states", required=True, help="Comma-separated state codes, e.g. NC,CA,MT")
    parser.add_argument("--no-llm", action="store_true",
                        help="Deterministic summary only (no Anthropic call).")
    args = parser.parse_args(argv)
    states = [s.strip().upper() for s in args.states.split(",") if s.strip()]

    try:
        ingestion_client = IngestionClient()
    except IngestionError as e:
        print(error_block(str(e)))
        return 2

    use_llm = not args.no_llm
    if use_llm and _anthropic_client() is None:
        print("(no Anthropic key found — using deterministic summary)\n")
        use_llm = False

    try:
        print(summarize_ingestion(states, use_llm, ingestion_client))
    except IngestionError as e:
        print(error_block(f"Ingestion failed: {e}"))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
