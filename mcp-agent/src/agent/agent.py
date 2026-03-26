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

from .format import (
    agent_response,
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

SYSTEM_PROMPT = """You are a clinical decision support assistant for healthcare professionals.
You help clinicians evaluate medication refill safety by checking for drug-allergy conflicts
and other clinical risks.

When asked about a patient by name, always call get_patient_summary first to resolve the
name to a patient ID. Then call assess_refill_risk with that ID.

Present your findings clearly and concisely. Always include:
- The patient's name and the risk level (HIGH/MODERATE/LOW)
- The specific clinical reason for the risk level
- The FHIR RiskAssessment ID for audit purposes
- A clear recommendation (dispense / review / do not dispense)

If risk is HIGH, be direct and emphatic. Patient safety is the priority.
If you cannot find a patient, say so clearly and suggest alternatives.
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

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        # ── Tool use ──────────────────────────────────────────────────────────
        if response.stop_reason == "tool_use":
            # Append assistant's tool-use message
            messages = messages + [
                {"role": "assistant", "content": response.content}
            ]

            # Execute each tool call and collect results
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    if verbose:
                        _print_tool_call(block.name, block.input)

                    result_str = execute_tool(block.name, block.input)

                    if verbose:
                        _print_tool_result(block.name, result_str)

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    })

            # Feed results back to Claude
            messages = messages + [
                {"role": "user", "content": tool_results}
            ]
            continue

        # ── Final response ────────────────────────────────────────────────────
        final_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                final_text += block.text

        messages = messages + [
            {"role": "assistant", "content": response.content}
        ]

        return final_text, messages


def _print_tool_call(name: str, inputs: dict) -> None:
    """Print a tool call indicator during execution."""
    if name == "get_patient_summary":
        summary = f"searching for \"{inputs.get('name', '')}\"..."
    elif name == "assess_refill_risk":
        summary = f"evaluating patient {inputs.get('patient_id', '')}..."
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
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print(error_block(
            "ANTHROPIC_API_KEY is not set.\n"
            "  export ANTHROPIC_API_KEY=<your-key>"
        ))
        sys.exit(1)

    fhir_url = os.environ.get("FHIR_GATEWAY_URL", "")
    if not fhir_url:
        print(error_block(
            "FHIR_GATEWAY_URL is not set.\n"
            "  export FHIR_GATEWAY_URL=http://localhost:8080/fhir"
        ))
        sys.exit(1)

    return anthropic.Anthropic(api_key=api_key)


def interactive_mode(client: anthropic.Anthropic) -> None:
    """Run the agent in interactive REPL mode."""
    print(welcome())
    messages: list[dict] = []

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
            print(agent_response(final_text))
        except anthropic.APIError as exc:
            print(error_block(f"Anthropic API error: {exc}"))
        except Exception as exc:
            print(error_block(f"Unexpected error: {exc}"))
            raise


def non_interactive_mode(client: anthropic.Anthropic, query: str) -> int:
    """Run a single query and exit. Returns exit code."""
    print(f"\nQuery: {query}\n")
    try:
        final_text, _ = run_query(client, query)
        print(agent_response(final_text))
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

    client = _check_env()

    if args.query:
        sys.exit(non_interactive_mode(client, args.query))
    else:
        interactive_mode(client)


if __name__ == "__main__":
    main()
