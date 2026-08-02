"""
Terminal output formatting for the MCP agent.

Produces readable, projector-friendly output. Risk level gets a visual
indicator so the severity is immediately obvious on a screen.
"""

from __future__ import annotations

RISK_ICONS = {
    "HIGH":     "🚨",
    "MODERATE": "⚠️ ",
    "LOW":      "✅",
}

RISK_LABELS = {
    "HIGH":     "HIGH RISK — Do not dispense without physician review",
    "MODERATE": "MODERATE RISK — Review before dispensing",
    "LOW":      "LOW RISK — Safe to dispense",
}

DIVIDER = "─" * 58

DECISION_ICONS = {
    "DISPENSE":         "✅",
    "DO_NOT_DISPENSE":  "🚨",
    "REVIEW":           "⚠️ ",
}

DECISION_LABELS = {
    "DISPENSE":         "DISPENSE",
    "DO_NOT_DISPENSE":  "DO NOT DISPENSE",
    "REVIEW":           "REVIEW — human decision required",
}


def tool_call_line(tool_name: str, summary: str) -> str:
    return f"  [tool] {tool_name} → {summary}"


def agent_response(text: str) -> str:
    """Format Claude's final narrative response."""
    lines = [
        "",
        DIVIDER,
        text.strip(),
        DIVIDER,
        "",
    ]
    return "\n".join(lines)


def risk_assessment_block(
    patient_name: str,
    risk_level: str,
    assessment_id: str,
    note: str,
) -> str:
    """
    Format a structured risk assessment block for terminal display.
    Used when the agent's response contains a risk assessment result.
    """
    icon = RISK_ICONS.get(risk_level, "❓")
    label = RISK_LABELS.get(risk_level, f"{risk_level} RISK")

    lines = [
        "",
        DIVIDER,
        "REFILL RISK ASSESSMENT",
        f"Patient : {patient_name}",
        DIVIDER,
        "",
        f"{icon}  {label}",
        "",
        note,
        "",
        f"FHIR RiskAssessment ID: {assessment_id}",
        DIVIDER,
        "",
    ]
    return "\n".join(lines)


def decision_block(
    decision: str,
    patient_id: str,
    risk_assessment_id: str | None,
    rationale: str,
    override_reason: str | None = None,
    trace_id: str | None = None,
) -> str:
    """
    Format the agent's final, code-validated decision for terminal display
    (docs/phase6/design.md Section 4.1). Unlike the free-text narrative this
    replaces, the decision line itself is always one of the enum values --
    never LLM-composed prose -- so a reader can trust it at a glance even
    without reading the rationale.

    trace_id is surfaced here deliberately (docs/phase6/telemetry-schema.md
    Section 5) -- a trace ID that only exists inside span context is useless
    to a clinician or a test program that isn't already looking at Jaeger.
    """
    icon = DECISION_ICONS.get(decision, "❓")
    label = DECISION_LABELS.get(decision, decision)

    lines = [
        "",
        DIVIDER,
        "AGENT DECISION",
        DIVIDER,
        "",
        f"{icon}  {label}",
        "",
        rationale.strip(),
    ]

    if override_reason:
        lines += [
            "",
            f"⚠️  Fail-closed override: {override_reason}",
        ]

    lines += [
        "",
        f"Patient ID: {patient_id or '(none)'}",
        f"FHIR RiskAssessment ID: {risk_assessment_id or '(none)'}",
        f"Trace ID: {trace_id or '(none)'}",
        DIVIDER,
        "",
    ]
    return "\n".join(lines)


def error_block(message: str, trace_id: str | None = None) -> str:
    if trace_id:
        return f"\n❌  {message}\n    Trace ID: {trace_id}\n"
    return f"\n❌  {message}\n"


def welcome() -> str:
    lines = [
        "",
        "╔══════════════════════════════════════════════════════╗",
        "║   Agentic Healthcare Platform — Clinical Assistant   ║",
        "╚══════════════════════════════════════════════════════╝",
        "",
        "Type a clinical question or 'quit' to exit.",
        "Examples:",
        "  Check refill risk for patient Kristle Mraz",
        "  Is it safe to refill amoxicillin for Jaqueline Bernhard?",
        "  What medications does patient 544f37bb have?",
        "",
    ]
    return "\n".join(lines)
