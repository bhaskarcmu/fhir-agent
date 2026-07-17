"""HTTP mocked, no network — mirrors mcp-agent's test_e2e_demo_flow.py mocking style."""

from unittest.mock import MagicMock, patch

import httpx

from provider_mcp import registry_client


def _mock_response(status_code: int, json_body: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    return resp


def test_resolve_specialty_posts_and_returns_body():
    body = {"query": "endocrinologist", "status": "ok", "matches": []}
    with patch("provider_mcp.registry_client.httpx.post", return_value=_mock_response(200, body)) as mock_post:
        result = registry_client.resolve_specialty("endocrinologist")

    assert result == body
    url, kwargs = mock_post.call_args
    assert url[0].endswith("/v1/taxonomy/resolve")
    assert kwargs["json"] == {"query": "endocrinologist"}


def test_search_providers_near_posts_arguments_as_is():
    body = {"status": "ok", "count": 0, "results": []}
    args = {"location": {"zip": "27514"}, "taxonomy_codes": ["207RE0101X"]}
    with patch("provider_mcp.registry_client.httpx.post", return_value=_mock_response(200, body)) as mock_post:
        result = registry_client.search_providers_near(args)

    assert result == body
    _, kwargs = mock_post.call_args
    assert kwargs["json"] == args


def test_get_provider_uses_get_with_npi_in_path():
    body = {"npi": "1234567890", "name": "Jane Doe"}
    with patch("provider_mcp.registry_client.httpx.get", return_value=_mock_response(200, body)) as mock_get:
        result = registry_client.get_provider("1234567890")

    assert result == body
    url = mock_get.call_args[0][0]
    assert url.endswith("/v1/providers/1234567890")


def test_error_body_from_registry_passed_through_unwrapped():
    body = {"error_type": "not_found", "message": "no provider with NPI 9999999999"}
    with patch("provider_mcp.registry_client.httpx.get", return_value=_mock_response(404, body)):
        result = registry_client.get_provider("9999999999")

    assert result == body  # passed through as-is, not re-wrapped


def test_connection_failure_maps_to_upstream_unavailable():
    with patch("provider_mcp.registry_client.httpx.post",
               side_effect=httpx.ConnectError("connection refused")):
        result = registry_client.resolve_specialty("endocrinologist")

    assert result["error_type"] == "upstream_unavailable"


def test_5xx_with_no_error_body_gets_wrapped():
    with patch("provider_mcp.registry_client.httpx.get", return_value=_mock_response(502, {})):
        result = registry_client.get_provider("1234567890")

    assert result["error_type"] == "upstream_unavailable"


def test_non_json_response_maps_to_upstream_unavailable():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.side_effect = ValueError("not json")
    with patch("provider_mcp.registry_client.httpx.get", return_value=resp):
        result = registry_client.get_provider("1234567890")

    assert result["error_type"] == "upstream_unavailable"
