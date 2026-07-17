#!/usr/bin/env python3
"""
Provider MCP Server — the actual protocol boundary this phase exists to build
(design.md §8). Real MCP handshake (initialize / tools/list / tools/call) via the
official Python `mcp` SDK, stdio transport. Thin adapter over
provider-registry-service's HTTP API (registry_client.py) — this server holds no
clinical/business logic itself; `provider-registry-service` is the deterministic core.

Tools exposed: resolve_specialty, search_providers_near, get_provider (design.md §8.3).
Internal-only — never on the Kong edge (design.md §9).

Usage:
  python3 -m provider_mcp

Environment:
  PROVIDER_REGISTRY_URL   Base URL of provider-registry-service (default http://localhost:8002)
"""

from __future__ import annotations

import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from . import registry_client
from .schemas import GET_PROVIDER_SCHEMA, RESOLVE_SPECIALTY_SCHEMA, SEARCH_PROVIDERS_NEAR_SCHEMA

server = Server("provider-search")

TOOLS = [
    types.Tool(
        name="resolve_specialty",
        description=(
            "Resolve a free-text clinical need to ranked NUCC taxonomy codes. "
            "Deterministic fuzzy match — no LLM call, fully traceable."
        ),
        inputSchema=RESOLVE_SPECIALTY_SCHEMA,
    ),
    types.Tool(
        name="search_providers_near",
        description=(
            "Search the provider registry for the nearest providers matching taxonomy "
            "codes and filters. Returns real, traceable records with lineage — every "
            "result carries the ingestion run and source it came from."
        ),
        inputSchema=SEARCH_PROVIDERS_NEAR_SCHEMA,
    ),
    types.Tool(
        name="get_provider",
        description="Fetch a single provider's full registry record by NPI, with lineage.",
        inputSchema=GET_PROVIDER_SCHEMA,
    ),
]

_DISPATCH = {
    "resolve_specialty": lambda args: registry_client.resolve_specialty(args["query"]),
    "search_providers_near": lambda args: registry_client.search_providers_near(args),
    "get_provider": lambda args: registry_client.get_provider(args["npi"]),
}


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> types.CallToolResult:
    handler = _DISPATCH.get(name)
    if handler is None:
        result = {"error_type": "validation_error", "message": f"unknown tool: {name}"}
    else:
        result = handler(arguments)

    # design.md §8.4: validation_error/not_found/upstream_unavailable are real MCP-level
    # errors (isError=True); success-with-results, success-no-results, and ambiguous are
    # NOT errors — they're normal content the agent must not treat as a failure to
    # paper over.
    is_error = "error_type" in result
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(result))],
        isError=is_error,
    )


async def run() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
