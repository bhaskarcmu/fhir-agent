"""Every reply the clinician sees, built from the service's tool output and nothing else (FR-A2,
FR-A3, O69).

Numbers, reasons, warnings and the planning-aid note are copied from the RiskAssessment; the
only wording added here is fixed text with no numbers in it. `grounded()` checks a reply against
the tool output it was built from — the agent refuses to show a reply that fails it.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum


class Outcome(str, Enum):
    """The only things one agent turn can end as (the agent-platform output-gate pattern)."""
    ESTIMATE = "ESTIMATE"                    # one patient's estimate, narrated
    MODEL_CARD = "MODEL_CARD"                # how the model was built
    CHOOSE_PATIENT = "CHOOSE_PATIENT"        # several patients match: the human chooses
    NOT_FOUND = "NOT_FOUND"
    NO_ESTIMATE = "NO_ESTIMATE"              # the service declined (e.g. not an adult alive on the date)
    NEEDS_PATIENT = "NEEDS_PATIENT"          # no patient identified
    OUT_OF_SCOPE = "OUT_OF_SCOPE"            # populations, rankings, thresholds
    UNAVAILABLE = "UNAVAILABLE"              # the model or the service couldn't be reached


@dataclass
class Reply:
    outcome: Outcome
    text: str
    evidence: list[dict] = field(default_factory=list)   # the tool outputs the text was built from


EXT = "http://fhir-agent.local/StructureDefinition/"

NOTICE_BAND = ("The service gives a probability and a percentile only. It does not classify patients "
               "into risk bands, because no thresholds have been clinically agreed.")
NOTICE_ADJUST = ("This estimate can't be adjusted or re-scored with different inputs here: it comes only "
                 "from the records in the FHIR server up to the date shown.")
NOTICE_POPULATION = ("This assistant gives the estimate for one patient at a time. It can't rank, filter or "
                     "list patients by risk.")
ASK_PATIENT = ("I can give the service's hospitalization risk estimate for one named patient, or describe how "
               "the model was built. Which patient do you mean?")
UNAVAILABLE_TEXT = "The risk service or the language model couldn't be reached, so no estimate is shown."

BAND_CUES = re.compile(r"\b(high|low|moderate|medium|elevated)[- ]risk\b|\bis (that|this|it|she|he) (high|bad|low|"
                       r"concerning|worrying)\b|\b(risk )?(band|category|tier|level)\b|\b(over|above|under|below) "
                       r"\d+ ?%|\btop \d+|\bthreshold|cut-?off", re.I)
ADJUST_CUES = re.compile(r"\b(adjust|re-?score|recalculate|recompute|what if|assume|assuming|if (she|he|they) "
                         r"(had|has|were|was)|account for|factor in|update the score|change the)\b", re.I)
# Questions about the model itself ("how was it built?") — the only ones the model card answers.
MODEL_CUES = re.compile(r"\b(model|built|trained|training|validat\w*|accura\w*|auroc|how (does|do|is|was) (it|this|"
                        r"the score)|where (does|do) .* come from|data (source|set))\b", re.I)
# Questions about more than one patient: refused before any tool is called.
POPULATION_CUES = re.compile(r"\b(everyone|everybody|all (the |my |our )?(patients|members|people)|rank|ranking|"
                             r"list (all|the|patients|everyone)|which patients|who (is|are) (over|above|at)|"
                             r"panel|population|cohort)\b", re.I)


def _ext(extensions: list[dict], name: str) -> list:
    return [next(v for k, v in e.items() if k.startswith("value")) for e in extensions if e["url"] == EXT + name]


def _pct(decimal: float) -> str:
    """The service's 4-decimal probability as a percentage: 0.1227 -> '12.27%'. Exact, not rounded."""
    return f"{decimal * 100:.2f}%"


def narrate_estimate(ra: dict, question: str, patient: dict | None = None) -> str:
    p = ra["prediction"][0]
    when = p["whenPeriod"]
    percentile = _ext(p["extension"], "risk-percentile")[0]
    comparison = _ext(p["extension"], "comparison-probability")[0]
    model_id = ra["method"]["coding"][0]["code"]
    contract = _ext(p["extension"], "contract-version")[0]
    ref = ra["subject"].get("reference", "This patient")
    born = f"born {patient['birth_date']}, " if patient and patient.get("birth_date") else ""
    who = f"{patient['name']} ({born}{ref})" if patient else ref
    lines = [
        f"{who}: estimated chance of a hospital admission between {when['start']} and {when['end']} — "
        f"{_pct(p['probabilityDecimal'])}.",
        f"Percentile among the adults the model was trained on: {percentile}.",
        f"A simpler comparison model (age and any prior hospital stay) gives {_pct(comparison)}.",
        p["rationale"],
    ]
    warnings = _ext(ra.get("extension", []), "input-warning")
    if warnings:
        lines.append("Notes from the service about the inputs: " + "; ".join(warnings) + ".")
    for cues, notice in ((ADJUST_CUES, NOTICE_ADJUST), (BAND_CUES, NOTICE_BAND), (POPULATION_CUES, NOTICE_POPULATION)):
        if cues.search(question):
            lines.append(notice)
    lines.append(f"Model {model_id} (contract {contract}). {ra['note'][0]['text']}")
    return "\n".join(lines)


def narrate_model_card(card: dict) -> str:
    v = card["validation_metrics"]
    gbm, comp = v.get("gbm", {}), v.get("comparison", {})
    return "\n".join([
        f"Model {card['model_id']} (contract {card['contract_version']}): {card['outcome']}.",
        f"Inputs: {', '.join(card['features'])}.",
        f"Training panels: {', '.join(map(str, card['training'].get('panels', [])))}.",
        f"Validation AUROC: {gbm.get('auroc')} (comparison model: {comp.get('auroc')}). {card['metrics_note']}",
        f"Explanations: {card['explanations']}.",
    ])


def narrate_candidates(result: dict) -> str:
    rows = [f"- {c['name']} (born {c['birth_date'] or 'unknown'}, id {c['id']})" for c in result["candidates"]]
    more = " Only the first matches are shown; a fuller name narrows the search." if result.get("truncated") else ""
    return "Several patients match that name. Which one do you mean?" + more + "\n" + "\n".join(rows)


# ── grounding (FR-A2) ────────────────────────────────────────────────────────────────

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _numbers(text: str) -> set[str]:
    return set(_NUMBER.findall(text))


def allowed_numbers(evidence: list[dict]) -> set[str]:
    """Every number the reply may state: those in the tool output, and the exact percentage form of
    each probability. Identifiers (model id, references, ids) contribute their digits as written."""
    dumped = json.dumps(evidence)
    allowed = _numbers(dumped)
    for match in re.finditer(r'"(probabilityDecimal|valueDecimal)": (\d+(?:\.\d+)?)', dumped):
        allowed |= _numbers(_pct(float(match.group(2))))
    return allowed


def grounded(text: str, evidence: list[dict]) -> list[str]:
    """Numbers in `text` that the tool output doesn't contain — empty when the reply is grounded."""
    return sorted(_numbers(text) - allowed_numbers(evidence))
