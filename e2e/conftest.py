"""
Fixtures for the end-to-end golden-path suite.

The stack's FHIR server is in-memory (`jdbc:h2:mem:hapi` in docker-compose.yml), so it boots
empty every time. Adjudication fails closed (R17.5): a member with no FHIR record yields risk
UNKNOWN, and the claim pends on `clinical-safety-unavailable`. The golden paths must therefore
seed the demo members' clinical records before asserting outcomes — without this, every path
that should approve pends instead, and the suite is testing the absence of its own fixtures.

Seeding reuses the committed demo seeder rather than restating the fixtures here, so there is
one reproducible generator per fixture (R19 golden-fixture governance). It is imported by path,
the same way `data/scripts/test_load.py` imports `load.py`.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import httpx
import pytest

_SEEDER_PATH = Path(__file__).resolve().parents[1] / "data" / "scripts" / "seed_claims_demo.py"
_spec = importlib.util.spec_from_file_location("seed_claims_demo", _SEEDER_PATH)
_seeder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_seeder)


@pytest.fixture(scope="session", autouse=True)
def seed_fhir_patients() -> None:
    """Give every demo member a clinical record, so the safety check runs instead of pending.

    Session-scoped and idempotent (the seeder PUTs fixed logical ids), so re-running the suite
    against a warm stack is harmless.
    """
    with httpx.Client(timeout=30) as client:
        try:
            _seeder.seed_patients(client)
        except httpx.HTTPError as exc:  # FHIR unreachable → the suite cannot be meaningful
            pytest.skip(f"could not seed FHIR fixtures: {exc}")
