"""explain.py: replies built from the service's output, and the grounding check (FR-A2, FR-A3)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from outcome_prediction_agent import explain

OUTPUTS = json.loads((Path(__file__).parent / "fixtures" / "service_outputs.json").read_text())

RA = OUTPUTS["estimate"]["risk_assessment"]
EVIDENCE = [{"tool": "get_hospitalization_risk", "result": OUTPUTS["estimate"]}]


def test_estimate_states_every_service_fact_and_the_planning_aid_note():
    text = explain.narrate_estimate(RA, "What is the risk?")
    p = RA["prediction"][0]
    for fact in (explain._pct(p["probabilityDecimal"]), p["rationale"], p["whenPeriod"]["start"],
                 p["whenPeriod"]["end"], RA["method"]["coding"][0]["code"], RA["note"][0]["text"]):
        assert fact in text
    for name in ("risk-percentile", "comparison-probability"):
        value = explain._ext(p["extension"], name)[0]
        assert (explain._pct(value) if isinstance(value, float) else str(value)) in text
    assert explain.grounded(text, EVIDENCE) == []


def test_percentages_are_the_services_decimals_exactly():
    assert explain._pct(0.1227) == "12.27%" and explain._pct(0.0317) == "3.17%"


def test_grounding_catches_a_number_the_service_didnt_return():
    assert explain.grounded("The risk is 42.5%, roughly double average.", EVIDENCE) == ["42.5"]
    assert explain.grounded("", EVIDENCE) == []


def test_grounding_catches_a_band_threshold_or_a_rescaled_number():
    assert explain.grounded("Above the 20% threshold.", EVIDENCE) == ["20"]
    assert explain.grounded("About 99%.", EVIDENCE) == ["99"]


def test_warnings_from_the_service_are_passed_on():
    text = explain.narrate_estimate(RA, "")
    for w in explain._ext(RA["extension"], "input-warning"):
        assert w in text


def test_notices_follow_the_question_and_carry_no_numbers():
    for notice in (explain.NOTICE_BAND, explain.NOTICE_ADJUST, explain.NOTICE_POPULATION, explain.ASK_PATIENT):
        assert explain._numbers(notice) == set()
    assert explain.NOTICE_ADJUST in explain.narrate_estimate(RA, "Adjust for her new diagnosis")
    assert explain.NOTICE_BAND in explain.narrate_estimate(RA, "Is she high risk?")
    assert explain.NOTICE_BAND not in explain.narrate_estimate(RA, "What is her risk?")


def test_no_reasons_and_no_warnings_still_narrate():
    ra = copy.deepcopy(RA)
    ra["extension"] = []
    text = explain.narrate_estimate(ra, "")
    assert "Notes from the service" not in text and RA["note"][0]["text"] in text


def test_candidates_list_ids_and_never_choose():
    text = explain.narrate_candidates(OUTPUTS["two_matches"])
    assert "Which one do you mean?" in text and text.count("- ") == 2


def test_model_card_states_validation_metrics_as_given():
    card = OUTPUTS["model_card"]["model_card"]
    text = explain.narrate_model_card(card)
    assert str(card["validation_metrics"]["gbm"]["auroc"]) in text and card["metrics_note"] in text
    assert explain.grounded(text, [{"result": OUTPUTS["model_card"]}]) == []
