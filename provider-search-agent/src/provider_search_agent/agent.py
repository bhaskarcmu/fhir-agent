#!/usr/bin/env python3
"""
Provider Search / Referral Agent — a real MCP client/host (design.md §3.1, §8.2).

It decomposes a natural-language clinical request into MCP tool calls against
provider-mcp-server, and explains the results. It connects over the actual MCP
protocol — `initialize`, real `tools/list` discovery, real `tools/call` invocation —
never by importing provider-mcp-server's or provider-registry-service's code directly.
That discovered-vs-hardcoded distinction is the protocol boundary this phase exists
to prove out: this agent does not hardcode tool schemas the way `mcp-agent/src/agent/
tools.py` does today; it asks the server what tools exist, at connect time.

Unlike claims-agent and provider-curation-agent, this agent has **no deterministic
--no-llm fallback**. Those agents' facts are already fully computed by a deterministic
service before the LLM narrates them — a template renderer is a straightforward
substitute. This agent's entire job is natural-language decomposition (turning "find
an endocrinologist near 27514" into a taxonomy code + coordinate + radius) — there is
no meaningful deterministic substitute for that step, so an Anthropic API key is
required, not optional (decisions.md).

Usage:
  python3 -m provider_search_agent --query "find an endocrinologist near 27514"

Environment:
  ANTHROPIC_API_KEY / CLAUDE_API_KEY   Anthropic key (required)
  PROVIDER_REGISTRY_URL                Passed through to the spawned MCP server
                                        (default http://localhost:8002) — MCP's stdio
                                        transport only inherits a safe-listed subset of
                                        env vars (HOME/LOGNAME/PATH/SHELL/TERM/USER,
                                        verified against the `mcp` SDK, not assumed),
                                        so this must be passed explicitly.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

import anthropic
import mcp.types as types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .format import DIVIDER, error_block, header

MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 1536

SYSTEM_PROMPT = """You help clinicians and care coordinators find real, qualified \
healthcare providers near a patient.

You have three tools, discovered live from the provider-search MCP server — use them, \
never answer from your own knowledge:
- resolve_specialty: turn a free-text clinical need into ranked NUCC taxonomy codes
- search_providers_near: find the nearest providers matching taxonomy codes and filters
- get_provider: fetch a single provider's full record by NPI

Typical flow: call resolve_specialty first to get taxonomy codes, then \
search_providers_near with those codes and the patient's location.

Hard rules, not suggestions:
- NEVER state a provider fact (name, address, phone, NPI, distance, accepting-new- \
patients status) that isn't literally present in a tool result. You select, rank, and \
explain results you're given — you never author facts.
- Every provider you mention must carry its lineage (NPI, source, ingestion run) — \
state it, or make clear it's available on request. Never drop it silently.
- If resolve_specialty returns status "ambiguous" or "no_match", or search_providers_near \
returns zero results, say so plainly and ask a clarifying question. Never substitute a \
different specialty or silently widen the radius without saying that's what you did.
- You make no clinical judgment beyond specialty matching — you never assess whether a \
referral is medically appropriate."""


def mcp_tools_to_anthropic_tools(tools: list[types.Tool]) -> list[dict]:
    """Translate MCP's discovered Tool objects into Anthropic's tool-use schema.
    Field name only (inputSchema -> input_schema) — the schema content is untouched,
    so whatever provider-mcp-server actually advertises is what Claude actually sees."""
    return [
        {"name": t.name, "description": t.description or "", "input_schema": t.inputSchema}
        for t in tools
    ]


async def run_query(user_input: str, session: ClientSession, client: anthropic.Anthropic,
                     tools: list[dict], verbose: bool = True) -> str:
    """Run the tool-use loop. Every tool call goes through session.call_tool() —
    the real MCP tools/call — never an in-process function."""
    messages = [{"role": "user", "content": user_input}]

    while True:
        response = client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT, tools=tools, messages=messages,
        )
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type == "tool_use":
                    if verbose:
                        print(f"  → {block.name}({block.input})")
                    call_result = await session.call_tool(block.name, block.input)
                    text = call_result.content[0].text if call_result.content else "{}"
                    results.append({
                        "type": "tool_result", "tool_use_id": block.id,
                        "content": text, "is_error": bool(call_result.isError),
                    })
            messages.append({"role": "user", "content": results})
            continue

        return "".join(b.text for b in response.content if hasattr(b, "text"))


def _anthropic_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("CLAUDE_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY or CLAUDE_API_KEY is required. This agent's job is "
            "natural-language decomposition, which has no deterministic fallback "
            "(unlike claims-agent/provider-curation-agent's optional LLM narration)."
        )
    return anthropic.Anthropic(api_key=api_key)


def _mcp_server_params() -> StdioServerParameters:
    registry_url = os.environ.get("PROVIDER_REGISTRY_URL", "http://localhost:8002")
    return StdioServerParameters(
        command=sys.executable, args=["-m", "provider_mcp"],
        env={"PROVIDER_REGISTRY_URL": registry_url},
    )


async def search(query: str, verbose: bool = True) -> str:
    client = _anthropic_client()  # fail fast before spawning a subprocess for nothing

    async with stdio_client(_mcp_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            discovered = await session.list_tools()
            tools = mcp_tools_to_anthropic_tools(discovered.tools)
            return await run_query(query, session, client, tools, verbose=verbose)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Find real, traceable providers for a clinical need.")
    parser.add_argument("--query", required=True, help="Natural-language clinical request.")
    parser.add_argument("--quiet", action="store_true", help="Suppress tool-call trace lines.")
    args = parser.parse_args(argv)

    try:
        result = asyncio.run(search(args.query, verbose=not args.quiet))
    except RuntimeError as e:
        print(error_block(str(e)))
        return 2

    print(header(args.query) + "\n" + DIVIDER)
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
