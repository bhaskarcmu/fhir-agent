"""
Deterministic, non-authoritative summary of an ingestion run.

This renders the *already-completed* run (from ingestion_runs + anomaly_flags, read by
tools.IngestionClient) into plain language. It never re-derives or alters the counts — it
only narrates them. Used directly when no LLM key is available, and as the grounding the
LLM elaborates when one is (design.md §3.2 — "AI curation mostly means summarizing and
flagging, not resolving conflicts").
"""

from __future__ import annotations


def render_summary(run: dict) -> str:
    """Return a plain-language summary of an ingestion run dict."""
    states = ", ".join(run.get("states_pulled") or []) or "(none)"
    fetched = run.get("states_freshly_fetched") or []
    added = run.get("records_added", 0)
    updated = run.get("records_updated", 0)
    flagged = run.get("records_flagged", 0)

    parts: list[str] = [
        f"Ingestion run {run.get('run_id', 'n/a')} for {states} complete.",
        f"{added} record(s) added, {updated} updated, {flagged} anomalies flagged.",
    ]

    if fetched:
        parts.append(f"Freshly fetched from NPPES this run: {', '.join(fetched)}.")

    breakdown = run.get("anomaly_breakdown") or {}
    if breakdown:
        items = [f"{count} {flag_type}" for flag_type, count in sorted(breakdown.items())]
        parts.append("Anomaly breakdown: " + "; ".join(items) + ".")
    else:
        parts.append("No anomalies flagged.")

    samples = run.get("sample_anomalies") or []
    if samples:
        sample_lines = [f"NPI {s['npi']} — {s['flag_type']}: {s['detail']}" for s in samples[:3]]
        parts.append("Sample flags: " + " | ".join(sample_lines))

    return " ".join(parts)
