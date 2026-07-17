"""
Concrete JSON Schemas for the three MCP tools — the exact shapes from design.md §8.3,
not placeholders. The `mcp` SDK's `call_tool()` decorator validates incoming arguments
against these automatically (jsonschema) before our handler ever runs — this is real,
free validation-error enforcement at the protocol layer, not something we reimplement.
"""

from __future__ import annotations

RESOLVE_SPECIALTY_SCHEMA = {
    "type": "object",
    "required": ["query"],
    "additionalProperties": False,
    "properties": {
        "query": {"type": "string", "minLength": 1, "maxLength": 200},
    },
}

SEARCH_PROVIDERS_NEAR_SCHEMA = {
    "type": "object",
    "required": ["location", "taxonomy_codes"],
    "additionalProperties": False,
    "properties": {
        "location": {
            "oneOf": [
                {
                    "type": "object",
                    "required": ["zip"],
                    "additionalProperties": False,
                    "properties": {"zip": {"type": "string", "pattern": "^[0-9]{5}$"}},
                },
                {
                    "type": "object",
                    "required": ["lat", "lon"],
                    "additionalProperties": False,
                    "properties": {
                        "lat": {"type": "number", "minimum": -90, "maximum": 90},
                        "lon": {"type": "number", "minimum": -180, "maximum": 180},
                    },
                },
            ]
        },
        "taxonomy_codes": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 10,
        },
        "radius_miles": {"type": "number", "exclusiveMinimum": 0, "maximum": 200, "default": 25},
        "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
        "accepting_new_patients": {"type": ["boolean", "null"], "default": None},
        "entity_type": {
            "type": ["string", "null"],
            "enum": ["individual", "organization", None],
            "default": None,
        },
    },
}

GET_PROVIDER_SCHEMA = {
    "type": "object",
    "required": ["npi"],
    "additionalProperties": False,
    "properties": {
        "npi": {"type": "string", "pattern": "^[0-9]{10}$"},
    },
}
