"""
Terminal output formatting for the MCP agent.

Produces readable, projector-friendly output. Risk level gets a visual
indicator so the severity is immediately obvious on a screen.
"""

from __future__ import annotations

from agent_platform import JudgeResult

# Regulatory label text can run to hundreds of words -- a citation, not a
# research dump. Truncated for terminal display; full_assessment-style
# "give me everything" isn't this function's job.
_CITATION_TEXT_MAX_CHARS = 280

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


def _truncate(text: str | None, max_chars: int = _CITATION_TEXT_MAX_CHARS) -> str | None:
    if not text:
        return None
    text = text.strip()
    return text if len(text) <= max_chars else text[:max_chars].rstrip() + "..."


def _citations_lines(citations: list[dict]) -> list[str]:
    """
    Render M6's post-decision knowledge-base citations (docs/phase6/
    decisions.md H15) -- always supporting evidence for a decision already
    made above, never presented as something that informed it.
    """
    if not citations:
        return []

    lines = ["", "Citations:"]
    for citation in citations:
        lines.append(f"  {citation['drug']}")
        label = citation.get("label")
        if label:
            boxed = _truncate(label.get("boxed_warning"))
            if boxed:
                lines.append(f"    Boxed warning: {boxed}")
            contraindications = _truncate(label.get("contraindications"))
            if contraindications:
                lines.append(f"    Contraindications: {contraindications}")
            lines.append(f"    Source: {label.get('source', 'openFDA Drug Label API')}")
        drug_classes = citation.get("drug_classes") or []
        if drug_classes:
            class_names = ", ".join(c["class_name"] for c in drug_classes)
            lines.append(f"    Drug class: {class_names} (source: RxClass API)")
    return lines


def _judgment_lines(judgment: JudgeResult | None) -> list[str]:
    """
    M6's LLM-as-judge (decisions.md H11) is advisory-only and never shown
    as if it were part of the decision -- it never changed it. Only
    surfaced when it actually flagged something; a clean judgment adds no
    visible noise to every single response.
    """
    if judgment is None or not judgment.available:
        return []
    if judgment.groundedness_ok and judgment.tone_ok and not judgment.phi_leak_detected:
        return []

    concerns = []
    if not judgment.groundedness_ok:
        concerns.append("groundedness")
    if not judgment.tone_ok:
        concerns.append("tone")
    if judgment.phi_leak_detected:
        concerns.append("possible PHI in rationale")

    lines = ["", f"ℹ️  Quality review flagged: {', '.join(concerns)}"]
    if judgment.notes:
        lines.append(f"    {judgment.notes}")
    lines.append("    (Advisory only -- did not change the decision above.)")
    return lines


def decision_block(
    decision: str,
    patient_id: str,
    risk_assessment_id: str | None,
    rationale: str,
    override_reason: str | None = None,
    trace_id: str | None = None,
    citations: list[dict] | None = None,
    judgment: JudgeResult | None = None,
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

    citations/judgment are M6 additions (decisions.md H11, H15), both
    optional and both strictly supplementary -- neither one is capable of
    changing `decision` itself, which was already finalized before either
    was computed.
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

    lines += _citations_lines(citations or [])
    lines += _judgment_lines(judgment)

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
