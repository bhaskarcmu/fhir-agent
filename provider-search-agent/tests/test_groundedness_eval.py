"""
Groundedness eval harness (design.md §3.1: "An eval harness asserts 100% of NPIs in an
agent transcript resolve via get_provider"). Runs real scripted NL queries through the
FULL real stack — real Claude API, real provider-search-agent tool-use loop, real
provider-mcp-server subprocess, real provider-registry-service subprocess, real
Postgres — then independently re-fetches every NPI the agent's final answer mentions and
asserts it's a real registry record. This is the actual grounding proof, not a unit test
asserting the guardrail prompt exists.

Self-skips (not errors) when either prerequisite is missing:
  - Postgres unreachable at TEST_DATABASE_URL
  - No ANTHROPIC_API_KEY / CLAUDE_API_KEY (this eval makes real, billed API calls —
    kept to a small scripted query set deliberately, not run on every `pytest` invocation
    in CI without a key configured)
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import psycopg
import pytest

from provider_search_agent.agent import search

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://provider_registry:provider_registry@localhost:5432/provider_registry_test",
)
REGISTRY_PORT = 8004
REGISTRY_URL = f"http://127.0.0.1:{REGISTRY_PORT}"

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_SQL_PATH = REPO_ROOT / "provider-registry-service" / "schema.sql"
FIXTURES_SQL_PATH = (
    REPO_ROOT / "provider-registry-service" / "src" / "provider_registry" / "tests" / "fixtures.sql"
)

NPI_PATTERN = re.compile(r"\b\d{10}\b")


def _db_available() -> bool:
    try:
        with psycopg.connect(TEST_DATABASE_URL, connect_timeout=2):
            return True
    except psycopg.OperationalError:
        return False


def _has_llm_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY"))


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


def _get_provider(npi: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"{REGISTRY_URL}/v1/providers/{npi}", timeout=5) as resp:
            import json
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


@pytest.fixture(scope="module")
def registry_service():
    if not _db_available():
        pytest.skip(f"Postgres not reachable at {TEST_DATABASE_URL} — skipping groundedness eval")
    if not _has_llm_key():
        pytest.skip("No ANTHROPIC_API_KEY/CLAUDE_API_KEY set — skipping groundedness eval (real, billed calls)")

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
def registry_url_env(registry_service, monkeypatch):
    monkeypatch.setenv("PROVIDER_REGISTRY_URL", registry_service)


@pytest.mark.asyncio
async def test_matching_query_returns_only_real_grounded_active_npis(registry_url_env):
    answer = await search("Find an endocrinologist near ZIP 27514", verbose=False)

    npis = set(NPI_PATTERN.findall(answer))
    assert npis, f"expected at least one NPI in a matching-query answer, got: {answer!r}"

    for npi in npis:
        record = _get_provider(npi)
        assert record is not None, f"agent stated NPI {npi} but it does not exist in the registry"
        assert record["npi_status"] != "deactivated", (
            f"agent stated NPI {npi}, which is deactivated -- must never surface in a referral"
        )
    # The deactivated fixture record must never appear, even implicitly.
    assert "3333333333" not in npis


@pytest.mark.asyncio
async def test_cross_state_query_returns_real_grounded_npi(registry_url_env):
    answer = await search("Find a cardiologist near Los Angeles, California, ZIP 90001", verbose=False)

    npis = set(NPI_PATTERN.findall(answer))
    for npi in npis:
        assert _get_provider(npi) is not None, f"agent stated NPI {npi} but it does not exist"
    if npis:
        assert "5555555555" in npis  # the only real cardiologist in the fixture


@pytest.mark.asyncio
async def test_no_match_query_never_fabricates_an_npi(registry_url_env):
    # No neurologist exists anywhere in the fixture data -- a grounded agent must say so,
    # not invent a plausible-looking result.
    answer = await search("Find a neurologist near ZIP 27514", verbose=False)

    npis = set(NPI_PATTERN.findall(answer))
    for npi in npis:
        assert _get_provider(npi) is not None, (
            f"agent stated NPI {npi} for a specialty with zero real matches -- fabrication"
        )
