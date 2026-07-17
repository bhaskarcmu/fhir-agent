"""
Integration test proving the REAL MCP protocol handshake — initialize, tools/list,
tools/call — against a real provider-registry-service backed by real ingested data
(design.md M5's explicit deliverable: "integration test proving the actual
initialize/tools-list/tools-call handshake").

Spawns provider-mcp-server as a genuine subprocess over stdio (not an in-process
function call) and provider-registry-service as a genuine subprocess over HTTP, then
drives the real `mcp` SDK client against both. Self-skips (not errors) when Postgres
is unreachable, matching the project's established pattern for DB-backed tests.

  TEST_DATABASE_URL   Postgres connection string
                       (default: postgresql://provider_registry:provider_registry@localhost:5432/provider_registry_test)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import psycopg
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://provider_registry:provider_registry@localhost:5432/provider_registry_test",
)
REGISTRY_PORT = 8003
REGISTRY_URL = f"http://127.0.0.1:{REGISTRY_PORT}"

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_SQL_PATH = REPO_ROOT / "provider-registry-service" / "schema.sql"
FIXTURES_SQL_PATH = (
    REPO_ROOT / "provider-registry-service" / "src" / "provider_registry" / "tests" / "fixtures.sql"
)

pytestmark = pytest.mark.asyncio


def _db_available() -> bool:
    try:
        with psycopg.connect(TEST_DATABASE_URL, connect_timeout=2):
            return True
    except psycopg.OperationalError:
        return False


def _seed_fixture_data() -> None:
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        conn.execute(SCHEMA_SQL_PATH.read_text())
        conn.execute(
            "TRUNCATE anomaly_flags, provider_taxonomies, provider_addresses, "
            "providers, ingestion_runs, taxonomy_reference, zip_centroids CASCADE"
        )
        conn.execute(FIXTURES_SQL_PATH.read_text())
        conn.commit()


def _wait_for_health(url: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=2) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError):
            pass
        time.sleep(0.3)
    raise RuntimeError(f"provider-registry-service did not become healthy at {url}")


@pytest.fixture(scope="module")
def registry_service():
    if not _db_available():
        pytest.skip(f"Postgres not reachable at {TEST_DATABASE_URL} — skipping MCP handshake test")

    _seed_fixture_data()

    env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "provider_registry.main:app",
         "--host", "127.0.0.1", "--port", str(REGISTRY_PORT)],
        cwd=REPO_ROOT / "provider-registry-service",
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        _wait_for_health(REGISTRY_URL)
        yield REGISTRY_URL
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture
def mcp_server_params(registry_service) -> StdioServerParameters:
    env = {**os.environ, "PROVIDER_REGISTRY_URL": registry_service}
    return StdioServerParameters(command=sys.executable, args=["-m", "provider_mcp"], env=env)


async def test_initialize_handshake_succeeds(mcp_server_params):
    async with stdio_client(mcp_server_params) as (read, write):
        async with ClientSession(read, write) as session:
            result = await session.initialize()
    assert result.serverInfo.name == "provider-search"


async def test_tools_list_discovers_all_three_real_tools(mcp_server_params):
    async with stdio_client(mcp_server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()

    names = {t.name for t in tools.tools}
    assert names == {"resolve_specialty", "search_providers_near", "get_provider"}
    # Real JSON Schemas, not placeholders (design.md §8.3) -- prove they came through.
    search_tool = next(t for t in tools.tools if t.name == "search_providers_near")
    assert search_tool.inputSchema["required"] == ["location", "taxonomy_codes"]


async def test_tools_call_resolve_specialty_against_real_data(mcp_server_params):
    async with stdio_client(mcp_server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("resolve_specialty", {"query": "endocrinologist"})

    assert result.isError is not True
    body = json.loads(result.content[0].text)
    assert body["status"] == "ok"
    assert body["matches"][0]["code"] == "207RE0101X"


async def test_tools_call_search_providers_near_returns_real_grounded_result(mcp_server_params):
    async with stdio_client(mcp_server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("search_providers_near", {
                "location": {"zip": "27514"},
                "taxonomy_codes": ["207RE0101X"],
                "radius_miles": 25,
            })

    assert result.isError is not True
    body = json.loads(result.content[0].text)
    assert body["status"] == "ok"
    assert body["results"][0]["npi"] == "1111111111"  # Jane Doe, fixtures.sql
    assert body["results"][0]["lineage"]["source"] == "NPPES"  # every result carries lineage


async def test_tools_call_get_provider_by_npi(mcp_server_params):
    async with stdio_client(mcp_server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("get_provider", {"npi": "1111111111"})

    body = json.loads(result.content[0].text)
    assert body["name"] == "Jane Doe"


async def test_tools_call_not_found_sets_mcp_level_error(mcp_server_params):
    async with stdio_client(mcp_server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("get_provider", {"npi": "9999999999"})

    assert result.isError is True
    body = json.loads(result.content[0].text)
    assert body["error_type"] == "not_found"


async def test_malformed_input_is_rejected_by_schema_validation_before_our_handler_runs(mcp_server_params):
    # The mcp SDK validates arguments against inputSchema automatically -- this proves
    # that's actually wired up, not just documented in schemas.py.
    async with stdio_client(mcp_server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("get_provider", {"npi": "not-a-valid-npi"})

    assert result.isError is True
