"""
LocationSearchPort (design.md §4.2) — the swappable proximity-search interface — and
its only implementation this build, HaversineSqlLocationSearch: a state-scoped full
scan computing great-circle distance in SQL. Explicitly a stub (no PostGIS/ES geo);
future implementations swap in behind the same Protocol without touching callers.
"""

from __future__ import annotations

import math
from typing import Literal, NamedTuple, Protocol, TypedDict

from psycopg_pool import ConnectionPool

EARTH_RADIUS_MILES = 3959.0
MILES_PER_DEGREE_LAT = 69.0


class Coordinate(NamedTuple):
    lat: float
    lon: float


class ProviderMatch(TypedDict):
    npi: str
    name: str
    entity_type: int
    npi_status: str
    taxonomy_code: str
    taxonomy_description: str
    address: dict
    distance_miles: float
    accepting_new_patients: str
    lineage: dict


class LocationSearchPort(Protocol):
    def search_near(
        self,
        origin: Coordinate,
        radius_miles: float,
        taxonomy_codes: list[str],
        limit: int,
        accepting_new_patients: bool | None,
        entity_type: Literal["individual", "organization"] | None = None,
        include_deactivated: bool = False,
    ) -> list[ProviderMatch]: ...


def _bounding_box(origin: Coordinate, radius_miles: float) -> tuple[float, float, float, float]:
    """Coarse bounding box around origin, padded generously (no trig precision needed —
    this only narrows the candidate-state lookup, the real filter is haversine)."""
    lat_delta = radius_miles / MILES_PER_DEGREE_LAT
    lon_denominator = max(math.cos(math.radians(origin.lat)), 0.1)
    lon_delta = radius_miles / (MILES_PER_DEGREE_LAT * lon_denominator)
    return (
        origin.lat - lat_delta, origin.lat + lat_delta,
        origin.lon - lon_delta, origin.lon + lon_delta,
    )


_SEARCH_SQL = """
    SELECT * FROM (
        SELECT p.npi, p.entity_type, p.first_name, p.last_name, p.organization_name,
               p.npi_status, p.source, p.source_pulled_at, p.ingestion_run_id,
               t.taxonomy_code, tr.classification, tr.specialization,
               a.address_1, a.address_2, a.city, a.state, a.zip5,
               3959 * acos(LEAST(1.0, GREATEST(-1.0,
                 cos(radians(%(origin_lat)s)) * cos(radians(a.lat)) * cos(radians(a.lon) - radians(%(origin_lon)s))
                 + sin(radians(%(origin_lat)s)) * sin(radians(a.lat))
               ))) AS distance_miles
        FROM provider_addresses a
        JOIN providers p ON p.npi = a.npi
        JOIN provider_taxonomies t ON t.npi = p.npi
        JOIN taxonomy_reference tr ON tr.code = t.taxonomy_code
        WHERE t.taxonomy_code = ANY(%(taxonomy_codes)s)
          AND a.state = ANY(%(candidate_states)s)
          AND a.lat IS NOT NULL
          AND (%(include_deactivated)s OR p.npi_status = 'active')
          AND (%(entity_type)s::smallint IS NULL OR p.entity_type = %(entity_type)s::smallint)
    ) candidates
    WHERE distance_miles <= %(radius_miles)s
    ORDER BY distance_miles ASC
    LIMIT %(limit)s
"""

_ENTITY_TYPE_CODE = {"individual": 1, "organization": 2}


class HaversineSqlLocationSearch:
    def __init__(self, pool: ConnectionPool):
        self._pool = pool

    def _candidate_states(self, origin: Coordinate, radius_miles: float) -> list[str]:
        lat_min, lat_max, lon_min, lon_max = _bounding_box(origin, radius_miles)
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT state FROM zip_centroids "
                "WHERE lat BETWEEN %s AND %s AND lon BETWEEN %s AND %s",
                (lat_min, lat_max, lon_min, lon_max),
            )
            return [row[0] for row in cur.fetchall()]

    def search_near(
        self,
        origin: Coordinate,
        radius_miles: float,
        taxonomy_codes: list[str],
        limit: int,
        accepting_new_patients: bool | None,
        entity_type: Literal["individual", "organization"] | None = None,
        include_deactivated: bool = False,
    ) -> list[ProviderMatch]:
        # No provider ever has a confirmed accepting_new_patients=False this build
        # (design.md P6/§4.1 — the column doesn't exist yet); "unknown" is the only
        # non-true value that exists, so an explicit False filter can never match.
        if accepting_new_patients is False:
            return []

        candidate_states = self._candidate_states(origin, radius_miles)
        if not candidate_states:
            return []

        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                _SEARCH_SQL,
                {
                    "origin_lat": origin.lat,
                    "origin_lon": origin.lon,
                    "taxonomy_codes": taxonomy_codes,
                    "candidate_states": candidate_states,
                    "include_deactivated": include_deactivated,
                    "entity_type": _ENTITY_TYPE_CODE.get(entity_type) if entity_type else None,
                    "radius_miles": radius_miles,
                    "limit": limit,
                },
            )
            columns = [d.name for d in cur.description]
            rows = cur.fetchall()

        results: list[ProviderMatch] = []
        for row in rows:
            record = dict(zip(columns, row))
            name = (
                record["organization_name"]
                if record["entity_type"] == 2
                else f"{record['first_name']} {record['last_name']}"
            )
            results.append(ProviderMatch(
                npi=record["npi"],
                name=name,
                entity_type=record["entity_type"],
                npi_status=record["npi_status"],
                taxonomy_code=record["taxonomy_code"],
                taxonomy_description=record["specialization"] or record["classification"],
                address={
                    "address_1": record["address_1"],
                    "address_2": record["address_2"],
                    "city": record["city"],
                    "state": record["state"],
                    "zip5": record["zip5"],
                },
                distance_miles=round(record["distance_miles"], 1),
                accepting_new_patients="unknown",
                lineage={
                    "source": record["source"],
                    "source_pulled_at": record["source_pulled_at"].isoformat(),
                    "ingestion_run_id": str(record["ingestion_run_id"]) if record["ingestion_run_id"] else None,
                },
            ))
        return results


def sanitize_location(zip: str | None, lat: float | None, lon: float | None) -> str:
    """PHI-safe location summary for logs (design.md §11/§12.1): never log the raw ZIP
    or exact coordinate a caller searched from — bucket to a 3-digit ZIP prefix or a
    whole-degree region instead. Used explicitly by call sites that log a search
    request (main.py's search_providers), not applied automatically to anything — the
    request-logging middleware itself never inspects the body at all, so it structurally
    cannot leak a raw location regardless of whether a call site remembers to sanitize."""
    if zip:
        return f"zip3:{zip[:3]}"
    if lat is not None and lon is not None:
        return f"region:{round(lat)},{round(lon)}"
    return "unknown"


def resolve_zip_to_coordinate(pool: ConnectionPool, zip5: str) -> Coordinate | None:
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT lat, lon FROM zip_centroids WHERE zip5 = %s", (zip5,))
        row = cur.fetchone()
        return Coordinate(lat=row[0], lon=row[1]) if row else None
