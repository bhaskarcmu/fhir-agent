"""Pydantic request/response models — the concrete schemas from design.md §8.3."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class HealthResponse(BaseModel):
    status: str
    version: str


# ── resolve_specialty ──────────────────────────────────────────────────────

class ResolveSpecialtyRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)


class TaxonomyMatch(BaseModel):
    code: str
    grouping: str
    classification: str
    specialization: str | None
    score: float
    nucc_version: str


class ResolveSpecialtyResponse(BaseModel):
    query: str
    status: Literal["ok", "ambiguous", "no_match"] = "ok"
    matches: list[TaxonomyMatch]


# ── search_providers_near ──────────────────────────────────────────────────

class LocationInput(BaseModel):
    zip: str | None = Field(default=None, pattern=r"^[0-9]{5}$")
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def _one_of_zip_or_latlon(self) -> "LocationInput":
        has_zip = self.zip is not None
        has_latlon = self.lat is not None and self.lon is not None
        if has_zip == has_latlon:  # neither set, or both set
            raise ValueError("location requires exactly one of: zip, or (lat and lon)")
        return self


class SearchProvidersRequest(BaseModel):
    location: LocationInput
    taxonomy_codes: list[str] = Field(min_length=1, max_length=10)
    radius_miles: float = Field(default=25.0, gt=0, le=200)
    limit: int = Field(default=10, ge=1, le=50)
    accepting_new_patients: bool | None = None
    entity_type: Literal["individual", "organization"] | None = None


class Lineage(BaseModel):
    source: str
    source_pulled_at: str
    ingestion_run_id: str | None


class Address(BaseModel):
    address_1: str
    address_2: str | None = None
    city: str
    state: str
    zip5: str


class ProviderMatch(BaseModel):
    npi: str
    name: str
    entity_type: int
    npi_status: Literal["active", "deactivated"]
    taxonomy_code: str
    taxonomy_description: str
    address: Address
    distance_miles: float
    accepting_new_patients: Literal["true", "false", "unknown"]
    lineage: Lineage


class Origin(BaseModel):
    lat: float
    lon: float
    resolved_from: str


class SearchProvidersResponse(BaseModel):
    origin: Origin | None = None
    status: Literal["ok", "ambiguous"] = "ok"
    reason: str | None = None
    count: int
    results: list[ProviderMatch]


# ── get_provider ────────────────────────────────────────────────────────────

class ProviderTaxonomy(BaseModel):
    taxonomy_code: str
    is_primary: bool


class ProviderRecord(BaseModel):
    npi: str
    entity_type: int
    name: str
    npi_status: Literal["active", "deactivated"]
    addresses: list[Address]
    taxonomies: list[ProviderTaxonomy]
    lineage: Lineage
