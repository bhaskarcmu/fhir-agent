"""
DB-backed end-to-end route tests — exercises main.py's wiring (origin resolution,
response construction), not just the location/registry/taxonomy modules directly.
"""

from fastapi.testclient import TestClient

from provider_registry.main import app


def test_search_by_zip_happy_path(db_pool):
    client = TestClient(app)
    resp = client.post(
        "/v1/providers/search",
        json={"location": {"zip": "27514"}, "taxonomy_codes": ["207RE0101X"], "radius_miles": 25},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["origin"]["resolved_from"] == "zip:27514"
    assert body["count"] >= 1
    assert body["results"][0]["npi"] == "1111111111"


def test_search_unresolvable_zip_is_ambiguous_not_an_error(db_pool):
    client = TestClient(app)
    resp = client.post(
        "/v1/providers/search",
        json={"location": {"zip": "00000"}, "taxonomy_codes": ["207RE0101X"]},
    )
    assert resp.status_code == 200  # not an error — design.md §8.4
    body = resp.json()
    assert body["status"] == "ambiguous"
    assert body["reason"] == "zip_not_found"
    assert body["count"] == 0


def test_search_no_matches_is_200_not_an_error(db_pool):
    client = TestClient(app)
    resp = client.post(
        "/v1/providers/search",
        json={"location": {"zip": "27514"}, "taxonomy_codes": ["207RC0000X"], "radius_miles": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["count"] == 0
    assert body["results"] == []


def test_get_provider_by_npi(db_pool):
    client = TestClient(app)
    resp = client.get("/v1/providers/1111111111")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Jane Doe"


def test_get_provider_not_found_is_404(db_pool):
    client = TestClient(app)
    resp = client.get("/v1/providers/9999999999")
    assert resp.status_code == 404
    assert resp.json()["error_type"] == "not_found"


def test_resolve_specialty_happy_path(db_pool):
    client = TestClient(app)
    resp = client.post("/v1/taxonomy/resolve", json={"query": "endocrinologist"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["matches"][0]["code"] == "207RE0101X"
