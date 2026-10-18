"""The hospitalization-risk agent (M8; design.md §9, O15, O69).

The language model orchestrates: it reads the clinician's question, finds the patient and calls
the service's tools. Code decides everything the clinician sees:

- only the service's published tools are offered, and the service validates every call;
- questions about more than one patient are refused before any tool is called;
- the model may score only a patient id that `find_patient` returned or the clinician typed;
- a single match is scored by code, without asking the model to take the second step;
- the reply is built by `explain.py` from the tool output, checked by `explain.grounded`, and
  shown only if every number in it came from the service. The model's own text is never shown.

    outcome-prediction-agent --query "What is the hospitalization risk for Jane Doe?"

Self-hosted Llama by default (O16, Phase 6 H45); see agent_platform.providers for LLM_PROVIDER.
Needs OUTCOME_PREDICTION_URL (default http://localhost:8005).
"""
from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

from agent_platform import (
    CircuitOpenError,
    CostLimitExceededError,
    ESTIMATED_TOKENS_PER_CALL,
    build_llm_client,
    call_with_resilience,
    get_tracer,
    layer_attrs,
    load_policy,
    safe_set_attributes,
    setup_tracing,
    start_span,
)

from outcome_prediction_agent import explain
from outcome_prediction_agent.explain import Outcome, Reply
from outcome_prediction_agent.service import ServiceTools, ServiceUnavailable, ToolRefused

log = logging.getLogger("outcome_prediction_agent")
_tracer = get_tracer("outcome-prediction-agent")
MAX_TOKENS = 512
MAX_STEPS = 4
REFUSED_ID = ("Refused: that is not a patient id. First call find_patient with the patient's name, "
              "for example find_patient(name=\"Jane Doe\"); the risk is then fetched for you.")
# Small self-hosted models often answer in prose instead of calling a tool; one reminder, then stop.
NUDGE_PATIENT = "Use the tools: call find_patient with the patient's name from my question."
NUDGE_MODEL = "Use the tools: call get_model_card."
NOT_A_MODEL_QUESTION = "Refused: the question is about a patient. Call find_patient with the patient's name."
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
# A patient id the clinician typed: all digits ("3208"), a UUID, or written explicitly as
# "Patient/<id>" or "id <id>". A word mixing letters and digits is NOT an id — Synthea names
# ("Beier427") look like that, and a small model passes names as ids (found in M9's live run).
ID_TOKEN = re.compile(r"(?<![\w-])(\d{1,64})(?![\w-])|\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b"
                      r"|\b(?:Patient/|id[:#]?\s+)([A-Za-z0-9\-.]{1,64})", re.I)

_INSTRUCTIONS = """You help clinicians look up a patient's 12-month hospitalization risk estimate.
To answer a question about a patient: call find_patient with the patient's name. If the clinician
gave a patient id instead, call get_hospitalization_risk with that id.
To answer "how was the model built?": call get_model_card.
Do not answer from your own knowledge. Do not calculate, adjust or classify anything. Only call tools."""
SYSTEM_PROMPT = _INSTRUCTIONS + "\n\n" + load_policy(Path(__file__).with_name("policy.md"))


def _gate(reply: Reply) -> Reply:
    """The output gate: a reply with any number the service didn't return is never shown."""
    if ungrounded := explain.grounded(reply.text, reply.evidence):
        log.error("withheld an ungrounded reply (numbers not in tool output: %s)", ungrounded)
        return Reply(Outcome.UNAVAILABLE, explain.UNAVAILABLE_TEXT)
    return reply


