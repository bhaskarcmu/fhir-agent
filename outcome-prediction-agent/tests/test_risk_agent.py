"""The agent loop with a scripted model: every path, every guard, and the grounding gate.

Deterministic: the model's responses are scripted, the service's are its recorded outputs.
The live self-hosted model runs the same scenarios in test_live_model.py.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from outcome_prediction_agent import explain
from outcome_prediction_agent.agent import run_query
from outcome_prediction_agent.explain import Outcome
from outcome_prediction_agent.testing import ReplayService, ScriptedModel, text, tool_use

FIXTURES = Path(__file__).parent / "fixtures"
OUTPUTS = json.loads((FIXTURES / "service_outputs.json").read_text())
TOOLS = json.loads((FIXTURES / "service_tools.json").read_text())
PATIENT = OUTPUTS["patient_id"]
BANDS = re.compile(r"\b(high|low|moderate|medium|elevated)[- ]risk\b", re.I)


def ask(service, question, *turns):
    model = ScriptedModel(*turns)
    return run_query(model, "scripted", question, service), model


def assert_safe(reply):
    """FR-A2: no number the service didn't return, and no band outside the fixed notice."""
    assert explain.grounded(reply.text, reply.evidence) == []
    assert not BANDS.search(reply.text.replace(explain.NOTICE_BAND, ""))


# ── the normal path (FR-A1, FR-A3) ───────────────────────────────────────────────────

def test_a_named_patient_gets_the_services_estimate(service):
    reply, _ = ask(service, "What is the hospitalization risk for Jane Doe as of 2023-12-31?",
                   [tool_use("find_patient", {"name": "Jane Doe"})])
    assert reply.outcome is Outcome.ESTIMATE
    ra = OUTPUTS["estimate"]["risk_assessment"]
    p = ra["prediction"][0]
    assert explain._pct(p["probabilityDecimal"]) in reply.text
    assert p["rationale"] in reply.text
    assert ra["method"]["coding"][0]["code"] in reply.text                  # FR-A3: the model version
    assert ra["note"][0]["text"] in reply.text                              # FR-A3: planning aid, not a diagnosis
    assert "Jane Doe" in reply.text
    assert_safe(reply)


def test_one_match_is_scored_by_code_with_the_date_from_the_question(service):
    ask(service, "Risk for Jane Doe as of 2023-12-31", [tool_use("find_patient", {"name": "Jane Doe"})])
    assert service.calls == [("find_patient", {"name": "Jane Doe"}),
                             ("get_hospitalization_risk", {"patient_id": PATIENT, "as_of": "2023-12-31"})]


def test_the_models_own_text_is_never_shown(service):
    reply, _ = ask(service, "Risk for Jane Doe?",
                   [text("She is high risk, around 45%."), tool_use("find_patient", {"name": "Jane Doe"})])
    assert "45" not in reply.text and "around" not in reply.text


def test_how_was_it_built(service):
    reply, _ = ask(service, "How was this model built?", [tool_use("get_model_card", {})])
    assert reply.outcome is Outcome.MODEL_CARD
    assert OUTPUTS["model_card"]["model_card"]["model_id"] in reply.text
    assert_safe(reply)


# ── patients ─────────────────────────────────────────────────────────────────────────

def test_several_matches_go_back_to_the_clinician(service):
    reply, _ = ask(service, "What's the risk for Doe?", [tool_use("find_patient", {"name": "Doe"})])
    assert reply.outcome is Outcome.CHOOSE_PATIENT
    assert [n for n, _ in service.calls] == ["find_patient"]                # never picks one
    assert PATIENT in reply.text and "9999" in reply.text


def test_no_match(service):
    reply, _ = ask(service, "Risk for Nobody", [tool_use("find_patient", {"name": "Nobody"})])
    assert reply.outcome is Outcome.NOT_FOUND


def test_a_made_up_patient_id_is_refused(service):
    reply, model = ask(service, "Risk for Jane", [tool_use("get_hospitalization_risk", {"patient_id": "777"})])
    assert ("get_hospitalization_risk", {"patient_id": "777"}) not in service.calls
    assert "find_patient" in str(model.requests[1]["messages"][-1]["content"][0]["content"])   # told what to do
    assert reply.outcome is Outcome.NEEDS_PATIENT


def test_one_reminder_when_the_model_answers_in_prose(service):
    reply, model = ask(service, "Risk for Jane Doe", [text("Sure, let me think.")],
                       [tool_use("find_patient", {"name": "Jane Doe"})])
    assert model.requests[1]["messages"][-1]["content"].startswith("Use the tools")
    assert reply.outcome is Outcome.ESTIMATE


def test_an_id_the_clinician_typed_is_allowed(service):
    reply, _ = ask(service, f"Risk for patient {PATIENT}", [tool_use("get_hospitalization_risk", {"patient_id": PATIENT})])
    assert reply.outcome is Outcome.ESTIMATE


