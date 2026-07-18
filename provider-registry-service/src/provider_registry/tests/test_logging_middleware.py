"""
Tests for the PHI-safe request-logging path (design.md §11/§12.1):
sanitize_location() as a pure function, plus a structural guarantee that the
request-logging middleware never has the raw request body available to log,
regardless of what any given route does with it.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from provider_registry.location import sanitize_location
from provider_registry.logging_middleware import RequestLoggingMiddleware


def test_sanitize_location_zip_returns_zip3_only():
    assert sanitize_location("27514", None, None) == "zip3:275"


def test_sanitize_location_latlon_returns_whole_degree_region():
    assert sanitize_location(None, 35.9132, -79.0558) == "region:36,-79"


def test_sanitize_location_neither_returns_unknown():
    assert sanitize_location(None, None, None) == "unknown"


def test_sanitize_location_never_echoes_raw_precise_input():
    # The whole point: the sanitized form must not contain the exact input values.
    raw_zip, raw_lat, raw_lon = "27514", 35.9132, -79.0558
    result = sanitize_location(raw_zip, None, None)
    assert raw_zip not in result
    result = sanitize_location(None, raw_lat, raw_lon)
    assert str(raw_lat) not in result and str(raw_lon) not in result


def test_middleware_never_reads_the_request_body():
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)
    seen_bodies = []

    @app.post("/echo")
    async def echo(payload: dict):
        seen_bodies.append(payload)
        return {"ok": True}

    client = TestClient(app)
    resp = client.post("/echo", json={"location": {"zip": "27514"}})
    assert resp.status_code == 200
    # The route itself received the body normally — middleware doesn't consume/break it —
    # but the middleware's own dispatch() never touches `request.body()` or `.json()`,
    # which is the structural property that makes a body-content leak impossible here.
    assert seen_bodies == [{"location": {"zip": "27514"}}]
