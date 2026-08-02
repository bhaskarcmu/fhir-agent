#!/usr/bin/env python3
"""
MCP Agent — Clinical workflow orchestrator.

Uses the Anthropic tool-use API (raw, no framework) to interpret natural
language clinical queries, call FHIR and triage tools, and compose a
structured clinical response.

The agent contains no clinical logic. It orchestrates tool calls and
composes narratives. Clinical logic lives in the triage service.

Usage:
  # Interactive mode
  python3 mcp-agent/src/agent/agent.py

  # Non-interactive (demo / CI)
  python3 mcp-agent/src/agent/agent.py --query "Check refill risk for Kristle Mraz"

Environment variables:
  ANTHROPIC_API_KEY    Anthropic API key (required)
  FHIR_GATEWAY_URL     FHIR server base URL (required)
  FHIR_API_KEY         Kong API key (omit for local dev)
  TRIAGE_SERVICE_URL   Triage service base URL (default: http://localhost:8001)
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import anthropic

from agent_platform import (
    get_tracer,
    is_unknown,
    safe_set_attributes,
    setup_tracing,
    start_span,
    validate_decision,
)

from .format import (
    decision_block,
    error_block,
    tool_call_line,
    welcome,
)
from .tools import TOOL_DEFINITIONS, execute_tool

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 1024

# Crude stopgap against interactive_mode's message list growing unbounded.
# Not the real memory/token-budget policy -- that's a real number set from
# telemetry in Phase 6 M3. This just closes the current zero-bound risk
# early (docs/phase6/decisions.md H13).
MAX_REPL_TURNS = 40

# Lazily bound to whatever TracerProvider setup_tracing() installs -- safe to
# create before setup_tracing() runs (docs/phase6/design.md Section 4.2).
_tracer = get_tracer("mcp-agent")

SYSTEM_PROMPT = """You are a clinical decision support assistant for healthcare professionals.
You help clinicians evaluate medication refill safety by checking for drug-allergy conflicts
and other clinical risks.

When asked about a patient by name, always call get_patient_summary first to resolve the
name to a patient ID. Then call assess_refill_risk with that ID.

Once you have the information you need, you MUST call submit_decision as your final action --
do not write a free-text final answer instead. Map the risk level to a decision:
- LOW risk → DISPENSE
- HIGH risk → DO_NOT_DISPENSE
- MODERATE risk, or anything you are not confident about → REVIEW
- If assess_refill_risk returned risk_level UNKNOWN or an error (the safety check could not
  be completed), you must submit REVIEW -- never guess DISPENSE or DO_NOT_DISPENSE on an
  incomplete check.

