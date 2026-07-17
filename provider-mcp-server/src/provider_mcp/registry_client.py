"""
Thin httpx wrapper over provider-registry-service's internal HTTP API — the same
"call the deterministic service over HTTP, don't import it" pattern mcp-agent already
uses for triage-service (design.md §8.1).

Environment:
  PROVIDER_REGISTRY_URL   Base URL of provider-registry-service (default http://localhost:8002)
"""

from __future__ import annotations

import os

import httpx

TIMEOUT = 30.0


def _base_url() -> str:
    return os.environ.get("PROVIDER_REGISTRY_URL", "http://localhost:8002").rstrip("/")


def resolve_specialty(query: str) -> dict:
    return _post("/v1/taxonomy/resolve", {"query": query})


def search_providers_near(arguments: dict) -> dict:
    return _post("/v1/providers/search", arguments)


def get_provider(npi: str) -> dict:
    return _get(f"/v1/providers/{npi}")


def _post(path: str, body: dict) -> dict:
    try:
        resp = httpx.post(f"{_base_url()}{path}", json=body, timeout=TIMEOUT)
    except httpx.RequestError as exc:
        return _unavailable(exc)
    return _handle_response(resp)


def _get(path: str) -> dict:
    try:
        resp = httpx.get(f"{_base_url()}{path}", timeout=TIMEOUT)
    except httpx.RequestError as exc:
        return _unavailable(exc)
    return _handle_response(resp)


def _unavailable(exc: httpx.RequestError) -> dict:
    return {
        "error_type": "upstream_unavailable",
        "message": f"cannot reach provider-registry-service at {_base_url()}: {exc}",
    }


def _handle_response(resp: httpx.Response) -> dict:
    # provider-registry-service's own error taxonomy (design.md §8.4) already returns a
    # {"error_type": ..., "message": ...} body on 4xx/5xx -- pass it through as-is rather
    # than re-wrapping it, so the agent sees the same error shape regardless of whether
    # the failure happened here or at the HTTP layer.
    try:
        body = resp.json()
    except ValueError:
        return {
            "error_type": "upstream_unavailable",
            "message": f"non-JSON response from provider-registry-service (HTTP {resp.status_code})",
        }
    if resp.status_code >= 500 and "error_type" not in body:
        body = {"error_type": "upstream_unavailable", "message": f"registry returned HTTP {resp.status_code}"}
    return body
