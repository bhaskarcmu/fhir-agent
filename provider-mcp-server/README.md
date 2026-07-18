# provider-mcp-server — the real, hand-built MCP server (Phase 3, M5)

The protocol boundary this whole phase exists to build: a genuine [Model Context
Protocol](https://modelcontextprotocol.io) server — real `initialize`/`tools/list`/`tools/call`
lifecycle via the official Python `mcp` SDK, stdio transport — not a simulation of one. Prior
"agent tools" in this repo (`mcp-agent/src/agent/tools.py`) are in-process Python function
dispatch; this is the first real protocol boundary.

It holds **no clinical or business logic**. Every tool call is a thin translation to an HTTP
call against `provider-registry-service` (`registry_client.py`) — the same "call the
deterministic service, don't import it" pattern `mcp-agent` already uses for `triage-service`.

## Tools exposed

| Tool | Input | What it does |
|---|---|---|
| `resolve_specialty` | `{query}` | Free-text clinical need → ranked NUCC taxonomy codes |
| `search_providers_near` | `{location, taxonomy_codes, radius_miles?, limit?, accepting_new_patients?, entity_type?}` | Nearest-N real providers, with lineage |
| `get_provider` | `{npi}` | Full registry record by NPI, with lineage |

Concrete JSON Schemas (not placeholders) live in `schemas.py` — the exact shapes documented in
design.md §8.3. **`location` is a flat object** (`{zip}` or `{lat, lon}`), not a `oneOf` union:
found real in M6 that live Claude reliably serializes a `oneOf`-typed tool parameter as a JSON
string instead of a native object (reproduced 12/12 times) — the cross-field "exactly one of
zip, or (lat and lon)" rule is enforced downstream by `provider-registry-service`'s own
Pydantic validator instead. See [[llm-tool-schema-oneof-unreliable]] / design.md §14 if you're
tempted to add a `oneOf` to any tool schema here.

Error taxonomy (design.md §8.4): `validation_error`/`not_found`/`upstream_unavailable` set
`isError: true` on the `CallToolResult`; a zero-result search or an ambiguous location does
**not** — those are normal content the caller must not treat as a failure to paper over.

## Running locally

```bash
pip install -e "provider-mcp-server[dev]"
export PROVIDER_REGISTRY_URL=http://localhost:8002   # provider-registry-service must be running
python -m provider_mcp
```

It speaks MCP over stdin/stdout — there's nothing to curl. Point any MCP-compliant client at
it (Claude Desktop, an IDE, or this repo's own `provider-search-agent`) via:

```python
from mcp import StdioServerParameters
StdioServerParameters(command="python", args=["-m", "provider_mcp"],
                      env={"PROVIDER_REGISTRY_URL": "http://localhost:8002"})
```

`env` matters: the `mcp` SDK's `stdio_client` only inherits a safe-listed subset of the
environment (`HOME`, `LOGNAME`, `PATH`, `SHELL`, `TERM`, `USER`) when spawning the child
process — verified against the SDK source, not assumed — so `PROVIDER_REGISTRY_URL` has to be
passed explicitly or the spawned server can't reach the registry at all.

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `PROVIDER_REGISTRY_URL` | No | Base URL of `provider-registry-service` (default `http://localhost:8002`) |

## Test

```bash
pip install -e "provider-mcp-server[dev]"
pytest provider-mcp-server/tests
```

`test_registry_client.py` mocks HTTP (no network). `test_handshake.py` is a real integration
test — it spawns this server as a genuine subprocess over stdio *and*
`provider-registry-service` as a genuine subprocess over HTTP, then drives a real `mcp` SDK
`ClientSession` through the actual handshake. Self-skips (not errors) when Postgres is
unreachable at `TEST_DATABASE_URL`.

## Cloud (design/stub — Phase 3b)

`infra/main.tf` provisions **only an Artifact Registry repository** — deliberately not a
`google_cloud_run_v2_service` resource. An stdio-only process has no `$PORT` listener or HTTP
health check; Cloud Run would kill it as unhealthy. Writing a Cloud Run Service resource here
would `terraform validate` cleanly while being actively undeployable — the exact "stub exists
≠ stub is deploy-ready" gap this project already caught once (decisions.md P8, P16).

Phase 3b has a real decision to make before this can run as a network service: switch
transports. Verified live, not assumed — the installed `mcp` SDK already ships
`mcp.server.sse`, `mcp.server.streamable_http`, and `mcp.server.websocket` alongside
`mcp.server.stdio`, so this is application-code work, not a missing-SDK-feature blocker. See
design.md §13.1.
