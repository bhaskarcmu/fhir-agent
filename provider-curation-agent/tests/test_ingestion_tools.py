import json
import os
import uuid
from pathlib import Path
from unittest.mock import patch

import psycopg
import pytest

from provider_curation_agent.tools import IngestionClient, IngestionError, execute_tool

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://provider_registry:provider_registry@localhost:5432/provider_registry_test",
)

SCHEMA_SQL_PATH = (
    Path(__file__).resolve().parents[2] / "provider-registry-service" / "schema.sql"
)


def _db_available() -> bool:
    try:
        with psycopg.connect(TEST_DATABASE_URL, connect_timeout=2):
            return True
    except psycopg.OperationalError:
        return False


def test_missing_database_url_raises_ingestion_error(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(IngestionError):
        IngestionClient(database_url="")


def test_fetch_missing_states_skips_existing_files(tmp_path):
    (tmp_path / "nppes_nc.json").write_text("[]")  # NC already fetched
    client = IngestionClient(database_url="postgresql://x/y", ref_dir=tmp_path)

    with patch.object(client, "_run_subprocess") as mock_run:
        fetched = client._fetch_missing_states(["NC", "CA"])

    assert fetched == ["CA"]
    mock_run.assert_called_once_with("fetch_nppes.py", "--state", "CA")


def test_fetch_missing_states_skips_all_when_all_present(tmp_path):
    (tmp_path / "nppes_nc.json").write_text("[]")
    client = IngestionClient(database_url="postgresql://x/y", ref_dir=tmp_path)

    with patch.object(client, "_run_subprocess") as mock_run:
        fetched = client._fetch_missing_states(["NC"])

    assert fetched == []
    mock_run.assert_not_called()


def test_execute_tool_unknown_tool_is_error():
    client = IngestionClient(database_url="postgresql://x/y")
    result = json.loads(execute_tool("nope", {}, client))
    assert "error" in result


def test_execute_tool_handles_ingestion_failure_gracefully():
    client = IngestionClient(database_url="postgresql://x/y")
    with patch.object(client, "run", side_effect=IngestionError("boom")):
        result = json.loads(execute_tool("run_provider_ingestion", {"states": ["NC"]}, client))
    assert result == {"error": "boom"}


@pytest.mark.skipif(not _db_available(), reason=f"Postgres not reachable at {TEST_DATABASE_URL}")
class TestLatestRunReadback:
    def setup_method(self):
        self.conn = psycopg.connect(TEST_DATABASE_URL)
        self.conn.execute(SCHEMA_SQL_PATH.read_text())
        with self.conn.cursor() as cur:
            cur.execute("TRUNCATE anomaly_flags, ingestion_runs CASCADE")
        self.conn.commit()

    def teardown_method(self):
        self.conn.close()

    def _seed_run(self) -> str:
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ingestion_runs (states_pulled, records_added, records_updated, records_flagged, completed_at) "
                "VALUES (%s, %s, %s, %s, now()) RETURNING id",
                (["NC"], 5, 0, 2),
            )
            run_id = cur.fetchone()[0]
            # anomaly_flags.npi has a FK to providers -- insert a minimal provider row first.
            cur.execute(
                "INSERT INTO providers (npi, entity_type, source, source_pulled_at, ingestion_run_id) "
                "VALUES ('1111111111', 1, 'NPPES', now(), %s)",
                (run_id,),
            )
            cur.execute(
                "INSERT INTO anomaly_flags (npi, run_id, flag_type, detail) VALUES "
                "('1111111111', %s, 'missing_coordinate', 'zip5 not found'), "
                "('1111111111', %s, 'missing_coordinate', 'zip5 not found again')",
                (run_id, run_id),
            )
        self.conn.commit()
        return str(run_id)

    def test_latest_run_reads_authoritative_counts_and_anomaly_breakdown(self):
        run_id = self._seed_run()
        client = IngestionClient(database_url=TEST_DATABASE_URL)

        run = client._latest_run(self.conn)

        assert str(run["id"]) == run_id
        assert run["records_added"] == 5
        assert run["records_flagged"] == 2
        assert run["anomaly_breakdown"] == {"missing_coordinate": 2}
        assert len(run["sample_anomalies"]) == 2

    def test_run_never_invents_states_not_in_the_pulled_result(self, tmp_path):
        (tmp_path / "nppes_nc.json").write_text("[]")
        self._seed_run()
        client = IngestionClient(database_url=TEST_DATABASE_URL, ref_dir=tmp_path)

        with patch.object(client, "_run_subprocess"):
            result = client.run(["NC"])

        # The states in the result come from the DB row (the authoritative record of what
        # was actually pulled), not echoed back from the caller's input unchecked.
        assert result["states_pulled"] == ["NC"]
        assert result["states_freshly_fetched"] == []
