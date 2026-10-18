"""Conversational access to Phase 8's 12-month hospitalization risk service (O15).

The model orchestrates — it works out which patient is meant and calls the service's tools.
Every reply the clinician sees is built in code from the service's own output (`explain.py`),
so no number, reason or band appears that the service didn't return (FR-A2, O69).
"""
