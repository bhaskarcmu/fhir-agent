"""
Error-taxonomy tests (design.md §8.4) for the validation-error class. These never
reach the database — Pydantic validation fails before any DB call — so they run
without requiring Postgres, unlike test_location_search.py / test_registry.py.
"""

from fastapi.testclient import TestClient

from provider_registry.main import app

client = TestClient(app)


def test_search_missing_taxonomy_codes_is_400_validation_error():
    resp = client.post("/v1/providers/search", json={"location": {"zip": "27514"}, "taxonomy_codes": []})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error_type"] == "validation_error"
    assert "message" in body


def test_search_location_with_neither_zip_nor_latlon_is_400():
    resp = client.post(
        "/v1/providers/search",
        json={"location": {}, "taxonomy_codes": ["207RE0101X"]},
    )
    assert resp.status_code == 400
    assert resp.json()["error_type"] == "validation_error"


def test_search_location_with_both_zip_and_latlon_is_400():
    resp = client.post(
        "/v1/providers/search",
        json={"location": {"zip": "27514", "lat": 35.9, "lon": -79.0}, "taxonomy_codes": ["207RE0101X"]},
    )
    assert resp.status_code == 400


def test_search_malformed_taxonomy_code_is_400_validation_error():
    # Mirrors provider-mcp-server's identical pattern constraint (design.md §14 Risks,
    # decisions.md P19) — a caller hitting this HTTP API directly, not through MCP, must
    # get the same 400 instead of a silently misleading zero-result search.
    resp = client.post(
        "/v1/providers/search",
        json={"location": {"zip": "27514"}, "taxonomy_codes": ["207RE0101"]},  # dropped trailing "X"
    )
    assert resp.status_code == 400
    assert resp.json()["error_type"] == "validation_error"


def test_search_radius_out_of_bounds_is_400():
    resp = client.post(
        "/v1/providers/search",
        json={"location": {"zip": "27514"}, "taxonomy_codes": ["207RE0101X"], "radius_miles": 500},
    )
    assert resp.status_code == 400


def test_get_provider_malformed_npi_is_400():
    resp = client.get("/v1/providers/not-a-valid-npi")
    assert resp.status_code == 400
    assert resp.json()["error_type"] == "validation_error"


def test_resolve_specialty_empty_query_is_400():
    resp = client.post("/v1/taxonomy/resolve", json={"query": ""})
    assert resp.status_code == 400


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
