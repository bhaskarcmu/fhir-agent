#!/usr/bin/env python3
"""
run_ingestion.py — deterministic ETL: load the curated NPPES/NUCC/ZCTA files
(data/reference/providers/) into provider-registry-service's Postgres schema.

Writes directly to Postgres via psycopg (design.md §6, decision P10) — no HTTP
layer; provider-registry-service gains no write endpoints from this. Idempotent:
upserts keyed on natural identity (NPI, taxonomy code, zip5). Each run gets its
own ingestion_runs row so lineage always shows which run last touched a record.
Re-running is safe — that's the whole point of "manually re-run, one-time-per-
state seed" (PRD §6 Freshness) rather than a live pipeline.

Environment variables:
  DATABASE_URL   Postgres connection string (required)

Usage:
  python3 data/scripts/provider_ingest/run_ingestion.py --states NC
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

import psycopg

REF_DIR = Path(__file__).resolve().parents[2] / "reference" / "providers"
SCHEMA_SQL_PATH = Path(__file__).resolve().parents[3] / "provider-registry-service" / "schema.sql"


def _connect() -> psycopg.Connection:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. "
            "Set it to a Postgres connection string, "
            "e.g. postgresql://provider_registry:provider_registry@localhost:5432/provider_registry"
        )
    return psycopg.connect(database_url)


def _apply_schema(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA_SQL_PATH.read_text())


def _load_taxonomy_reference(conn: psycopg.Connection) -> int:
    path = REF_DIR / "taxonomy_reference.csv"
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO taxonomy_reference (code, grouping, classification, specialization, definition, nucc_version)
                VALUES (%(code)s, %(grouping)s, %(classification)s, %(specialization)s, %(definition)s, %(nucc_version)s)
                ON CONFLICT (code) DO UPDATE SET
                    grouping = EXCLUDED.grouping, classification = EXCLUDED.classification,
                    specialization = EXCLUDED.specialization, definition = EXCLUDED.definition,
                    nucc_version = EXCLUDED.nucc_version
                """,
                {**row, "specialization": row["specialization"] or None},
            )
    conn.commit()
    return len(rows)


