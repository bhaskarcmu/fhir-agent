"""
Coarse per-caller rate limit — defense-in-depth against a compromised/buggy internal
caller (design.md §12.1). Not a substitute for correct IAM/VPC scoping; in-memory only,
so it resets per instance and doesn't coordinate across replicas. That's an accepted
limitation for a single-instance internal prototype, not a distributed rate limiter.

Environment variables:
  RATE_LIMIT_REQUESTS         Max requests per window per caller (default 60)
  RATE_LIMIT_WINDOW_SECONDS   Window length in seconds (default 60)
"""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int | None = None, window_seconds: float | None = None):
        super().__init__(app)
        self._max_requests = max_requests or int(os.environ.get("RATE_LIMIT_REQUESTS", "60"))
        self._window_seconds = window_seconds or float(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _caller_key(self, request: Request) -> str:
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next):
        key = self._caller_key(request)
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self._window_seconds:
                hits.popleft()
            if len(hits) >= self._max_requests:
                return JSONResponse(
                    status_code=429,
                    content={"error_type": "rate_limited", "message": "too many requests"},
                )
            hits.append(now)
        return await call_next(request)
