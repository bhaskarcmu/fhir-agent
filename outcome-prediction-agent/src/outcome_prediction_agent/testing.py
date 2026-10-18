"""Test support: a scripted model and a replay of the scoring service's recorded outputs.

Used by this package's tests (and usable by M9's acceptance tests): the replay enforces the same
input schemas the service does, so a test can't pass by calling a tool the service would refuse.
"""
from __future__ import annotations

import copy
from types import SimpleNamespace

from outcome_prediction_agent.service import ServiceUnavailable, ToolRefused


class ReplayService:
    """Answers like the scoring service, from its recorded outputs. Enforces the same schemas."""

    def __init__(self, outputs: dict, tools: list[dict], unavailable: bool = False):
        self.outputs, self.tools = outputs, tools
        self.calls: list[tuple[str, dict]] = []
        self.unavailable = unavailable

    def definitions(self) -> list[dict]:
        if self.unavailable:
            raise ServiceUnavailable("down")
        return copy.deepcopy(self.tools)

    def call(self, name: str, args: dict) -> dict:
        self.calls.append((name, args))
        schema = next((t["input_schema"] for t in self.tools if t["name"] == name), None)
        if schema is None:
            raise ToolRefused(f"no tool {name!r}")
        if extra := set(args) - set(schema["properties"]):
            raise ToolRefused(f"extra inputs are not permitted ({sorted(extra)})")
        if name == "get_model_card":
            return copy.deepcopy(self.outputs["model_card"])
        if name == "find_patient":
            key = {"Jane Doe": "one_match", "Doe": "two_matches"}.get(args.get("name", "").strip(), "no_match")
            return copy.deepcopy(self.outputs[key])
        if args.get("as_of") == "1950-01-01":
            return copy.deepcopy(self.outputs["no_estimate"])
        if args.get("patient_id") in (self.outputs["patient_id"], "9999"):
            return copy.deepcopy(self.outputs["estimate"])
        return {"outcome": "not_found", "detail": "patient not found"}


def tool_use(name: str, args: dict, id_: str = "t1"):
    return SimpleNamespace(type="tool_use", name=name, input=args, id=id_)


def text(content: str):
    return SimpleNamespace(type="text", text=content)


class ScriptedModel:
    """A stand-in for the LLM client: returns the given responses in order (then plain text)."""

    def __init__(self, *turns):
        self.turns = list(turns)
        self.requests: list[dict] = []
        self.messages = self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        content = self.turns.pop(0) if self.turns else [text("I think it's about 40%, which is high risk.")]
        has_tool = any(getattr(b, "type", "") == "tool_use" for b in content)
        return SimpleNamespace(content=content, stop_reason="tool_use" if has_tool else "end_turn", usage=None)
