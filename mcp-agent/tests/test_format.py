"""
Tests for format.py's M6 additions to decision_block (docs/phase6/
decisions.md H11, H15): citations and judge notes are strictly
supplementary display -- neither can appear as if it changed `decision`.

Run:
  python3 -m pytest mcp-agent/tests/test_format.py -v
"""

from __future__ import annotations

from agent.format import decision_block
from agent_platform import JudgeResult


def test_decision_block_with_no_citations_or_judgment_is_unchanged_from_pre_m6():
    text = decision_block(
        decision="DISPENSE", patient_id="p1", risk_assessment_id="r1", rationale="Looks fine.",
    )
    assert "Citations:" not in text
    assert "Quality review" not in text


def test_citations_render_boxed_warning_and_contraindications():
    citations = [{
        "drug": "Amoxicillin 500 MG Oral Capsule",
        "label": {
            "boxed_warning": "Serious risk of X.",
            "contraindications": "Do not use with Y.",
            "source": "openFDA Drug Label API",
        },
        "drug_classes": [{"class_name": "PENICILLINS", "class_type": "VA"}],
    }]

    text = decision_block(
        decision="DO_NOT_DISPENSE", patient_id="p1", risk_assessment_id="r1",
        rationale="Penicillin allergy conflict.", citations=citations,
    )

    assert "Citations:" in text
    assert "Amoxicillin 500 MG Oral Capsule" in text
    assert "Serious risk of X." in text
    assert "Do not use with Y." in text
    assert "PENICILLINS" in text
    assert "openFDA Drug Label API" in text


def test_long_citation_text_is_truncated():
    long_text = "A" * 500
    citations = [{"drug": "X", "label": {"boxed_warning": long_text, "contraindications": None, "source": "openFDA"}, "drug_classes": []}]

    text = decision_block(
        decision="REVIEW", patient_id="p1", risk_assessment_id=None,
        rationale="r", citations=citations,
    )

    assert "A" * 500 not in text  # not the full text
    assert "..." in text


def test_empty_citations_list_renders_nothing():
    text = decision_block(
        decision="DISPENSE", patient_id="p1", risk_assessment_id="r1", rationale="r", citations=[],
    )
    assert "Citations:" not in text


def test_clean_judgment_renders_nothing():
    judgment = JudgeResult(available=True, groundedness_ok=True, tone_ok=True, phi_leak_detected=False, notes="")
    text = decision_block(
        decision="DISPENSE", patient_id="p1", risk_assessment_id="r1", rationale="r", judgment=judgment,
    )
    assert "Quality review" not in text


def test_flagged_judgment_renders_a_visible_advisory_note():
    judgment = JudgeResult(
        available=True, groundedness_ok=False, tone_ok=True, phi_leak_detected=False,
        notes="Rationale doesn't mention the actual conflict found.",
    )
    text = decision_block(
        decision="DO_NOT_DISPENSE", patient_id="p1", risk_assessment_id="r1", rationale="r", judgment=judgment,
    )
    assert "Quality review flagged" in text
    assert "groundedness" in text
    assert "Advisory only" in text
    assert "did not change the decision" in text


def test_unavailable_judgment_renders_nothing():
    """The judge being inconclusive is not itself a quality problem worth surfacing."""
    judgment = JudgeResult(available=False)
    text = decision_block(
        decision="DISPENSE", patient_id="p1", risk_assessment_id="r1", rationale="r", judgment=judgment,
    )
    assert "Quality review" not in text


def test_flagged_judgment_never_changes_the_decision_label_itself():
    """The core invariant (H11): even a fully-flagged judgment leaves DECISION_LABELS untouched."""
    judgment = JudgeResult(
        available=True, groundedness_ok=False, tone_ok=False, phi_leak_detected=True, notes="bad",
    )
    text = decision_block(
        decision="DISPENSE", patient_id="p1", risk_assessment_id="r1", rationale="r", judgment=judgment,
    )
    assert "✅  DISPENSE" in text
    assert "DO NOT DISPENSE" not in text
    assert "REVIEW" not in text  # case-sensitive -- "Quality review" (lowercase) doesn't match
