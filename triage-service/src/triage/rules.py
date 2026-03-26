"""
Triage rule engine.

Rules are plain Python dataclasses evaluated in priority order.
First match wins. Adding a new rule is adding one item to RULES.

Each rule receives the patient's full medication and allergy lists and
returns a RuleResult describing the risk level, clinical rationale, and
the specific resource IDs that triggered the rule.

Walking skeleton ships with three rules:
  1. Penicillin family conflict  → HIGH
  2. Duplicate therapeutic class → MODERATE
  3. High-criticality allergy    → MODERATE
  Default                        → LOW
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Callable, Literal

from fhir_clinical_client import Allergy, Medication


# ─────────────────────────────────────────────────────────────────────────────
# Rule result
# ─────────────────────────────────────────────────────────────────────────────

RiskLevel = Literal["HIGH", "MODERATE", "LOW"]


@dataclass
class RuleResult:
    risk_level: RiskLevel
    rule_id: str
    note: str
    basis_medication_ids: list[str] = field(default_factory=list)
    basis_allergy_ids: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Rule definition
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Rule:
    id: str
    name: str
    evaluate: Callable[[list[Medication], list[Allergy]], RuleResult | None]


# ─────────────────────────────────────────────────────────────────────────────
# Clinical knowledge sets
# ─────────────────────────────────────────────────────────────────────────────

# RxNorm codes for penicillin-family antibiotics.
# Amoxicillin, ampicillin, penicillin V/G, piperacillin, oxacillin, dicloxacillin.
PENICILLIN_RXNORM_CODES = {
    "723",      # amoxicillin
    "733",      # ampicillin
    "7980",     # penicillin V
    "7981",     # penicillin G
    "8331",     # piperacillin
    "7454",     # oxacillin
    "3423",     # dicloxacillin
    "18631",    # amoxicillin/clavulanate (Augmentin)
    "10829",    # piperacillin/tazobactam
}

# Display-name fragments that indicate a penicillin-family drug.
PENICILLIN_DISPLAY_FRAGMENTS = {
    "amoxicillin", "ampicillin", "penicillin", "piperacillin",
    "oxacillin", "dicloxacillin", "augmentin", "tazobactam",
}

# SNOMED CT codes for penicillin allergy.
PENICILLIN_ALLERGY_SNOMED_CODES = {
    "372687004",  # Amoxicillin
    "372687004",  # Amoxicillin (duplicate intentional — different SNOMED versions)
    "764146007",  # Penicillin
    "6369005",    # Penicillin G
    "372687004",  # Amoxicillin
    "96067000",   # Penicillin allergy
    "91936005",   # Allergy to penicillin
    "294505008",  # Allergy to amoxicillin
}

# Coarse therapeutic class groupings by RxNorm code prefix / display fragment.
# Used for duplicate-class detection.
THERAPEUTIC_CLASSES: dict[str, set[str]] = {
    "antihistamine": {
        "fexofenadine", "loratadine", "cetirizine", "diphenhydramine",
        "desloratadine", "levocetirizine", "hydroxyzine",
    },
    "statin": {
        "atorvastatin", "simvastatin", "rosuvastatin", "pravastatin",
        "lovastatin", "fluvastatin", "pitavastatin",
    },
    "ace_inhibitor": {
        "lisinopril", "enalapril", "ramipril", "captopril",
        "benazepril", "fosinopril", "quinapril",
    },
    "arb": {
        "losartan", "valsartan", "irbesartan", "candesartan",
        "olmesartan", "telmisartan", "azilsartan",
    },
    "ssri": {
        "sertraline", "fluoxetine", "escitalopram", "citalopram",
        "paroxetine", "fluvoxamine",
    },
    "ppi": {
        "omeprazole", "pantoprazole", "esomeprazole", "lansoprazole",
        "rabeprazole", "dexlansoprazole",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────────────────

def _is_penicillin_medication(med: Medication) -> bool:
    if med.code in PENICILLIN_RXNORM_CODES:
        return True
    display_lower = med.display.lower()
    return any(frag in display_lower for frag in PENICILLIN_DISPLAY_FRAGMENTS)


def _is_penicillin_allergy(allergy: Allergy) -> bool:
    if allergy.code in PENICILLIN_ALLERGY_SNOMED_CODES:
        return True
    display_lower = allergy.display.lower()
    return "penicillin" in display_lower or "amoxicillin" in display_lower


def _therapeutic_class(med: Medication) -> str | None:
    display_lower = med.display.lower()
    for cls, fragments in THERAPEUTIC_CLASSES.items():
        if any(frag in display_lower for frag in fragments):
            return cls
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Rule implementations
# ─────────────────────────────────────────────────────────────────────────────

def _rule_penicillin_conflict(
    medications: list[Medication],
    allergies: list[Allergy],
) -> RuleResult | None:
    """
    HIGH risk: patient has an active penicillin-family prescription AND
    a recorded penicillin allergy.

    Cross-reactivity between penicillins and amoxicillin is ~10% and
    can cause anaphylaxis. This is the canonical drug-allergy conflict
    the triage service is designed to catch.
    """
    pen_meds = [m for m in medications if _is_penicillin_medication(m)]
    pen_allergies = [a for a in allergies if _is_penicillin_allergy(a)]

    if not pen_meds or not pen_allergies:
        return None

    med_names = ", ".join(m.display.split()[0] for m in pen_meds)
    allergy_names = ", ".join(a.display for a in pen_allergies)

    return RuleResult(
        risk_level="HIGH",
        rule_id="penicillin-conflict",
        note=(
            f"CONFLICT DETECTED: {med_names} belongs to the penicillin antibiotic family. "
            f"Patient has a recorded allergy to: {allergy_names}. "
            "Cross-reactivity risk: ~10% between penicillins and amoxicillin. "
            "Do not dispense without physician review. "
            "Consider alternatives: Azithromycin or Doxycycline (confirm no contraindications)."
        ),
        basis_medication_ids=[m.id for m in pen_meds],
        basis_allergy_ids=[a.id for a in pen_allergies],
    )


def _rule_duplicate_therapeutic_class(
    medications: list[Medication],
    allergies: list[Allergy],
) -> RuleResult | None:
    """
    MODERATE risk: patient has two or more active medications in the same
    therapeutic class (e.g. two antihistamines, two statins).

    Concurrent use within a class is rarely intentional and warrants
    pharmacist review before refill approval.
    """
    class_to_meds: dict[str, list[Medication]] = {}
    for med in medications:
        cls = _therapeutic_class(med)
        if cls:
            class_to_meds.setdefault(cls, []).append(med)

    duplicates = {cls: meds for cls, meds in class_to_meds.items() if len(meds) > 1}
    if not duplicates:
        return None

    details = "; ".join(
        f"{cls.replace('_', ' ').title()}: "
        + ", ".join(m.display.split()[0] for m in meds)
        for cls, meds in duplicates.items()
    )
    all_med_ids = [m.id for meds in duplicates.values() for m in meds]

    return RuleResult(
        risk_level="MODERATE",
        rule_id="duplicate-therapeutic-class",
        note=(
            f"Concurrent medications in the same therapeutic class detected: {details}. "
            "Duplicate use within a class is rarely intentional. "
            "Pharmacist review recommended before refill approval."
        ),
        basis_medication_ids=all_med_ids,
        basis_allergy_ids=[],
    )


def _rule_high_criticality_allergy(
    medications: list[Medication],
    allergies: list[Allergy],
) -> RuleResult | None:
    """
    MODERATE risk: patient has any high-criticality allergy and at least
    one active medication.

    A high-criticality allergy on record warrants a general review even
    when no specific drug-allergy conflict is detected by other rules.
    """
    if not medications:
        return None

    high_allergies = [a for a in allergies if a.criticality == "high"]
    if not high_allergies:
        return None

    allergy_names = ", ".join(a.display for a in high_allergies)
    return RuleResult(
        risk_level="MODERATE",
        rule_id="high-criticality-allergy",
        note=(
            f"Patient has {len(high_allergies)} high-criticality allergy record(s): "
            f"{allergy_names}. "
            "No direct drug conflict detected, but high-criticality allergies on record "
            "warrant pharmacist review before dispensing."
        ),
        basis_medication_ids=[m.id for m in medications[:3]],  # first 3 as context
        basis_allergy_ids=[a.id for a in high_allergies],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Rule registry — evaluated in order, first match wins
# ─────────────────────────────────────────────────────────────────────────────

RULES: list[Rule] = [
    Rule(
        id="penicillin-conflict",
        name="Penicillin family drug-allergy conflict",
        evaluate=_rule_penicillin_conflict,
    ),
    Rule(
        id="duplicate-therapeutic-class",
        name="Duplicate therapeutic class",
        evaluate=_rule_duplicate_therapeutic_class,
    ),
    Rule(
        id="high-criticality-allergy",
        name="High-criticality allergy on record",
        evaluate=_rule_high_criticality_allergy,
    ),
]

_DEFAULT_LOW = RuleResult(
    risk_level="LOW",
    rule_id="no-conflict",
    note=(
        "No drug-allergy conflicts detected. "
        "No duplicate therapeutic classes. "
        "No high-criticality allergies on record. "
        "Safe to dispense."
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Engine entry point
# ─────────────────────────────────────────────────────────────────────────────

def evaluate(
    medications: list[Medication],
    allergies: list[Allergy],
) -> RuleResult:
    """
    Evaluate all rules against the patient's medications and allergies.
    Returns the first matching result, or LOW risk if no rule fires.
    """
    for rule in RULES:
        result = rule.evaluate(medications, allergies)
        if result is not None:
            return result
    return _DEFAULT_LOW
