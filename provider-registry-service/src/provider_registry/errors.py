"""
Error taxonomy (design.md §8.4): validation_error -> 400, not_found -> 404,
upstream_unavailable -> 502/503. Ambiguous and no-results are NOT errors — they're
normal 200 responses with a `status` field (see models.py) — so they have no
representation here.
"""

from __future__ import annotations

import logging

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

log = logging.getLogger("provider_registry")


class NotFoundError(Exception):
    def __init__(self, message: str):
        self.message = message


class UpstreamUnavailableError(Exception):
    def __init__(self, message: str):
        self.message = message


def _error_body(error_type: str, message: str, field: str | None = None) -> dict:
    body: dict = {"error_type": error_type, "message": message}
    if field is not None:
        body["field"] = field
    return body


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
        return JSONResponse(
            status_code=400,
            content=_error_body("validation_error", first.get("msg", "invalid request"), field or None),
        )

    @app.exception_handler(NotFoundError)
    async def _not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content=_error_body("not_found", exc.message))

    @app.exception_handler(UpstreamUnavailableError)
    async def _upstream_handler(request: Request, exc: UpstreamUnavailableError) -> JSONResponse:
        return JSONResponse(status_code=503, content=_error_body("upstream_unavailable", exc.message))

    @app.exception_handler(psycopg.OperationalError)
    async def _db_operational_handler(request: Request, exc: psycopg.OperationalError) -> JSONResponse:
        log.error("Database unavailable: %s", exc)
        return JSONResponse(
            status_code=503,
            content=_error_body("upstream_unavailable", "registry database is unavailable"),
        )
