"""Shared fixtures: the service's recorded tool outputs, a scripted model, and live Ollama.

`fixtures/service_outputs.json` holds what the real scoring service returned for each tool call
(record_service_outputs.py). Live-model tests request `ensure_ollama_model_available`, which —
like mcp-agent's (docs/phase6/decisions.md H50) — hard-fails rather than skipping when Ollama
isn't reachable.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import pytest

from outcome_prediction_agent.testing import ReplayService

FIXTURES = Path(__file__).parent / "fixtures"
OUTPUTS = json.loads((FIXTURES / "service_outputs.json").read_text())
TOOLS = json.loads((FIXTURES / "service_tools.json").read_text())
PATIENT = OUTPUTS["patient_id"]


@pytest.fixture
def service() -> ReplayService:
    return ReplayService(OUTPUTS, TOOLS)


OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:1b")


@pytest.fixture(scope="session")
def ensure_ollama_model_available() -> None:
    try:
        names = {m["name"] for m in httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=5.0).json().get("models", [])}
        if OLLAMA_MODEL not in names:
            with httpx.stream("POST", f"{OLLAMA_HOST}/api/pull", json={"name": OLLAMA_MODEL}, timeout=300.0) as r:
                r.raise_for_status()
                for _ in r.iter_lines():
                    pass
    except Exception as exc:
        pytest.fail(f"Ollama at {OLLAMA_HOST} is required for this test but the model {OLLAMA_MODEL!r} "
                    f"could not be made available: {exc}", pytrace=False)
