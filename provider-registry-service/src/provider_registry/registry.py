"""Registry module (design.md §4): direct record lookup by NPI, with lineage."""

from __future__ import annotations

from psycopg_pool import ConnectionPool


class ProviderRegistry:
    def __init__(self, pool: ConnectionPool):
        self._pool = pool

    def get_provider(self, npi: str) -> dict | None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT npi, entity_type, first_name, last_name, organization_name, "
                "npi_status, source, source_pulled_at, ingestion_run_id "
                "FROM providers WHERE npi = %s",
                (npi,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            columns = [d.name for d in cur.description]
            provider = dict(zip(columns, row))

            cur.execute(
                "SELECT address_1, address_2, city, state, zip5 FROM provider_addresses WHERE npi = %s",
                (npi,),
            )
            addr_columns = [d.name for d in cur.description]
            addresses = [dict(zip(addr_columns, r)) for r in cur.fetchall()]

            cur.execute(
                "SELECT taxonomy_code, is_primary FROM provider_taxonomies WHERE npi = %s",
                (npi,),
            )
            tax_columns = [d.name for d in cur.description]
            taxonomies = [dict(zip(tax_columns, r)) for r in cur.fetchall()]

        name = (
            provider["organization_name"]
            if provider["entity_type"] == 2
            else f"{provider['first_name']} {provider['last_name']}"
        )
        return {
            "npi": provider["npi"],
            "entity_type": provider["entity_type"],
            "name": name,
            "npi_status": provider["npi_status"],
            "addresses": addresses,
            "taxonomies": taxonomies,
            "lineage": {
                "source": provider["source"],
                "source_pulled_at": provider["source_pulled_at"].isoformat(),
                "ingestion_run_id": str(provider["ingestion_run_id"]) if provider["ingestion_run_id"] else None,
            },
        }
