"""
DB-backed tests for run_ingestion.py — self-skips when Postgres is unreachable,
same pattern as provider-registry-service/.../tests/conftest.py and the project's
e2e suite (real DB, not mocked; skip cleanly rather than fake it).

  TEST_DATABASE_URL   Postgres connection string
                       (default: postgresql://provider_registry:provider_registry@localhost:5432/provider_registry_test)

Run:
  python3 -m pytest data/scripts/provider_ingest/test_run_ingestion.py -v
"""

from __future__ import annotations

import importlib.util
import json
import os
import unittest
from pathlib import Path

import psycopg

_MODULE_PATH = Path(__file__).parent / "run_ingestion.py"
_spec = importlib.util.spec_from_file_location("run_ingestion", _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://provider_registry:provider_registry@localhost:5432/provider_registry_test",
)

_TABLES_IN_FK_ORDER = (
    "anomaly_flags", "provider_taxonomies", "provider_addresses",
    "providers", "ingestion_runs", "taxonomy_reference", "zip_centroids",
)

FAKE_TAXONOMY_CSV = "code,grouping,classification,specialization,definition,nucc_version\n" \
    "207RE0101X,Allopathic & Osteopathic Physicians,Internal Medicine,\"Endocrinology, Diabetes & Metabolism\",A specialist,26.0\n"

FAKE_ZIP_CENTROIDS_CSV = "zip5,lat,lon,state\n27514,35.9132,-79.0558,NC\n"

FAKE_NPPES_RECORDS = [
    {
        "npi": "1111111111", "entity_type": 1, "name": "Jane Doe", "npi_status": "active",
        "addresses": [{"address_1": "1 Main St", "address_2": None, "city": "Chapel Hill",
                        "state": "NC", "zip5": "27514"}],
        "taxonomies": [{"code": "207RE0101X", "is_primary": True}],
    },
    {
        # Intentionally references a ZIP with no centroid -- exercises the
        # missing_coordinate anomaly-flagging path.
        "npi": "2222222222", "entity_type": 1, "name": "No Centroid Doe", "npi_status": "active",
        "addresses": [{"address_1": "2 Main St", "address_2": None, "city": "Nowhere",
                        "state": "NC", "zip5": "00000"}],
        "taxonomies": [{"code": "207RE0101X", "is_primary": True}],
    },
]


def _db_available() -> bool:
    try:
        with psycopg.connect(TEST_DATABASE_URL, connect_timeout=2):
            return True
    except psycopg.OperationalError:
        return False


@unittest.skipUnless(_db_available(), f"Postgres not reachable at {TEST_DATABASE_URL} — skipping DB-backed tests")
class TestRunIngestion(unittest.TestCase):
    def setUp(self):
        os.environ["DATABASE_URL"] = TEST_DATABASE_URL
        self.conn = _mod._connect()
        _mod._apply_schema(self.conn)
        with self.conn.cursor() as cur:
            cur.execute(f"TRUNCATE {', '.join(_TABLES_IN_FK_ORDER)} CASCADE")
        self.conn.commit()

        # Point the module's REF_DIR at a temp fixture directory instead of the
        # real curated files, so this test is self-contained and fast.
        self.ref_dir = Path("/tmp/test_provider_ingest_ref")
        self.ref_dir.mkdir(exist_ok=True)
        (self.ref_dir / "taxonomy_reference.csv").write_text(FAKE_TAXONOMY_CSV)
        (self.ref_dir / "zip_centroids.csv").write_text(FAKE_ZIP_CENTROIDS_CSV)
        (self.ref_dir / "nppes_nc.json").write_text(json.dumps(FAKE_NPPES_RECORDS))
        self._orig_ref_dir = _mod.REF_DIR
        _mod.REF_DIR = self.ref_dir

    def tearDown(self):
        _mod.REF_DIR = self._orig_ref_dir
        self.conn.close()

    def test_first_run_inserts_and_flags_missing_coordinate(self):
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO ingestion_runs (states_pulled) VALUES (%s) RETURNING id, started_at", (["NC"],))
            run_id, started_at = cur.fetchone()
        self.conn.commit()

        _mod._load_taxonomy_reference(self.conn)
        _mod._load_zip_centroids(self.conn)
        known_codes = _mod._known_taxonomy_codes(self.conn)
        added, updated, flagged = _mod._ingest_state(
            self.conn, "NC", str(run_id), started_at.isoformat(), known_codes,
        )

        self.assertEqual((added, updated, flagged), (2, 0, 1))  # 1 missing_coordinate flag

        with self.conn.cursor() as cur:
            cur.execute("SELECT npi_status FROM providers WHERE npi = '1111111111'")
            self.assertEqual(cur.fetchone()[0], "active")
            cur.execute("SELECT lat, lon FROM provider_addresses WHERE npi = '1111111111'")
            lat, lon = cur.fetchone()
            self.assertAlmostEqual(lat, 35.9132)
            cur.execute("SELECT lat FROM provider_addresses WHERE npi = '2222222222'")
            self.assertIsNone(cur.fetchone()[0])  # no centroid -- lat stays NULL, not guessed
            cur.execute("SELECT flag_type FROM anomaly_flags WHERE npi = '2222222222'")
            self.assertEqual(cur.fetchone()[0], "missing_coordinate")

    def test_second_run_is_idempotent_updates_not_duplicates(self):
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO ingestion_runs (states_pulled) VALUES (%s) RETURNING id, started_at", (["NC"],))
            run_id_1, started_at_1 = cur.fetchone()
        self.conn.commit()
        _mod._load_taxonomy_reference(self.conn)
        _mod._load_zip_centroids(self.conn)
        known_codes = _mod._known_taxonomy_codes(self.conn)
        _mod._ingest_state(self.conn, "NC", str(run_id_1), started_at_1.isoformat(), known_codes)

        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO ingestion_runs (states_pulled) VALUES (%s) RETURNING id, started_at", (["NC"],))
            run_id_2, started_at_2 = cur.fetchone()
        self.conn.commit()
        added, updated, flagged = _mod._ingest_state(
            self.conn, "NC", str(run_id_2), started_at_2.isoformat(), known_codes,
        )

        self.assertEqual((added, updated), (0, 2))  # re-run updates, doesn't duplicate
        with self.conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM providers")
            self.assertEqual(cur.fetchone()[0], 2)  # still exactly 2 rows, not 4
            cur.execute("SELECT ingestion_run_id FROM providers WHERE npi = '1111111111'")
            self.assertEqual(str(cur.fetchone()[0]), str(run_id_2))  # lineage points at the latest run


if __name__ == "__main__":
    unittest.main()