def _load_zip_centroids(conn: psycopg.Connection) -> int:
    path = REF_DIR / "zip_centroids.csv"
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO zip_centroids (zip5, lat, lon, state)
                VALUES (%(zip5)s, %(lat)s, %(lon)s, %(state)s)
                ON CONFLICT (zip5) DO UPDATE SET lat = EXCLUDED.lat, lon = EXCLUDED.lon, state = EXCLUDED.state
                """,
                row,
            )
    conn.commit()
    return len(rows)


def _zip_centroid_exists(conn: psycopg.Connection, zip5: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM zip_centroids WHERE zip5 = %s", (zip5,))
        return cur.fetchone() is not None


def _known_taxonomy_codes(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT code FROM taxonomy_reference")
        return {row[0] for row in cur.fetchall()}


def _ingest_state(conn: psycopg.Connection, state: str, run_id: str, source_pulled_at: str,
                   known_taxonomy_codes: set[str]) -> tuple[int, int, int]:
    path = REF_DIR / f"nppes_{state.lower()}.json"
    if not path.exists():
        print(f"  no curated file for {state} at {path} — skipping (run fetch_nppes.py first)")
        return 0, 0, 0

    records = json.loads(path.read_text())
    added = updated = flagged = 0

    with conn.cursor() as cur:
        for record in records:
            npi = record["npi"]
            primary_addr = record["addresses"][0] if record["addresses"] else None

            cur.execute(
                """
                INSERT INTO providers
                    (npi, entity_type, first_name, last_name, organization_name,
                     npi_status, source, source_pulled_at, ingestion_run_id, updated_at)
                VALUES (%(npi)s, %(entity_type)s, %(first_name)s, %(last_name)s, %(organization_name)s,
                        %(npi_status)s, 'NPPES', %(source_pulled_at)s, %(run_id)s, now())
                ON CONFLICT (npi) DO UPDATE SET
                    entity_type = EXCLUDED.entity_type, first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name, organization_name = EXCLUDED.organization_name,
                    npi_status = EXCLUDED.npi_status, source_pulled_at = EXCLUDED.source_pulled_at,
                    ingestion_run_id = EXCLUDED.ingestion_run_id, updated_at = now()
                RETURNING (xmax = 0) AS inserted
                """,
                {
                    "npi": npi,
                    "entity_type": record["entity_type"],
                    "first_name": None if record["entity_type"] == 2 else record["name"].split(" ", 1)[0],
                    "last_name": None if record["entity_type"] == 2 else
                                 (record["name"].split(" ", 1)[1] if " " in record["name"] else ""),
                    "organization_name": record["name"] if record["entity_type"] == 2 else None,
                    "npi_status": record["npi_status"],
                    "source_pulled_at": source_pulled_at,
                    "run_id": run_id,
                },
            )
            inserted = cur.fetchone()[0]
            added += 1 if inserted else 0
            updated += 0 if inserted else 1

            # Child rows: delete + reinsert is the simplest correct upsert for a
            # variable-length collection (addresses, taxonomies) keyed to one parent.
            cur.execute("DELETE FROM provider_addresses WHERE npi = %s", (npi,))
            for addr in record["addresses"]:
                zip5 = addr["zip5"] or None
                has_coord = bool(zip5) and _zip_centroid_exists(conn, zip5)
                cur.execute(
                    """
                    INSERT INTO provider_addresses (npi, address_1, address_2, city, state, zip5, lat, lon, is_primary_practice)
                    VALUES (%(npi)s, %(address_1)s, %(address_2)s, %(city)s, %(state)s, %(zip5)s,
                            (SELECT lat FROM zip_centroids WHERE zip5 = %(zip5)s),
                            (SELECT lon FROM zip_centroids WHERE zip5 = %(zip5)s), true)
                    """,
                    {"npi": npi, **addr},
                )
                if not has_coord:
                    cur.execute(
                        "INSERT INTO anomaly_flags (npi, run_id, flag_type, detail) VALUES (%s, %s, 'missing_coordinate', %s)",
                        (npi, run_id, f"zip5={zip5!r} not found in zip_centroids"),
                    )
                    flagged += 1

            cur.execute("DELETE FROM provider_taxonomies WHERE npi = %s", (npi,))
            if not record["taxonomies"]:
                cur.execute(
                    "INSERT INTO anomaly_flags (npi, run_id, flag_type, detail) VALUES (%s, %s, 'missing_taxonomy', 'no taxonomies on record')",
                    (npi, run_id),
                )
                flagged += 1
            for tax in record["taxonomies"]:
                if tax["code"] not in known_taxonomy_codes:
                    cur.execute(
                        "INSERT INTO anomaly_flags (npi, run_id, flag_type, detail) VALUES (%s, %s, 'missing_taxonomy', %s)",
                        (npi, run_id, f"code {tax['code']!r} not in taxonomy_reference"),
                    )
                    flagged += 1
                    continue
                cur.execute(
                    "INSERT INTO provider_taxonomies (npi, taxonomy_code, is_primary) VALUES (%s, %s, %s)",
                    (npi, tax["code"], tax["is_primary"]),
                )
    conn.commit()
    return added, updated, flagged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--states", required=True, help="Comma-separated state codes, e.g. NC or NC,CA,MT")
    args = parser.parse_args()
    states = [s.strip().upper() for s in args.states.split(",") if s.strip()]

    conn = _connect()
    _apply_schema(conn)

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO ingestion_runs (states_pulled) VALUES (%s) RETURNING id, started_at",
            (states,),
        )
        run_id, started_at = cur.fetchone()
    conn.commit()
    source_pulled_at = started_at.isoformat()
    print(f"ingestion_run {run_id} started {started_at}")

    tax_count = _load_taxonomy_reference(conn)
    print(f"taxonomy_reference: {tax_count} codes upserted")

    zip_count = _load_zip_centroids(conn)
    print(f"zip_centroids: {zip_count} rows upserted")

    known_taxonomy_codes = _known_taxonomy_codes(conn)

    total_added = total_updated = total_flagged = 0
    for state in states:
        print(f"ingesting {state}...")
        added, updated, flagged = _ingest_state(conn, state, str(run_id), source_pulled_at, known_taxonomy_codes)
        print(f"  {state}: {added} added, {updated} updated, {flagged} anomalies flagged")
        total_added += added
        total_updated += updated
        total_flagged += flagged

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE ingestion_runs SET completed_at = now(), records_added = %s, records_updated = %s, records_flagged = %s WHERE id = %s",
            (total_added, total_updated, total_flagged, run_id),
        )
    conn.commit()
    conn.close()

    print(f"\ningestion_run {run_id} complete: "
          f"{total_added} added, {total_updated} updated, {total_flagged} anomalies flagged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