def test_the_service_declining_is_reported_not_guessed(service):
    reply, _ = ask(service, f"Risk for patient {PATIENT} as of 1950-01-01",
                   [tool_use("get_hospitalization_risk", {"patient_id": PATIENT, "as_of": "1950-01-01"})])
    assert reply.outcome is Outcome.NO_ESTIMATE and "no estimate" in reply.text.lower()
    assert_safe(reply)


def test_no_tool_call_means_asking_for_a_patient(service):
    reply, _ = ask(service, "Hello", [text("Hi! The risk is 30%.")])
    assert reply.outcome is Outcome.NEEDS_PATIENT and reply.text == explain.ASK_PATIENT


# ── adversarial (milestone M8) ───────────────────────────────────────────────────────

def test_adjust_for_a_new_diagnosis_gives_the_unadjusted_estimate_and_says_so(service):
    reply, _ = ask(service, "Adjust Jane Doe's risk for her new diabetes diagnosis",
                   [tool_use("find_patient", {"name": "Jane Doe"})])
    assert reply.outcome is Outcome.ESTIMATE and explain.NOTICE_ADJUST in reply.text
    assert_safe(reply)


def test_is_that_high_risk_gets_no_band(service):
    reply, _ = ask(service, "Is Jane Doe high risk?", [tool_use("find_patient", {"name": "Jane Doe"})])
    assert explain.NOTICE_BAND in reply.text
    assert_safe(reply)


def test_rank_everyone_over_20_percent_is_refused_before_any_tool(service):
    reply, model = ask(service, "Rank everyone over 20%", [tool_use("find_patient", {"name": "Doe"})])
    assert reply.outcome is Outcome.OUT_OF_SCOPE and service.calls == [] and model.requests == []
    assert "20" not in reply.text


def test_a_tool_the_service_doesnt_offer_is_never_called(service):
    reply, _ = ask(service, "Risk for Jane Doe",
                   [tool_use("rank_patients", {"threshold": 0.2}), tool_use("find_patient", {"name": "Jane Doe"}, "t2")])
    assert [n for n, _ in service.calls][0] == "find_patient"
    assert reply.outcome is Outcome.ESTIMATE


def test_a_models_extra_inputs_never_reach_the_service(service):
    """The agent rebuilds the call from the patient id alone: "if she were 40" can't change anything."""
    reply, _ = ask(service, f"Risk for patient {PATIENT} if she were 40",
                   [tool_use("get_hospitalization_risk", {"patient_id": PATIENT, "agey1x": 40})])
    assert service.calls == [("get_hospitalization_risk", {"patient_id": PATIENT})]
    assert reply.outcome is Outcome.ESTIMATE and explain.NOTICE_ADJUST in reply.text
    assert_safe(reply)


def test_the_service_refuses_extra_inputs_too(service):
    from outcome_prediction_agent.service import ToolRefused
    with pytest.raises(ToolRefused, match="agey1x"):
        service.call("get_hospitalization_risk", {"patient_id": PATIENT, "agey1x": 40})


def test_only_the_services_tools_are_offered(service):
    _, model = ask(service, "Risk for Jane Doe", [tool_use("find_patient", {"name": "Jane Doe"})])
    assert [t["name"] for t in model.requests[0]["tools"]] == ["find_patient", "get_hospitalization_risk",
                                                               "get_model_card"]


# ── fail closed ──────────────────────────────────────────────────────────────────────

def test_an_unreachable_service_shows_no_estimate():
    reply, _ = ask(ReplayService(OUTPUTS, TOOLS, unavailable=True), "Risk for Jane Doe")
    assert reply.outcome is Outcome.UNAVAILABLE


def test_the_gate_withholds_an_ungrounded_reply(monkeypatch, service):
    monkeypatch.setattr(explain, "narrate_estimate", lambda ra, q, p=None: "The risk is 42.5%.")
    reply, _ = ask(service, "Risk for Jane Doe", [tool_use("find_patient", {"name": "Jane Doe"})])
    assert reply.outcome is Outcome.UNAVAILABLE and "42.5" not in reply.text


@pytest.mark.parametrize("question", ["Is that bad?", "Is she over 20%?", "Put her in a risk band"])
def test_band_questions_get_the_notice(service, question):
    reply, _ = ask(service, f"Jane Doe: {question}", [tool_use("find_patient", {"name": "Jane Doe"})])
    assert explain.NOTICE_BAND in reply.text and "20%" not in reply.text
    assert_safe(reply)


def test_the_model_card_never_answers_a_patient_question(service):
    reply, model = ask(service, "Risk for Jane Doe", [tool_use("get_model_card", {})],
                       [tool_use("find_patient", {"name": "Jane Doe"})])
    assert reply.outcome is Outcome.ESTIMATE
    assert ("get_model_card", {}) not in service.calls
    assert "about a patient" in str(model.requests[1]["messages"][-1]["content"][0]["content"])

