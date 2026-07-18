"""
Request-logging middleware (design.md §11/§12.1's PHI-safe-handling enforcement).

Deliberately structural, not scrub-after-the-fact: this middleware logs only method,
path, status code, and duration — it never reads the request body, so it cannot leak a
raw search location into logs regardless of whether a call site remembers to sanitize.
Route handlers that need to log a location value (main.py's search_providers) call
location.sanitize_location() explicitly before logging it.
"""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

log = logging.getLogger("provider_registry.requests")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000
        log.info(
            "%s %s -> %d (%.1fms)",
            request.method, request.url.path, response.status_code, duration_ms,
        )
        return response
