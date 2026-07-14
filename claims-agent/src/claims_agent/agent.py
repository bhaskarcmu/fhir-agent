#!/usr/bin/env python3
"""
Claims Explanation Agent — a SEPARATE agent from the Phase 1 mcp-agent (D3).

It explains prescription-claim adjudication decisions in plain language. It is
**non-authoritative** (R17.8): it calls the claims-service to obtain the authoritative
decision and only narrates it — it never computes, changes, or overrides the outcome. All
clinical/business logic lives in the deterministic services.

Usage:
  python3 -m claims_agent --claim path/to/claim.json
  python3 -m claims_agent --claim '{"claimId":"C1", ...}'
  python3 -m claims_agent --claim claim.json --no-llm   # deterministic, no API key needed

Environment:
  ANTHROPIC_API_KEY / CLAUDE_API_KEY   Anthropic key (optional; falls back to deterministic)
  CLAIMS_GATEWAY_URL                   claims-service base URL (default http://localhost:8090)
  CLAIMS_API_KEY                       Kong API key (omit for local/direct)
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .explain import render_explanation
from .format import DIVIDER, error_block, header
from .tools import TOOL_DEFINITIONS, ClaimsClient, execute_tool

MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 1024

SYSTEM_PROMPT = """You explain prescription-claim adjudication decisions to clinicians and \
reviewers in clear, plain language.

Call adjudicate_claim exactly once with the provided claim to obtain the AUTHORITATIVE \
decision. Then explain it:
- State the outcome (approved / denied / pended / routed for manual review).
- Give the specific reason(s); if there are several, aggregate them in one clear explanation.
- If the claim was priced, state the total, patient pay, and plan pay.
- Cite the decision id for audit.

You must NEVER change, override, or contradict the decision the tool returns — you only \
narrate it. Never invent reasons, amounts, or outcomes."""


def run_query(client, user_input: str, claims_client: ClaimsClient, verbose: bool = True):
    """Run the tool-use loop. Returns (final_text, decision_dict_or_None)."""
    import anthropic  # local import so --no-llm path needs no key/SDK at import time  # noqa: F401

    messages = [{"role": "user", "content": user_input}]
    decision: dict | None = None

    while True:
        response = client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT, tools=TOOL_DEFINITIONS, messages=messages,
        )
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type == "tool_use":
                    if verbose:
                        print(f"  → {block.name}(…)")
                    result_str = execute_tool(block.name, block.input, claims_client)
                    if block.name == "adjudicate_claim":
                        try:
                            decision = json.loads(result_str)
                        except json.JSONDecodeError:
                            decision = None
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": result_str})
            messages.append({"role": "user", "content": results})
            continue

        final_text = "".join(b.text for b in response.content if hasattr(b, "text"))
        return final_text, decision


def explain_claim(claim: dict, use_llm: bool, claims_client: ClaimsClient) -> str:
    """Adjudicate then explain. LLM narrative when available, deterministic otherwise."""
    anthropic_client = _anthropic_client() if use_llm else None

    if anthropic_client is None:
        # Deterministic path: get the authoritative decision, render it (no LLM required).
        decision = claims_client.adjudicate(claim)
        return header(decision.get("outcome", "?"), decision.get("decisionId", "n/a")) \
            + "\n" + DIVIDER + "\n" + render_explanation(decision)

    prompt = "Adjudicate and explain this prescription claim:\n" + json.dumps(claim, indent=2)
    final_text, decision = run_query(anthropic_client, prompt, claims_client)
    head = header(decision.get("outcome", "?"), decision.get("decisionId", "n/a")) if decision \
        else "Decision unavailable"
    return head + "\n" + DIVIDER + "\n" + (final_text or render_explanation(decision or {}))


def _anthropic_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("CLAUDE_API_KEY", "")
    if not api_key:
        return None
    import anthropic
    return anthropic.Anthropic(api_key=api_key)


def _load_claim(value: str) -> dict:
    if os.path.isfile(value):
        with open(value) as f:
            return json.load(f)
    return json.loads(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explain a claim adjudication decision.")
    parser.add_argument("--claim", required=True, help="Claim JSON, or a path to a JSON file.")
    parser.add_argument("--no-llm", action="store_true",
                        help="Deterministic explanation only (no Anthropic call).")
    parser.add_argument("--claims-url", default=None, help="claims-service base URL.")
    args = parser.parse_args(argv)

    try:
        claim = _load_claim(args.claim)
    except (OSError, json.JSONDecodeError) as e:
        print(error_block(f"Could not read claim: {e}"))
        return 2

    claims_client = ClaimsClient(base_url=args.claims_url)
    use_llm = not args.no_llm
    if use_llm and _anthropic_client() is None:
        print("(no Anthropic key found — using deterministic explanation)\n")
        use_llm = False

    try:
        print(explain_claim(claim, use_llm, claims_client))
    except Exception as e:  # noqa: BLE001 - surface a clean error to the user
        print(error_block(f"Adjudication/explanation failed: {e}"))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