class Turn:
    """One question: the tools called, what they returned, and the patients they named."""

    def __init__(self, service: ServiceTools, question: str):
        self.service = service
        self.question = question
        self.evidence: list[dict] = []
        self.candidates: dict[str, dict] = {}
        self.as_of = (DATE.findall(question) or [None])[0]

    def allowed_ids(self) -> set[str]:
        typed = {next(g for g in m if g) for m in ID_TOKEN.findall(DATE.sub(" ", self.question))}
        return set(self.candidates) | typed

    def call(self, name: str, args: dict) -> dict:
        with start_span(f"execute_tool {name}", _tracer,
                        {"gen_ai.tool.name": name, **layer_attrs("agent.tools", name)}):
            result = self.service.call(name, args)
        self.evidence.append({"tool": name, "result": result})
        return result

    def risk(self, patient_id: str) -> Reply:
        args = {"patient_id": patient_id} | ({"as_of": self.as_of} if self.as_of else {})
        result = self.call("get_hospitalization_risk", args)
        if result["outcome"] == "estimate":
            text = explain.narrate_estimate(result["risk_assessment"], self.question, self.candidates.get(patient_id))
            return Reply(Outcome.ESTIMATE, text, self.evidence)
        if result["outcome"] == "no_estimate":
            return Reply(Outcome.NO_ESTIMATE, f"The service made no estimate: {result['detail']}", self.evidence)
        if result["outcome"] == "not_found":
            return Reply(Outcome.NOT_FOUND, "The service has no patient with that id.", self.evidence)
        return Reply(Outcome.UNAVAILABLE, explain.UNAVAILABLE_TEXT, self.evidence)

    def handle(self, name: str, args: dict) -> Reply | str:
        """Run one model-requested tool call. Returns a final Reply, or text to hand back to the model."""
        if name == "find_patient":
            result = self.call(name, args)
            if result["outcome"] != "candidates":
                return Reply(Outcome.UNAVAILABLE, explain.UNAVAILABLE_TEXT, self.evidence)
            self.candidates.update({c["id"]: c for c in result["candidates"]})
            if result["found"] == 0:
                return Reply(Outcome.NOT_FOUND, "No patient matches that name.", self.evidence)
            if result["ambiguous"]:
                return Reply(Outcome.CHOOSE_PATIENT, explain.narrate_candidates(result), self.evidence)
            return self.risk(result["candidates"][0]["id"])           # one match: code takes the next step
        if name == "get_hospitalization_risk":
            patient_id = str(args.get("patient_id", "")).removeprefix("Patient/")
            if patient_id not in self.allowed_ids():
                return REFUSED_ID
            return self.risk(patient_id)
        if name == "get_model_card":
            if not explain.MODEL_CUES.search(self.question):
                return NOT_A_MODEL_QUESTION
            result = self.call(name, {})
            return Reply(Outcome.MODEL_CARD, explain.narrate_model_card(result["model_card"]), self.evidence)
        return f"Refused: {name} is not one of this service's tools."


def run_query(llm, model: str, question: str, service: ServiceTools | None = None,
              gen_ai_system: str = "ollama") -> Reply:
    service = service or ServiceTools()
    with start_span("agent.run_query", _tracer, layer_attrs("agent.orchestration", "run_query")) as span:
        reply = _gate(_run(llm, model, question, service, gen_ai_system))     # every reply, every path
        safe_set_attributes(span, {"outcome": reply.outcome.value})
    return reply


def _run(llm, model, question, service, gen_ai_system) -> Reply:
    if explain.POPULATION_CUES.search(question):
        return Reply(Outcome.OUT_OF_SCOPE, explain.NOTICE_POPULATION)
    try:
        tools = service.definitions()
    except ServiceUnavailable:
        return Reply(Outcome.UNAVAILABLE, explain.UNAVAILABLE_TEXT)
    allowed = {t["name"] for t in tools}
    turn = Turn(service, question)
    messages = [{"role": "user", "content": question}]
    nudged = False
    for _ in range(MAX_STEPS):
        try:
            with start_span(f"chat {model}", _tracer, {"gen_ai.system": gen_ai_system, "gen_ai.request.model": model,
                                                       **layer_attrs("agent.orchestration", "run_query")}):
                response = call_with_resilience(
                    lambda: llm.messages.create(model=model, max_tokens=MAX_TOKENS, system=SYSTEM_PROMPT,
                                                tools=tools, messages=messages),
                    estimated_tokens=ESTIMATED_TOKENS_PER_CALL)
        except (CircuitOpenError, CostLimitExceededError):
            return Reply(Outcome.UNAVAILABLE, explain.UNAVAILABLE_TEXT)
        uses = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
        if not uses:                                # the model answered in text: never shown
            if nudged or turn.evidence:
                break
            nudged = True
            nudge = NUDGE_MODEL if explain.MODEL_CUES.search(question) else NUDGE_PATIENT
            messages = messages + [{"role": "assistant", "content": response.content}, {"role": "user", "content": nudge}]
            continue
        messages = messages + [{"role": "assistant", "content": response.content}]
        results = []
        for block in uses:
            args = block.input if isinstance(block.input, dict) else {}
            try:
                outcome = (turn.handle(block.name, args) if block.name in allowed
                           else f"Refused: {block.name} is not one of this service's tools.")
            except ToolRefused as e:
                outcome = f"Refused by the service: {e}"
            except ServiceUnavailable:
                return Reply(Outcome.UNAVAILABLE, explain.UNAVAILABLE_TEXT)
            if isinstance(outcome, Reply):
                return _gate(outcome)
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": outcome})
        messages = messages + [{"role": "user", "content": results}]       # new lists: never mutate what was sent
    return Reply(Outcome.NEEDS_PATIENT, explain.ASK_PATIENT)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Ask for a patient's 12-month hospitalization risk.")
    parser.add_argument("--query", required=True)
    parser.add_argument("--url", default=None, help="outcome-prediction service (default $OUTCOME_PREDICTION_URL)")
    args = parser.parse_args(argv)
    setup_tracing("outcome-prediction-agent")
    resolved = build_llm_client()
    reply = run_query(resolved.client, resolved.model, args.query, ServiceTools(args.url), resolved.gen_ai_system)
    print(reply.text)
    print(f"\n[{reply.outcome.value}]")


if __name__ == "__main__":
    main()
