"""
Provider Registry Service — FastAPI application.

Internal-only service (never on the Kong edge, design.md §9): registry, taxonomy,
and location modules behind one deployable, matching triage-service's shape.

Routes are `/v1/...` (design.md §8.3 contract-versioning note) — a deliberate small
improvement for a new service, not a retrofit of existing unversioned routes.

Environment variables:
  DATABASE_URL                Postgres connection string (required) — see db.py
  RATE_LIMIT_REQUESTS         Max requests/window/caller (default 60) — see ratelimit.py
  RATE_LIMIT_WINDOW_SECONDS   Window length in seconds (default 60)
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Path

from . import location, registry as registry_module, taxonomy
from .db import get_pool
from .errors import NotFoundError, register_error_handlers
from .logging_middleware import RequestLoggingMiddleware
from .models import (
    HealthResponse,
    LocationInput,
    ProviderRecord,
    ResolveSpecialtyRequest,
    ResolveSpecialtyResponse,
    SearchProvidersRequest,
    SearchProvidersResponse,
    TaxonomyMatch,
)
from .ratelimit import RateLimitMiddleware

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
log = logging.getLogger("provider_registry")

VERSION = "0.1.0"

app = FastAPI(
    title="Provider Registry Service",
    description="Canonical provider registry: taxonomy resolution + haversine proximity search.",
    version=VERSION,
)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)  # outermost: sees the final status, incl. 429s
register_error_handlers(app)


def _load_taxonomy_rows() -> list[taxonomy.TaxonomyRow]:
    pool = get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT code, grouping, classification, specialization, definition, nucc_version "
            "FROM taxonomy_reference"
        )
        columns = [d.name for d in cur.description]
        return [taxonomy.TaxonomyRow(**dict(zip(columns, row))) for row in cur.fetchall()]


@app.get("/health", response_model=HealthResponse, tags=["ops"])
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=VERSION)


@app.post(
    "/v1/taxonomy/resolve",
    response_model=ResolveSpecialtyResponse,
    tags=["taxonomy"],
    summary="Resolve free-text clinical need to NUCC taxonomy codes",
)
def resolve_specialty(request: ResolveSpecialtyRequest) -> ResolveSpecialtyResponse:
    rows = _load_taxonomy_rows()
    result = taxonomy.resolve(request.query, rows)
    matches = [
        TaxonomyMatch(
            code=c.row.code,
            grouping=c.row.grouping,
            classification=c.row.classification,
            specialization=c.row.specialization,
            score=c.score,
            nucc_version=c.row.nucc_version,
        )
        for c in result.candidates
    ]
    return ResolveSpecialtyResponse(query=request.query, status=result.status, matches=matches)


@app.post(
    "/v1/providers/search",
    response_model=SearchProvidersResponse,
    tags=["providers"],
    summary="Search nearest providers matching taxonomy codes and filters",
)
def search_providers(request: SearchProvidersRequest) -> SearchProvidersResponse:
    log.info(
        "search_providers request location=%s radius_miles=%s",
        location.sanitize_location(request.location.zip, request.location.lat, request.location.lon),
        request.radius_miles,
    )
    pool = get_pool()
    origin = _resolve_origin(request.location, pool)
    if origin is None:
        return SearchProvidersResponse(
            origin=None, status="ambiguous", reason="zip_not_found", count=0, results=[],
        )

    search = location.HaversineSqlLocationSearch(pool)
    matches = search.search_near(
        origin=origin,
        radius_miles=request.radius_miles,
        taxonomy_codes=request.taxonomy_codes,
        limit=request.limit,
        accepting_new_patients=request.accepting_new_patients,
        entity_type=request.entity_type,
    )
    return SearchProvidersResponse(
        origin={
            "lat": origin.lat,
            "lon": origin.lon,
            "resolved_from": f"zip:{request.location.zip}" if request.location.zip else "latlon",
        },
        status="ok",
        count=len(matches),
        results=matches,
    )


def _resolve_origin(loc: LocationInput, pool) -> location.Coordinate | None:
    if loc.zip is not None:
        return location.resolve_zip_to_coordinate(pool, loc.zip)
    return location.Coordinate(lat=loc.lat, lon=loc.lon)


@app.get(
    "/v1/providers/{npi}",
    response_model=ProviderRecord,
    tags=["providers"],
    summary="Fetch a provider record by NPI, with lineage",
)
def get_provider(npi: str = Path(pattern=r"^[0-9]{10}$")) -> ProviderRecord:
    pool = get_pool()
    reg = registry_module.ProviderRegistry(pool)
    record = reg.get_provider(npi)
    if record is None:
        raise NotFoundError(f"no provider with NPI {npi}")
    return ProviderRecord(**record)
