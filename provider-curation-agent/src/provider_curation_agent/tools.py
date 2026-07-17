"""
Tool layer for the provider curation agent.

The single tool runs the deterministic ingestion pipeline (data/scripts/provider_ingest/)
for the given states and returns the AUTHORITATIVE run summary — record counts and anomaly
flags, read back from provider-registry-service's own database tables (ingestion_runs,
anomaly_flags), not from subprocess output text. The agent narrates that summary; it never
computes counts, resolves anomalies, or alters the registry itself (design.md §3.2 — this
agent is a read-only narrative layer over deterministic ETL).

Environment:
  DATABASE_URL   Postgres connection string (required) — see provider-registry-service/schema.sql
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import psycopg

REPO_ROOT = Path(__file__).resolve().parents[3]
PROVIDER_INGEST_DIR = REPO_ROOT / "data" / "scripts" / "provider_ingest"
REF_DIR = REPO_ROOT / "data" / "reference" / "providers"

TOOL_DEFINITIONS = [
    {
        "name": "run_provider_ingestion",
        "description": (
            "Run the deterministic NPPES/NUCC/ZCTA ingestion pipeline for the given states "
            "and return the AUTHORITATIVE run summary (record counts and anomaly-flag "
            "breakdown), read from the registry database. This is the source of truth — "
            "summarize it; never invent counts or flags not present in the result, and "
            "never claim an anomaly was resolved — only describe what was flagged."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "states": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "2-letter state codes to ingest, e.g. [\"NC\", \"CA\", \"MT\"]",
                }
            },
            "required": ["states"],
        },
    }
]


class IngestionError(Exception):
    pass


class IngestionClient:
    """Orchestrates the deterministic fetch/ingest scripts as subprocesses, then reads the
    authoritative result back from Postgres. Never writes to the registry itself — the
    deterministic scripts do that; this class only invokes them and reads their output."""

    def __init__(self, database_url: str | None = None, ref_dir: Path | None = None,
                 provider_ingest_dir: Path | None = None, python: str | None = None):
        self.database_url = database_url or os.environ.get("DATABASE_URL", "")
        if not self.database_url:
            raise IngestionError(
                "DATABASE_URL is not set. "
                "Set it to a Postgres connection string, "
                "e.g. postgresql://provider_registry:provider_registry@localhost:5432/provider_registry"
            )
        self.ref_dir = ref_dir or REF_DIR
        self.provider_ingest_dir = provider_ingest_dir or PROVIDER_INGEST_DIR
        self.python = python or sys.executable

    def _run_subprocess(self, script: str, *args: str) -> str:
        env = {**os.environ, "DATABASE_URL": self.database_url}
        result = subprocess.run(
            [self.python, str(self.provider_ingest_dir / script), *args],
            capture_output=True, text=True, env=env, timeout=600,
        )
        if result.returncode != 0:
            raise IngestionError(f"{script} failed (exit {result.returncode}): {result.stderr.strip()}")
        return result.stdout

    def _fetch_missing_states(self, states: list[str]) -> list[str]:
        fetched = []
        for state in states:
            curated_file = self.ref_dir / f"nppes_{state.lower()}.json"
            if curated_file.exists():
                continue
            self._run_subprocess("fetch_nppes.py", "--state", state)
            fetched.append(state)
        return fetched

    def _latest_run(self, conn: psycopg.Connection) -> dict:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, started_at, completed_at, states_pulled, "
                "records_added, records_updated, records_flagged "
                "FROM ingestion_runs ORDER BY started_at DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row is None:
                raise IngestionError("no ingestion_runs row found after running the pipeline")
            columns = [d.name for d in cur.description]
            run = dict(zip(columns, row))

            cur.execute(
                "SELECT flag_type, count(*) FROM anomaly_flags WHERE run_id = %s GROUP BY flag_type",
                (run["id"],),
            )
            run["anomaly_breakdown"] = dict(cur.fetchall())

            cur.execute(
                "SELECT npi, flag_type, detail FROM anomaly_flags WHERE run_id = %s LIMIT 5",
                (run["id"],),
            )
            sample_columns = [d.name for d in cur.description]
            run["sample_anomalies"] = [dict(zip(sample_columns, r)) for r in cur.fetchall()]
        return run

    def run(self, states: list[str]) -> dict:
        fetched = self._fetch_missing_states(states)
        self._run_subprocess("run_ingestion.py", "--states", ",".join(states))

        with psycopg.connect(self.database_url) as conn:
            run = self._latest_run(conn)

        return {
            "run_id": str(run["id"]),
            "started_at": run["started_at"].isoformat(),
            "completed_at": run["completed_at"].isoformat() if run["completed_at"] else None,
            "states_pulled": run["states_pulled"],
            "states_freshly_fetched": fetched,
            "records_added": run["records_added"],
            "records_updated": run["records_updated"],
            "records_flagged": run["records_flagged"],
            "anomaly_breakdown": run["anomaly_breakdown"],
            "sample_anomalies": run["sample_anomalies"],
        }


def execute_tool(name: str, tool_input: dict, client: IngestionClient) -> str:
    """Dispatch an Anthropic tool call. Returns a JSON string (never raises into the loop)."""
    if name != "run_provider_ingestion":
        return json.dumps({"error": f"unknown tool: {name}"})
    try:
        result = client.run(tool_input["states"])
        return json.dumps(result, default=str)
    except IngestionError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:  # noqa: BLE001 - tools must not raise into the agent loop
        return json.dumps({"error": str(e)})
