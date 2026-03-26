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


def error_block(message: str) -> str:
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
