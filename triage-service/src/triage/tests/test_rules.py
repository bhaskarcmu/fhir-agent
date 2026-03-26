"""
Unit tests for the triage rule engine.

No running server required. Tests use in-memory Medication and Allergy
objects constructed to match real Synthea output shapes.

Run:
  python3 -m pytest triage-service/src/triage/tests/test_rules.py -v
"""

from datetime import date

import pytest

from fhir_clinical_client import Allergy, Medication
from triage.rules import (
    RuleResult,
    _rule_duplicate_therapeutic_class,
    _rule_high_criticality_allergy,
    _rule_penicillin_conflict,
    evaluate,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def med(
    id="med-1",
    code="723",
    display="Amoxicillin 250 MG Oral Capsule",
    status="active",
) -> Medication:
    return Medication(id=id, code=code, display=display, status=status)


def allergy(
    id="alg-1",
    code="91936005",
    display="Allergy to penicillin",
    criticality="high",
    category=None,
) -> Allergy:
    return Allergy(
        id=id,
        code=code,
        display=display,
        criticality=criticality,
        category=category or ["medication"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Rule 1 — Penicillin conflict
# ─────────────────────────────────────────────────────────────────────────────

class TestPenicillinConflict:

    def test_amoxicillin_plus_penicillin_allergy_is_high(self):
        result = _rule_penicillin_conflict(
            [med(code="723", display="Amoxicillin 250 MG Oral Capsule")],
            [allergy(code="91936005", display="Allergy to penicillin", criticality="high")],
        )
        assert result is not None
        assert result.risk_level == "HIGH"
        assert result.rule_id == "penicillin-conflict"

    def test_display_match_triggers_conflict(self):
        """Match by display text when RxNorm code is not in the known set."""
        result = _rule_penicillin_conflict(
            [med(code="99999", display="Penicillin V Potassium 500 MG Oral Tablet")],
            [allergy(code="91936005", display="Allergy to penicillin")],
        )
        assert result is not None
        assert result.risk_level == "HIGH"

    def test_allergy_display_match_triggers_conflict(self):
        result = _rule_penicillin_conflict(
            [med(code="723", display="Amoxicillin 250 MG Oral Capsule")],
            [allergy(code="99999", display="Penicillin allergy (finding)")],
        )
        assert result is not None
        assert result.risk_level == "HIGH"

    def test_no_penicillin_medication_returns_none(self):
        result = _rule_penicillin_conflict(
            [med(code="1049502", display="Atorvastatin 40 MG Oral Tablet")],
            [allergy(code="91936005", display="Allergy to penicillin")],
        )
        assert result is None

    def test_no_penicillin_allergy_returns_none(self):
        result = _rule_penicillin_conflict(
            [med(code="723", display="Amoxicillin 250 MG Oral Capsule")],
            [allergy(code="419199007", display="Allergy to latex", criticality="low",
                     category=["environment"])],
        )
        assert result is None

    def test_empty_medications_returns_none(self):
        result = _rule_penicillin_conflict(
            [],
            [allergy(code="91936005", display="Allergy to penicillin")],
        )
        assert result is None

    def test_empty_allergies_returns_none(self):
        result = _rule_penicillin_conflict(
            [med(code="723", display="Amoxicillin 250 MG Oral Capsule")],
            [],
        )
        assert result is None

    def test_basis_ids_populated(self):
        m = med(id="med-amox", code="723", display="Amoxicillin 250 MG Oral Capsule")
        a = allergy(id="alg-pen", code="91936005", display="Allergy to penicillin")
        result = _rule_penicillin_conflict([m], [a])
        assert "med-amox" in result.basis_medication_ids
        assert "alg-pen" in result.basis_allergy_ids

    def test_note_contains_conflict_language(self):
        result = _rule_penicillin_conflict(
            [med(code="723", display="Amoxicillin 250 MG Oral Capsule")],
            [allergy(code="91936005", display="Allergy to penicillin")],
        )
        assert "CONFLICT" in result.note
        assert "penicillin" in result.note.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Rule 2 — Duplicate therapeutic class
# ─────────────────────────────────────────────────────────────────────────────

class TestDuplicateTherapeuticClass:

    def test_two_antihistamines_is_moderate(self):
        result = _rule_duplicate_therapeutic_class(
            [
                med(id="m1", code="997488", display="Fexofenadine hydrochloride 30 MG Oral Tablet"),
                med(id="m2", code="311372", display="Loratadine 10 MG Oral Tablet"),
            ],
            [],
        )
        assert result is not None
        assert result.risk_level == "MODERATE"
        assert result.rule_id == "duplicate-therapeutic-class"

    def test_two_statins_is_moderate(self):
        result = _rule_duplicate_therapeutic_class(
            [
                med(id="m1", code="1049502", display="Atorvastatin 40 MG Oral Tablet"),
                med(id="m2", code="36567", display="Simvastatin 20 MG Oral Tablet"),
            ],
            [],
        )
        assert result is not None
        assert result.risk_level == "MODERATE"

    def test_different_classes_returns_none(self):
        result = _rule_duplicate_therapeutic_class(
            [
                med(id="m1", code="997488", display="Fexofenadine hydrochloride 30 MG"),
                med(id="m2", code="1049502", display="Atorvastatin 40 MG Oral Tablet"),
            ],
            [],
        )
        assert result is None

    def test_single_medication_returns_none(self):
        result = _rule_duplicate_therapeutic_class(
            [med(code="997488", display="Fexofenadine hydrochloride 30 MG")],
            [],
        )
        assert result is None

    def test_empty_medications_returns_none(self):
        result = _rule_duplicate_therapeutic_class([], [])
        assert result is None

    def test_basis_ids_contain_duplicate_meds(self):
        result = _rule_duplicate_therapeutic_class(
            [
                med(id="m1", code="997488", display="Fexofenadine hydrochloride 30 MG"),
                med(id="m2", code="311372", display="Loratadine 10 MG Oral Tablet"),
            ],
            [],
        )
        assert "m1" in result.basis_medication_ids
        assert "m2" in result.basis_medication_ids


# ─────────────────────────────────────────────────────────────────────────────
# Rule 3 — High-criticality allergy
# ─────────────────────────────────────────────────────────────────────────────

class TestHighCriticalityAllergy:

    def test_high_criticality_allergy_with_meds_is_moderate(self):
        result = _rule_high_criticality_allergy(
            [med(code="1049502", display="Atorvastatin 40 MG Oral Tablet")],
            [allergy(code="419199007", display="Latex allergy", criticality="high",
                     category=["environment"])],
        )
        assert result is not None
        assert result.risk_level == "MODERATE"
        assert result.rule_id == "high-criticality-allergy"

    def test_low_criticality_allergy_returns_none(self):
        result = _rule_high_criticality_allergy(
            [med(code="1049502", display="Atorvastatin 40 MG Oral Tablet")],
            [allergy(code="419199007", display="Latex allergy", criticality="low")],
        )
        assert result is None

    def test_no_medications_returns_none(self):
        result = _rule_high_criticality_allergy(
            [],
            [allergy(criticality="high")],
        )
        assert result is None

    def test_no_allergies_returns_none(self):
        result = _rule_high_criticality_allergy(
            [med(code="1049502", display="Atorvastatin 40 MG Oral Tablet")],
            [],
        )
        assert result is None

    def test_basis_allergy_ids_populated(self):
        result = _rule_high_criticality_allergy(
            [med()],
            [allergy(id="alg-high", criticality="high")],
        )
        assert "alg-high" in result.basis_allergy_ids


# ─────────────────────────────────────────────────────────────────────────────
# evaluate() — engine entry point
# ─────────────────────────────────────────────────────────────────────────────

class TestEvaluate:

    def test_penicillin_conflict_takes_priority_over_duplicate_class(self):
        """HIGH rule fires before MODERATE rules."""
        result = evaluate(
            [
                med(id="m1", code="723", display="Amoxicillin 250 MG Oral Capsule"),
                med(id="m2", code="311372", display="Loratadine 10 MG Oral Tablet"),
                med(id="m3", code="997488", display="Fexofenadine hydrochloride 30 MG"),
            ],
            [allergy(code="91936005", display="Allergy to penicillin", criticality="high")],
        )
        assert result.risk_level == "HIGH"
        assert result.rule_id == "penicillin-conflict"

    def test_no_conflicts_returns_low(self):
        result = evaluate(
            [med(code="1049502", display="Atorvastatin 40 MG Oral Tablet")],
            [allergy(code="419199007", display="Latex allergy", criticality="low",
                     category=["environment"])],
        )
        assert result.risk_level == "LOW"
        assert result.rule_id == "no-conflict"

    def test_empty_patient_returns_low(self):
        result = evaluate([], [])
        assert result.risk_level == "LOW"

    def test_duplicate_class_fires_when_no_penicillin(self):
        result = evaluate(
            [
                med(id="m1", code="997488", display="Fexofenadine hydrochloride 30 MG"),
                med(id="m2", code="311372", display="Loratadine 10 MG Oral Tablet"),
            ],
            [],
        )
        assert result.risk_level == "MODERATE"
        assert result.rule_id == "duplicate-therapeutic-class"

    def test_high_criticality_fires_when_no_penicillin_no_duplicate(self):
        result = evaluate(
            [med(code="1049502", display="Atorvastatin 40 MG Oral Tablet")],
            [allergy(criticality="high", display="Latex allergy",
                     code="419199007", category=["environment"])],
        )
        assert result.risk_level == "MODERATE"
        assert result.rule_id == "high-criticality-allergy"
