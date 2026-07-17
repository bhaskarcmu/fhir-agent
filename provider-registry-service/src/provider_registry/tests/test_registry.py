"""DB-backed tests for the registry module (get_provider by NPI)."""

import pytest

from provider_registry.registry import ProviderRegistry


def test_get_existing_provider_returns_full_record(db_pool):
    reg = ProviderRegistry(db_pool)
    record = reg.get_provider("1111111111")
    assert record is not None
    assert record["npi"] == "1111111111"
    assert record["name"] == "Jane Doe"
    assert record["npi_status"] == "active"
    assert len(record["addresses"]) == 1
    assert len(record["taxonomies"]) == 1
    assert record["lineage"]["source"] == "NPPES"


def test_get_deactivated_provider_still_returns_the_record(db_pool):
    # design.md §4.1: get_provider must still return a deactivated record explicitly,
    # so an existing caller can see why it's stale rather than an unexplained 404.
    reg = ProviderRegistry(db_pool)
    record = reg.get_provider("3333333333")
    assert record is not None
    assert record["npi_status"] == "deactivated"


def test_get_unknown_npi_returns_none(db_pool):
    reg = ProviderRegistry(db_pool)
    assert reg.get_provider("9999999999") is None


def test_organization_provider_uses_organization_name(db_pool):
    reg = ProviderRegistry(db_pool)
    record = reg.get_provider("4444444444")
    assert record["name"] == "Duke Health Endocrinology Center"
    assert record["entity_type"] == 2
