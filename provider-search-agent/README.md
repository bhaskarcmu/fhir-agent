# provider-search-agent — the real MCP client/host (Phase 3, M6)

The agent that turns a natural-language clinical request into ranked, explained, traceable
providers by orchestrating `provider-mcp-server` over the actual MCP protocol. It discovers
the server's tools live via a real `tools/list` call — it does **not** hardcode tool
definitions the way `mcp-agent/src/agent/tools.py` does today. That discovered-vs-hardcoded
distinction is the point of this whole phase: this is the client side of the same protocol
boundary `provider-mcp-server` (M5) built the server side of.

**No `--no-llm` fallback**, unlike `claims-agent`/`provider-curation-agent` (decisions.md
P18). Those agents narrate an already-fully-computed deterministic fact; this agent's entire
job is natural-language decomposition (free text → taxonomy code + coordinate + radius) — there
is no meaningful deterministic substitute for that step, so an Anthropic key is required.

## How it works

1. Spawn `provider-mcp-server` as a local child process over stdio
   (`StdioServerParameters(command=sys.executable, args=["-m", "provider_mcp"], env=...)`).
2. Real MCP handshake: `initialize`, then `tools/list` to discover the three tools live.
3. Translate the discovered tools into Anthropic's tool-use schema
   (`inputSchema` → `input_schema` — field name only, the schema content is untouched) and run
   the tool-use loop. Every tool call goes through `session.call_tool()` — the real MCP
   `tools/call` — never an in-process function.
4. Guardrails (system prompt, `agent.py`): never state a provider fact not literally present in
   a tool result; every provider mentioned carries its lineage; a zero-result or ambiguous
   response gets a plain "here's what I found" and a clarifying question, never a substituted
   specialty or a silently widened radius.

## Usage

```bash
python3 -m provider_search_agent --query "find an endocrinologist near 27514 who's accepting new patients"
```

## Environment

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` / `CLAUDE_API_KEY` | Yes | No deterministic fallback — see above |
| `PROVIDER_REGISTRY_URL` | No | Passed through to the spawned `provider-mcp-server` (default `http://localhost:8002`) |

## Test

```bash
pip install -e "provider-search-agent[dev]"
pytest provider-search-agent/tests
```

`test_agent.py` mocks the Anthropic client and the MCP session (no network, no cost).
`test_groundedness_eval.py` is the real thing — design.md §3.1's explicit deliverable ("100%
of NPIs in an agent transcript resolve via `get_provider`"): scripted NL queries run through
the full real stack (real Claude, real tool-use loop, real `provider-mcp-server` subprocess,
real `provider-registry-service` subprocess, real Postgres), then every NPI the agent's final
answer mentions is independently re-fetched and asserted real — including a query with zero
real matches, asserted to produce zero fabricated NPIs. Self-skips (not errors) when either
Postgres or an Anthropic key is unavailable — it makes real, billed API calls, so it isn't run
unconditionally.

## Real bugs this surfaced (not just written up in a doc)

Two, both found by running live queries against the full stack, not from the scripted eval set
alone — full detail in design.md §14 and decisions.md P17/P19:

1. Live Claude reliably serialized `provider-mcp-server`'s `oneOf`-typed `location` parameter
   as a JSON string instead of a native object (12/12 consecutive attempts). Fixed in
   `provider-mcp-server/src/provider_mcp/schemas.py` by flattening the schema — see that
   package's README before adding a `oneOf` anywhere in this repo's tool schemas.
2. Live Claude once transcribed a taxonomy code with a dropped character between tool calls,
   which silently produced a misleading zero-result answer instead of an error. Fixed with a
   format pattern on `taxonomy_codes`, verified against all 883 real NUCC codes.
