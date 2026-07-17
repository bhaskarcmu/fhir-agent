"""Pure-logic test for the defense-in-depth rate limiter (design.md §12.1) — no DB."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from provider_registry.ratelimit import RateLimitMiddleware


def _make_app(max_requests: int) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, max_requests=max_requests, window_seconds=60)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return app


def test_requests_within_limit_succeed():
    client = TestClient(_make_app(max_requests=3))
    for _ in range(3):
        assert client.get("/ping").status_code == 200


def test_requests_beyond_limit_are_429():
    client = TestClient(_make_app(max_requests=3))
    for _ in range(3):
        client.get("/ping")
    resp = client.get("/ping")
    assert resp.status_code == 429
    assert resp.json()["error_type"] == "rate_limited"