If risk is HIGH, be direct and emphatic in your rationale. Patient safety is the priority.
If you cannot find a patient, say so clearly in your rationale and suggest alternatives, then
submit_decision with REVIEW.
Never fabricate patient data or clinical information."""


# ─────────────────────────────────────────────────────────────────────────────
# Agent loop
# ─────────────────────────────────────────────────────────────────────────────

def run_query(
    client: anthropic.Anthropic,
    user_input: str,
    messages: list[dict] | None = None,
    verbose: bool = True,
) -> tuple[str, list[dict]]:
    """
    Run one query through the agent loop.

    Returns (final_text_response, updated_messages).
    The caller can pass messages back in for multi-turn conversation.
    """
    if messages is None:
        messages = []

    messages = messages + [{"role": "user", "content": user_input}]

    # Fail-closed enforcement state for this query (docs/phase6/decisions.md
    # H18): tracks whether any risk check during this run_query call came
    # back UNKNOWN, so a subsequent submit_decision can be overridden
    # regardless of which order the model called tools in. Scoped to this
    # single query, not the whole session -- see the docstring note below.
    saw_unknown_risk = False

    # One trace per agent run (docs/phase6/design.md Section 4.2, R4).
    # Deliberately no user_input text as a span attribute -- a clinician's
    # query can itself contain a patient name.
    with start_span("agent.run_query", _tracer):
        while True:
            with start_span(
                f"chat {MODEL}",
                _tracer,
                {"gen_ai.system": "anthropic", "gen_ai.request.model": MODEL},
            ) as chat_span:
                response = client.messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=SYSTEM_PROMPT,
                    tools=TOOL_DEFINITIONS,
                    messages=messages,
                )
                usage = getattr(response, "usage", None)
                safe_set_attributes(chat_span, {
                    "gen_ai.response.finish_reasons": [response.stop_reason],
                    "gen_ai.usage.input_tokens": getattr(usage, "input_tokens", None),
                    "gen_ai.usage.output_tokens": getattr(usage, "output_tokens", None),
                })

            # ── Tool use ──────────────────────────────────────────────────────
            if response.stop_reason == "tool_use":
                # Append assistant's tool-use message
                messages = messages + [
                    {"role": "assistant", "content": response.content}
                ]

                # Execute every non-decision tool call first, updating
                # saw_unknown_risk as we go, so a submit_decision call
                # anywhere in this same batch -- before or after the risk
                # check -- is validated against the fully up-to-date state.
                tool_results = []
                decision_block_data = None
                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    if block.name == "submit_decision":
                        decision_block_data = block
                        continue

                    if verbose:
                        _print_tool_call(block.name, block.input)

                    with start_span(
                        f"execute_tool {block.name}",
                        _tracer,
                        {
                            "gen_ai.tool.name": block.name,
                            "patient_id": block.input.get("patient_id"),
                        },
                    ):
                        result_str = execute_tool(block.name, block.input)

                    if verbose:
                        _print_tool_result(block.name, result_str)

                    if block.name == "assess_refill_risk":
                        try:
                            parsed = json.loads(result_str)
                        except json.JSONDecodeError:
                            parsed = {}
                        if is_unknown(parsed.get("risk_level")):
                            saw_unknown_risk = True

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    })

                # ── submit_decision: terminal action, validated and enforced ──
                if decision_block_data is not None:
                    inputs = decision_block_data.input
                    with start_span("agent.submit_decision", _tracer) as decision_span:
                        decision, override_reason = validate_decision(
                            inputs.get("decision"),
                            saw_unknown_risk=saw_unknown_risk,
                        )
                        safe_set_attributes(decision_span, {
                            "decision": decision.value,
                            "override_reason": override_reason,
                            "patient_id": inputs.get("patient_id"),
                        })

                    if verbose:
                        _print_tool_call("submit_decision", inputs)

                    ack = {
                        "recorded_decision": decision.value,
                        "override_reason": override_reason,
                    }
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": decision_block_data.id,
                        "content": json.dumps(ack, indent=2),
                    })
                    messages = messages + [
                        {"role": "user", "content": tool_results}
                    ]

                    final_text = decision_block(
                        decision=decision.value,
                        patient_id=str(inputs.get("patient_id", "")),
                        risk_assessment_id=inputs.get("risk_assessment_id"),
                        rationale=str(inputs.get("rationale", "")),
                        override_reason=override_reason,
                    )
                    return final_text, messages

                # No decision this round -- feed results back to Claude and keep going.
                messages = messages + [
                    {"role": "user", "content": tool_results}
                ]
                continue

            # ── Final response without submit_decision ──────────────────────
            # The model answered in free text instead of calling
            # submit_decision. That's an off-contract turn (docs/phase6/
            # decisions.md H5, H21) -- fail closed to REVIEW, but keep the
            # model's own narrative visible as supporting context rather
            # than discarding it.
            narrative = ""
            for block in response.content:
                if hasattr(block, "text"):
                    narrative += block.text

            messages = messages + [
                {"role": "assistant", "content": response.content}
            ]

            with start_span("agent.submit_decision", _tracer) as decision_span:
                decision, override_reason = validate_decision(
                    None, saw_unknown_risk=saw_unknown_risk
                )
                safe_set_attributes(decision_span, {
                    "decision": decision.value,
                    "override_reason": override_reason,
                })

            final_text = decision_block(
                decision=decision.value,
                patient_id="",
                risk_assessment_id=None,
                rationale=narrative.strip() or "(no rationale provided)",
                override_reason=override_reason,
            )
            return final_text, messages


def _print_tool_call(name: str, inputs: dict) -> None:
    """Print a tool call indicator during execution."""
    if name == "get_patient_summary":
        summary = f"searching for \"{inputs.get('name', '')}\"..."
    elif name == "assess_refill_risk":
        pid = inputs.get("patient_id", "")
        mid = inputs.get("medication_id")
        summary = f"evaluating patient {pid}" + (f", med {mid}" if mid else "") + "..."
    else:
        summary = str(inputs)
    print(tool_call_line(name, summary))


def _print_tool_result(name: str, result_str: str) -> None:
    """Print a brief tool result summary."""
    try:
        result = json.loads(result_str)
    except json.JSONDecodeError:
        return

    if name == "get_patient_summary":
        if result.get("found"):
            if result.get("multiple_matches"):
                print(tool_call_line(name, f"found {result['count']} matches"))
            else:
                p = result["patient"]
                print(tool_call_line(name, f"found: {p['name']}, {p['gender']}, DOB {p['birth_date']}"))
        else:
            print(tool_call_line(name, "not found"))

    elif name == "assess_refill_risk":
        risk = result.get("risk_level", "?")
        aid = result.get("assessment_id", "")
        print(tool_call_line(name, f"risk={risk}  id={aid}"))


# ─────────────────────────────────────────────────────────────────────────────
# Entry points
# ─────────────────────────────────────────────────────────────────────────────

def _check_env() -> anthropic.Anthropic:
    """Validate required environment variables and return an Anthropic client."""
    # Accept CLAUDE_API_KEY as a fallback — that is the name the Ona/devcontainer
    # secret is stored under, while the Anthropic SDK expects ANTHROPIC_API_KEY.
    api_key = os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("CLAUDE_API_KEY", "")
    if not api_key:
        print(error_block(
            "ANTHROPIC_API_KEY is not set (CLAUDE_API_KEY is also accepted).\n"
            "  export ANTHROPIC_API_KEY=<your-key>"
        ))
        sys.exit(1)

    fhir_url = os.environ.get("FHIR_GATEWAY_URL", "")
    if not fhir_url:
        print(error_block(
            "FHIR_GATEWAY_URL is not set.\n"
            "  export FHIR_GATEWAY_URL=http://localhost:8000/fhir"
        ))
        sys.exit(1)

    return anthropic.Anthropic(api_key=api_key)


def interactive_mode(client: anthropic.Anthropic) -> None:
    """Run the agent in interactive REPL mode."""
    print(welcome())
    messages: list[dict] = []
    turn_count = 0

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit", "q"}:
            print("Goodbye.")
            break

        print()
        try:
            final_text, messages = run_query(client, user_input, messages)
            print(final_text)
        except anthropic.APIError as exc:
            print(error_block(f"Anthropic API error: {exc}"))
            continue
        except Exception as exc:
            print(error_block(f"Unexpected error: {exc}"))
            raise

        turn_count += 1
        if turn_count >= MAX_REPL_TURNS:
            print(error_block(
                f"This session has reached {MAX_REPL_TURNS} turns -- starting a fresh "
                "conversation to keep context bounded (a crude stopgap; Phase 6 M3 replaces "
                "this with a real, telemetry-derived budget)."
            ))
            messages = []
            turn_count = 0


def non_interactive_mode(client: anthropic.Anthropic, query: str) -> int:
    """Run a single query and exit. Returns exit code."""
    print(f"\nQuery: {query}\n")
    try:
        final_text, _ = run_query(client, query)
        print(final_text)
        return 0
    except anthropic.APIError as exc:
        print(error_block(f"Anthropic API error: {exc}"))
        return 1
    except Exception as exc:
        print(error_block(f"Unexpected error: {exc}"))
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agentic Healthcare Platform — Clinical Assistant"
    )
    parser.add_argument(
        "--query", "-q",
        metavar="QUERY",
        help="Run a single query non-interactively and exit.",
    )
    args = parser.parse_args()

    setup_tracing("mcp-agent")
    client = _check_env()

    if args.query:
        sys.exit(non_interactive_mode(client, args.query))
    else:
        interactive_mode(client)


if __name__ == "__main__":
    main()
