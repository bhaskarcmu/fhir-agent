"""The agent's only connection to the outside world: the scoring service's published tools, over
HTTP (design.md §1, §9). No model code and no FHIR client are imported here."""
from __future__ import annotations

import os

import httpx

DEFAULT_URL = "http://localhost:8005"


class ServiceUnavailable(RuntimeError):
    """The scoring service couldn't be reached, or answered with a server error."""


class ToolRefused(ValueError):
    """The service refused the call (unknown tool, or arguments outside its schema)."""


class ServiceTools:
    def __init__(self, base_url: str | None = None, timeout: float = 30.0):
        self.base_url = (base_url or os.environ.get("OUTCOME_PREDICTION_URL") or DEFAULT_URL).rstrip("/")
        self.timeout = timeout

    def _send(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = httpx.request(method, self.base_url + path, timeout=self.timeout, **kwargs)
        except httpx.HTTPError as e:
            raise ServiceUnavailable(f"{self.base_url} unreachable: {e}") from e
        if response.status_code >= 500:
            raise ServiceUnavailable(f"{path}: HTTP {response.status_code}")
        return response

    def definitions(self) -> list[dict]:
        """The tools the service allows — the agent offers the model exactly these."""
        return self._send("GET", "/agent-tools").json()

    def call(self, name: str, args: dict) -> dict:
        response = self._send("POST", f"/agent-tools/{name}", json=args)
        if response.status_code in (404, 422):
            raise ToolRefused(str(response.json().get("detail")))
        response.raise_for_status()
        return response.json()
