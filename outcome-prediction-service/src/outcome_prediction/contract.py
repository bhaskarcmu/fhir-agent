"""The portable feature contract `meps-portable-v2` (docs/phase8/decisions.md O52–O54).

One definition of which model inputs a customer's FHIR / claims data can actually supply, how
reliably, and from where. Production models are trained on this contract — never on MEPS-only
features — so a model never depends on an input production can't fill.

Reliability tiers:
  always        demographics present on essentially every Patient resource
  usually       present in records, but undercounted when care happens outside the health system
  rarely        usually missing in records (e.g. income) -> optional input; models are trained with
                missingness augmentation so they predict well without it (O53)
  claims_only   reliable only from claims / dispensing data, not from records alone
  not_portable  means something different outside MEPS -> never a production input (O25)

Rule (O53): a feature that will ALWAYS be missing in production is dropped and the model retrained;
it is never imputed — an imputed value is a function of the other inputs and only adds silent
miscalibration. A feature that is SOMETIMES missing stays, with missingness augmentation.
"""
from __future__ import annotations

from dataclasses import dataclass

CONTRACT_VERSION = "meps-portable-v2"


@dataclass(frozen=True)
class Feature:
    name: str
    tier: str
    fhir_source: str
    meps_source: str
    note: str = ""


FEATURES: tuple[Feature, ...] = (
    # demographics and coverage
    Feature("agey1x", "always", "Patient.birthDate (age at the as-of date, top-coded 85)", "AGEY1X"),
    Feature("sex", "always", "Patient.gender", "SEX"),
    Feature("racethx", "usually", "US Core race + ethnicity extensions", "RACETHX",
            "used by the model, never narrated per patient (O50)"),
    Feature("regiony1", "usually", "Patient.address.state -> census region", "REGIONY1"),
    Feature("inscovy1", "usually", "Coverage, or ExplanationOfBenefit.insurance", "INSCOVY1"),
    Feature("mcrevy1", "usually", "Coverage.type = Medicare", "MCREVY1"),
    Feature("mcdevy1", "usually", "Coverage.type = Medicaid", "MCDEVY1"),
    Feature("povcaty1", "rarely", "household income and size are almost never recorded", "POVCATY1",
            "optional: missingness augmentation in training; a 'worth recording' prompt in narratives"),
    # use of care in the 12 months before the as-of date
    Feature("ipdisy1", "usually", "Encounter.class IMP (count)", "IPDISY1", "misses stays at other hospitals"),
    Feature("ipngtdy1", "usually", "Encounter.period of IMP encounters (nights)", "IPNGTDY1"),
    Feature("ertoty1", "usually", "Encounter.class EMER (count)", "ERTOTY1", "misses ER visits elsewhere"),
    Feature("obtotvy1", "usually", "Encounter.class AMB / VR, office setting (count)", "OBTOTVY1",
            "office vs hospital-outpatient split to be confirmed in M6"),
    Feature("optotvy1", "usually", "Encounter.class AMB, hospital outpatient setting (count)", "OPTOTVY1"),
    Feature("rxtoty1", "claims_only", "MedicationDispense or pharmacy claims (fills)", "RXTOTY1",
            "MedicationRequest = orders, not fills: not a substitute"),
    Feature("hhtotdy1", "claims_only", "home-health claims (days)", "HHTOTDY1"),
    Feature("totexpy1", "not_portable", "—", "TOTEXPY1",
            "MEPS = payments from all payers at all providers; records hold charges from one system"),
    # conditions (ever diagnosed, by the as-of date) and code-derived features
    *(Feature(f, "usually", "Condition (SNOMED -> ICD-10 via M13 code lists)", f.upper() + "Y1")
      for f in ("hibpdx", "chddx", "angidx", "midx", "ohrtdx", "strkdx", "emphdx", "diabdx",
                "arthdx", "asthdx", "choldx")),
    Feature("n_icd", "usually", "Condition codes -> distinct ICD-10 3-character categories", "conditions file"),
    Feature("n_icd_chapters", "usually", "Condition codes -> distinct ICD-10 chapters", "conditions file",
            "portable replacement for CCSR body systems (CCSR needs AHRQ's mapping file)"),
    Feature("n_distinct_drugs", "usually", "MedicationRequest -> distinct RxNorm ingredients", "RXDRGNAM",
            "portable replacement for Multum drug-class counts"),
    Feature("hfrs", "usually", "ICD-10 3-character codes -> Hospital Frailty Risk Score", "conditions file"),
    Feature("charlson_approx", "usually", "ICD-10 codes -> Charlson (Quan)", "conditions file"),
    Feature("elixhauser_vw_approx", "usually", "ICD-10 codes -> Elixhauser (Quan, van Walraven)", "conditions file"),
    Feature("elixhauser_count_approx", "usually", "ICD-10 codes -> Elixhauser count", "conditions file"),
)

# Text input: the patient's year-1 ICD-10 3-character codes only ("tokens_icd"). CCSR groups and
# Multum drug classes are left out of the portable contract until a licensed / free mapping exists.
TEXT_COLUMN = "tokens_icd"

# ICD-10-CM chapters by 3-character code range (CMS/NCHS tabular list).
_CHAPTERS = [("A00", "B99", 1), ("C00", "D49", 2), ("D50", "D89", 3), ("E00", "E89", 4), ("F01", "F99", 5),
             ("G00", "G99", 6), ("H00", "H59", 7), ("H60", "H95", 8), ("I00", "I99", 9), ("J00", "J99", 10),
             ("K00", "K95", 11), ("L00", "L99", 12), ("M00", "M99", 13), ("N00", "N99", 14),
             ("O00", "O9A", 15), ("P00", "P96", 16), ("Q00", "Q99", 17), ("R00", "R99", 18),
             ("S00", "T88", 19), ("U00", "U85", 22), ("V00", "Y99", 20), ("Z00", "Z99", 21)]


def icd10_chapter(code3: str) -> int | None:
    """Chapter number of a 3-character ICD-10-CM category, or None if outside every range."""
    c = code3.strip().upper()[:3]
    return next((ch for lo, hi, ch in _CHAPTERS if lo <= c <= hi), None)


CATEGORICAL = ("sex", "racethx", "regiony1", "inscovy1", "povcaty1")
OPTIONAL = tuple(f.name for f in FEATURES if f.tier == "rarely")


def names(tiers: tuple[str, ...]) -> list[str]:
    return [f.name for f in FEATURES if f.tier in tiers]


DEFAULT_TIERS = ("always", "usually", "rarely")           # records-only customers
WITH_CLAIMS_TIERS = DEFAULT_TIERS + ("claims_only",)        # customers who also send claims


# Can a customer observe the OUTCOME? Needed to validate and recalibrate (scorecard, O54).
LABEL_OBSERVABILITY = {
    "admit_nonobstetric_y2": "records (within the health system) or claims (all hospitals)",
    "admit_via_er_y2": "records (within the health system) or claims (all hospitals)",
    "label_hosp_12m": "records (within the health system) or claims (all hospitals)",
    "any_ed_y2": "records (within the health system) or claims (all ERs)",
    "ed_visits_y2": "records (within the health system) or claims (all ERs)",
    "high_cost_y2": "claims only — a records-only customer can never validate or recalibrate it",
    "cost_y2": "claims only — a records-only customer can never validate or recalibrate it",
}
