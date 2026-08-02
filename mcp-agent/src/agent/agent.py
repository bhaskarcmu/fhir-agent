#!/usr/bin/env python3
"""
MCP Agent — Clinical workflow orchestrator.

Uses the Anthropic tool-use API (raw, no framework) to interpret natural
language clinical queries, call FHIR and triage tools, and compose a
structured clinical response.

The agent contains no clinical logic. It orchestrates tool calls and
composes narratives. Clinical logic lives in the triage service.

Usage:
  # Interactive mode -- self-hosted Llama by default, free, PHI stays local.
  python3 mcp-agent/src/agent/agent.py

  # Non-interactive (demo / CI)
  python3 mcp-agent/src/agent/agent.py --query "Check refill risk for Kristle Mraz"

  # See what's actually available before choosing (docs/phase6/decisions.md H48)
  python3 mcp-agent/src/agent/agent.py --list-models ollama

  # Explicit opt-in to a stronger, third-party-hosted model for this run
  python3 mcp-agent/src/agent/agent.py --provider anthropic --model claude-sonnet-4-5 \
      --query "Check refill risk for Kristle Mraz"

Environment variables:
  FHIR_GATEWAY_URL     FHIR server base URL (required)
  FHIR_API_KEY         Kong API key (omit for local dev)
  TRIAGE_SERVICE_URL   Triage service base URL (default: http://localhost:8001)

  Provider seam (docs/phase6/decisions.md H4, superseded by H45-H48) -- three
  identities, --provider/--model above take precedence over these for a
  single run:
  LLM_PROVIDER   "ollama" (default when unset -- self-hosted, free, PHI
                 never leaves this host) | "anthropic" | "openai_compatible".
                 A present ANTHROPIC_API_KEY does NOT change this default on
                 its own (H46) -- only an explicit LLM_PROVIDER does.
  LLM_MODEL      Model name. Optional for "ollama" (default "llama3.2:1b")
                 and "anthropic" (default "claude-sonnet-4-5"); REQUIRED for
                 "openai_compatible" (no safe generic default exists).
  LLM_BASE_URL   Optional for "ollama" (default http://localhost:11434/v1);
                 REQUIRED for "openai_compatible".
  LLM_API_KEY    Optional -- Ollama needs none, DeepSeek/OpenRouter do.
  ANTHROPIC_API_KEY / CLAUDE_API_KEY   Required only when LLM_PROVIDER=anthropic.
  DEPLOYMENT_ENV=production            Refuses to silently default to Ollama
                 if LLM_PROVIDER is unset (H47) -- a minimal guardrail
                 pending the fuller environment-tier design deferred to M7.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import anthropic
import httpx

from agent_platform import (
    AgentDecision,
    CircuitOpenError,
    CostLimitExceededError,
    ESTIMATED_TOKENS_PER_CALL,
    ResolvedProvider,
    build_client_for,
    build_llm_client,
    call_with_resilience,
    compact,
    create_session,
    current_trace_id,
    extract_generic_name,
    fetch_drug_class,
    fetch_drug_label_citation,
    get_tracer,
    is_unknown,
    judge_response,
    layer_attrs,
    list_anthropic_models,
    list_ollama_models,
    list_openai_compatible_models,
    load_policy,
    load_session,
    record_usage,
    safe_set_attributes,
    save_session,
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

# Lazily bound to whatever TracerProvider setup_tracing() installs -- safe to
# create before setup_tracing() runs (docs/phase6/design.md Section 4.2).
_tracer = get_tracer("mcp-agent")

# mcp-agent/policy.md, two directories up from this file (mcp-agent/src/agent/
# -> mcp-agent/). Copied into the Docker image alongside src/ -- see Dockerfile.
POLICY_PATH = Path(__file__).resolve().parents[2] / "policy.md"

_TOOL_USE_INSTRUCTIONS = """You are a clinical decision support assistant for healthcare professionals.
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

# Policy rules load straight into the system prompt (docs/phase6/decisions.md
# H6) -- they always apply, so retrieval would be the wrong mechanism for
# them. Distinct from _TOOL_USE_INSTRUCTIONS above: that's tool-orchestration
# mechanics ("how to use these tools"); policy.md is clinical/business policy
# ("what this agent is and isn't allowed to do"). Loaded once at import time
# -- a missing policy file fails the whole process at startup (load_policy's
# own contract), not silently at first query.
SYSTEM_PROMPT = _TOOL_USE_INSTRUCTIONS + "\n\n" + load_policy(POLICY_PATH)


# ─────────────────────────────────────────────────────────────────────────────
# Agent loop
# ─────────────────────────────────────────────────────────────────────────────

def run_query(
    client: anthropic.Anthropic,
    user_input: str,
    messages: list[dict] | None = None,
    verbose: bool = True,
    token_count: int = 0,
    stats: dict | None = None,
    model: str = MODEL,
    gen_ai_system: str = "anthropic",
) -> tuple[str, list[dict]]:
    """
    Run one query through the agent loop.

    Returns (final_text_response, updated_messages). The caller can pass
    messages back in for multi-turn conversation.

    token_count is the caller's last known conversation size (docs/phase6/
    decisions.md H13, design.md Section 4.3) -- typically the input_tokens
    of the previous real API response, which already reflects the full
    history being sent. If it exceeds TOKEN_BUDGET, the oldest turn is
    dropped before this query runs. Deliberately doesn't change run_query's
    return arity to also hand back the new token_count -- pass a `stats`
    dict and read stats["token_count"] afterward, so every existing
    2-tuple-unpacking call site (and test) stays valid unchanged.

    client may be anthropic.Anthropic or agent_platform's
    OpenAICompatibleProvider (docs/phase6/decisions.md H4, M5) -- both
    duck-type the same client.messages.create(**kwargs) surface, so
    nothing else in this function branches on which one it is. model and
    gen_ai_system are new, purely additive parameters defaulting to the
    module constant MODEL and "anthropic" respectively -- every pre-M5
    call site (and test) that doesn't pass them keeps working unchanged
    (the same discipline as H31's `stats` parameter).
    """
    if messages is None:
        messages = []

    messages, compacted = compact(messages, token_count)
    if compacted and verbose:
        print(error_block(
            "Conversation exceeded the token budget -- dropped the oldest turn "
            "to keep going (docs/phase6/decisions.md H13)."
        ))

    messages = messages + [{"role": "user", "content": user_input}]

    # Fail-closed enforcement state for this query (docs/phase6/decisions.md
    # H18): tracks whether any risk check during this run_query call came
    # back UNKNOWN, so a subsequent submit_decision can be overridden
    # regardless of which order the model called tools in. Scoped to this
    # single query, not the whole session -- see the docstring note below.
    saw_unknown_risk = False
    # Medication(s) flagged by assess_refill_risk during this run, if any --
    # feeds the post-decision citation lookup only (docs/phase6/decisions.md
    # H15). Never read before a decision is final; see _fetch_citations().
    flagged_medications: list[dict] = []

    # One trace per agent run (docs/phase6/design.md Section 4.2, R4).
    # Deliberately no user_input text as a span attribute -- a clinician's
    # query can itself contain a patient name.
    with start_span(
        "agent.run_query", _tracer, layer_attrs("agent.orchestration", "run_query")
    ):
        if stats is not None:
            # Captured now, while the span is still current -- current_trace_id()
            # returns None once this `with` block exits, so a caller reading
            # stats after run_query() returns (e.g. api.py, after the span has
            # already closed) would otherwise always see None.
            stats["trace_id"] = current_trace_id()

        while True:
            with start_span(
                f"chat {model}",
                _tracer,
                {
                    "gen_ai.system": gen_ai_system,
                    "gen_ai.request.model": model,
                    **layer_attrs("agent.orchestration", "run_query"),
                },
            ) as chat_span:
                # Circuit breaker + rate/cost limiter wrap this one paid,
                # external call (docs/phase6/decisions.md H19, H20) regardless
                # of provider (H4) -- resilience.py's breaker treats both
                # anthropic.APIError and httpx.HTTPError as tripping failures.
                # token_count is the caller's last-known conversation size --
                # the same number compact() above already uses -- and is a
                # good pre-call cost estimate since every call resends the
                # full history; ESTIMATED_TOKENS_PER_CALL covers a session's
                # first call, before any real measurement exists yet.
                try:
                    response = call_with_resilience(
                        lambda: client.messages.create(
                            model=model,
                            max_tokens=MAX_TOKENS,
                            system=SYSTEM_PROMPT,
                            tools=TOOL_DEFINITIONS,
                            messages=messages,
                        ),
                        estimated_tokens=token_count or ESTIMATED_TOKENS_PER_CALL,
                    )
                except (CircuitOpenError, CostLimitExceededError) as exc:
                    return _fail_closed_unavailable(str(exc), messages)

                usage = getattr(response, "usage", None)
                input_tokens = getattr(usage, "input_tokens", None)
                output_tokens = getattr(usage, "output_tokens", None)
                safe_set_attributes(chat_span, {
                    "gen_ai.response.finish_reasons": [response.stop_reason],
                    "gen_ai.usage.input_tokens": input_tokens,
                    "gen_ai.usage.output_tokens": output_tokens,
                })
                if input_tokens is not None and output_tokens is not None:
                    record_usage(input_tokens, output_tokens)
                if stats is not None and input_tokens is not None:
                    # input_tokens already reflects the full history just sent --
                    # the simplest accurate "how big is this conversation now"
                    # measurement, no separate estimate needed.
                    stats["token_count"] = input_tokens

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
                            **layer_attrs("agent.tools", block.name),
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
                        flagged_medications.extend(parsed.get("flagged_medications") or [])

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    })

                # ── submit_decision: terminal action, validated and enforced ──
                if decision_block_data is not None:
                    inputs = decision_block_data.input
                    with start_span(
                        "agent.submit_decision",
                        _tracer,
                        layer_attrs("agent.orchestration", "submit_decision"),
                    ) as decision_span:
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

                    rationale = str(inputs.get("rationale", ""))
                    final_text = decision_block(
                        decision=decision.value,
                        patient_id=str(inputs.get("patient_id", "")),
                        risk_assessment_id=inputs.get("risk_assessment_id"),
                        rationale=rationale,
                        override_reason=override_reason,
                        trace_id=current_trace_id(),
                        citations=_fetch_citations(flagged_medications) if flagged_medications else [],
                        judgment=judge_response(client, model, query=user_input, rationale=rationale),
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

            with start_span(
                "agent.submit_decision",
                _tracer,
                layer_attrs("agent.orchestration", "submit_decision"),
            ) as decision_span:
                decision, override_reason = validate_decision(
                    None, saw_unknown_risk=saw_unknown_risk
                )
                safe_set_attributes(decision_span, {
                    "decision": decision.value,
                    "override_reason": override_reason,
                })

            rationale = narrative.strip() or "(no rationale provided)"
            final_text = decision_block(
                decision=decision.value,
                patient_id="",
                risk_assessment_id=None,
                rationale=rationale,
                override_reason=override_reason,
                trace_id=current_trace_id(),
                citations=_fetch_citations(flagged_medications) if flagged_medications else [],
                judgment=judge_response(client, model, query=user_input, rationale=rationale),
            )
            return final_text, messages


def _fail_closed_unavailable(reason: str, messages: list[dict]) -> tuple[str, list[dict]]:
    """
    The LLM API call could not even be attempted -- the circuit breaker is
    open, or the hard cost backstop was exceeded (docs/phase6/decisions.md
    H19, H20). Fails closed to REVIEW exactly like an incomplete risk
    check (H18): a query that couldn't be answered is never narrated as
    safe. No assistant turn is appended to messages -- none was produced,
    and fabricating one would mislead the next turn's history.
    """
    with start_span(
        "agent.submit_decision", _tracer, layer_attrs("agent.orchestration", "submit_decision")
    ) as decision_span:
        safe_set_attributes(decision_span, {
            "decision": AgentDecision.REVIEW.value,
            "override_reason": reason,
        })

    final_text = decision_block(
        decision=AgentDecision.REVIEW.value,
        patient_id="",
        risk_assessment_id=None,
        rationale="The clinical assistant could not reach the LLM API for this request.",
        override_reason=reason,
        trace_id=current_trace_id(),
    )
    return final_text, messages


def _fetch_citations(flagged_medications: list[dict]) -> list[dict]:
    """
    Post-decision knowledge-base lookup (docs/phase6/decisions.md H15):
    called only from the two places in run_query where a decision is
    already final -- never as an input the model reasons over. Best-effort
    -- any lookup failure already returns None/[] from knowledge.py itself,
    so this never raises and never blocks the decision it's attached to.
    """
    citations = []
    with start_span(
        "agent.fetch_citations", _tracer, layer_attrs("agent.knowledge", "fetch_citations")
    ) as span:
        for med in flagged_medications:
            display = med.get("display", "")
            rxnorm_code = med.get("rxnorm_code", "")
            label = fetch_drug_label_citation(extract_generic_name(display)) if display else None
            drug_classes = fetch_drug_class(rxnorm_code) if rxnorm_code else []
            if label or drug_classes:
                citations.append({
                    "drug": display or rxnorm_code,
                    "label": label,
                    "drug_classes": drug_classes,
                })
        safe_set_attributes(span, {
            "knowledge.found": bool(citations),
            "knowledge.source": "openFDA + RxClass" if citations else None,
        })
    return citations


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

def _resolve_provider() -> ResolvedProvider:
    """
    Validate required environment variables and resolve the LLM provider.
    Ollama is the default when LLM_PROVIDER is unset (docs/phase6/
    decisions.md H45) -- self-hosted, free, PHI stays on this host. See
    agent_platform.providers.build_llm_client for the full env var
    contract, including the DEPLOYMENT_ENV=production guardrail (H47).
    """
    fhir_url = os.environ.get("FHIR_GATEWAY_URL", "")
    if not fhir_url:
        print(error_block(
            "FHIR_GATEWAY_URL is not set.\n"
            "  export FHIR_GATEWAY_URL=http://localhost:8000/fhir"
        ))
        sys.exit(1)

    try:
        return build_llm_client()
    except RuntimeError as exc:
        print(error_block(str(exc)))
        sys.exit(1)


def _maybe_print_disclosure(resolved: ResolvedProvider) -> None:
    """
    Disclose, never silently substitute (docs/phase6/decisions.md H46):
    only prints when the self-hosted default was actually used (not an
    explicit choice) and a human is plausibly reading this -- sys.stdin's
    TTY-ness is used *only* to decide whether to show this message, never
    to change which model gets used. A test harness/automated caller
    (stdin not a TTY) sees nothing extra. The HTTP transport has no TTY
    concept at all and doesn't get this disclosure -- a documented
    limitation (docs/phase6/decisions.md H46), not a safety gap: the
    underlying default-selection rule doesn't depend on this signal.
    """
    if resolved.is_default and sys.stdin.isatty():
        print(error_block(
            "Using self-hosted Llama (free -- no data leaves this host) since no "
            "LLM_PROVIDER was set. For stronger reasoning, explicitly opt into a "
            "third-party model: --provider anthropic --model claude-sonnet-4-5 "
            "(requires ANTHROPIC_API_KEY) -- data would then leave this host. "
            "Run --list-models to see what's actually available first."
        ))


def interactive_mode(resolved: ResolvedProvider, session_id: str | None = None) -> None:
    """
    Run the agent in interactive REPL mode.

    If session_id is given, resumes that session from the Postgres session
    store (docs/phase6/design.md Section 4.3, decisions.md H12) -- using
    THAT session's own pinned provider/model (H49), not `resolved`, which
    is only the freshly-resolved default/choice for a *new* session. If
    DATABASE_URL is set but no session_id is given, starts a new persisted
    session using `resolved`. If DATABASE_URL isn't set at all, falls back
    to a purely in-memory session -- the same zero-setup behavior this
    REPL always had, just without cross-process resume (mirrors
    claims-agent's own no-API-key deterministic fallback: degrade
    gracefully, don't crash). Context-budget compaction (H13) applies
    either way -- it only needs token_count threaded through in-memory
    turn to turn, not the DB.
    """
    print(welcome())

    client = resolved.client
    model = resolved.model
    gen_ai_system = resolved.gen_ai_system

    messages: list[dict] = []
    token_count = 0
    persisted = False

    if session_id:
        try:
            loaded = load_session(session_id)
            messages, token_count = loaded.messages, loaded.token_count
            persisted = True
            # A resumed session keeps using what it was created with (H49),
            # not today's default/CLI choice -- rebuild the client to match.
            # Whether that original choice was itself a default fallback
            # isn't persisted (only provider/model are, H49) -- so this
            # print is an unconditional disclosure instead of a TTY-gated
            # one; it's not trying to reconstruct that lost information.
            client = build_client_for(loaded.provider, loaded.model)
            model, gen_ai_system = loaded.model, loaded.provider
            print(f"(resumed session {session_id}, {len(messages)} prior message(s), "
                  f"provider={loaded.provider} model={loaded.model})")
        except Exception as exc:
            print(error_block(f"Could not resume session {session_id}: {exc}"))
            return
    else:
        # A fresh session (persisted or in-memory-only) -- resolved.is_default
        # accurately reflects whether this run fell back to the self-hosted
        # default, so the disclosure gate below is meaningful here.
        _maybe_print_disclosure(resolved)
        if os.environ.get("DATABASE_URL"):
            try:
                session_id = create_session(gen_ai_system, model)
                persisted = True
                print(f"(session {session_id}, provider={gen_ai_system} model={model})")
            except Exception as exc:
                print(error_block(f"Session store unavailable, continuing in-memory only: {exc}"))

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
        stats: dict = {}
        try:
            final_text, messages = run_query(
                client, user_input, messages, token_count=token_count, stats=stats,
                model=model, gen_ai_system=gen_ai_system,
            )
            print(final_text)
        except (anthropic.APIError, httpx.HTTPError) as exc:
            # A single call failure below M4's circuit breaker threshold --
            # print and continue the REPL rather than crashing it, for
            # any of the three provider identities (docs/phase6/decisions.md H4, H20).
            print(error_block(f"LLM API error: {exc}"))
            continue
        except Exception as exc:
            print(error_block(f"Unexpected error: {exc}"))
            raise

        token_count = stats.get("token_count", token_count)
        if persisted:
            try:
                save_session(session_id, messages, token_count)
            except Exception as exc:
                print(error_block(f"Failed to persist session: {exc}"))


def non_interactive_mode(resolved: ResolvedProvider, query: str, session_id: str | None = None) -> int:
    """
    Run a single query and exit. Returns exit code.

    session_id is optional -- omit it for the original stateless, ephemeral
    behavior; pass one to resume/continue a persisted session (docs/phase6/
    design.md Section 4.3), making a single-shot invocation usable as a real
    multi-turn conversation across separate process runs, e.g. from a test
    program issuing one query per invocation against the same session. As
    in interactive_mode, a resumed session uses its own pinned
    provider/model (H49), not `resolved`.
    """
    client = resolved.client
    model = resolved.model
    gen_ai_system = resolved.gen_ai_system

    messages: list[dict] = []
    token_count = 0
    persisted = False

    if session_id:
        try:
            loaded = load_session(session_id)
            messages, token_count = loaded.messages, loaded.token_count
            persisted = True
            client = build_client_for(loaded.provider, loaded.model)
            model, gen_ai_system = loaded.model, loaded.provider
        except Exception as exc:
            print(error_block(f"Could not resume session {session_id}: {exc}"))
            return 1
    else:
        _maybe_print_disclosure(resolved)

    print(f"\nQuery: {query}\n")
    stats: dict = {}
    try:
        final_text, messages = run_query(
            client, query, messages, token_count=token_count, stats=stats,
            model=model, gen_ai_system=gen_ai_system,
        )
        print(final_text)
        if persisted:
            save_session(session_id, messages, stats.get("token_count", token_count))
        return 0
    except (anthropic.APIError, httpx.HTTPError) as exc:
        print(error_block(f"LLM API error: {exc}"))
        return 1
    except Exception as exc:
        print(error_block(f"Unexpected error: {exc}"))
        return 1


def _print_model_list(provider: str) -> None:
    """
    Discovery (docs/phase6/decisions.md H48) -- opt-in only, called only
    when --list-models is explicitly passed. Succeeds or raises; no
    partial results, no silent fallback to the default.
    """
    if provider == "ollama":
        base_url = os.environ.get("LLM_BASE_URL", "") or None
        models = list_ollama_models(base_url) if base_url else list_ollama_models()
    elif provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("CLAUDE_API_KEY", "")
        if not api_key:
            print(error_block("ANTHROPIC_API_KEY is not set (CLAUDE_API_KEY is also accepted)."))
            sys.exit(1)
        models = list_anthropic_models(api_key)
    else:  # openai_compatible
        base_url = os.environ.get("LLM_BASE_URL", "")
        if not base_url:
            print(error_block(
                "LLM_BASE_URL is not set (required to list openai_compatible models)."
            ))
            sys.exit(1)
        models = list_openai_compatible_models(base_url, api_key=os.environ.get("LLM_API_KEY", ""))

    print(f"Available models for provider={provider!r}:")
    for name in models:
        print(f"  {name}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agentic Healthcare Platform — Clinical Assistant"
    )
    parser.add_argument(
        "--query", "-q",
        metavar="QUERY",
        help="Run a single query non-interactively and exit.",
    )
    parser.add_argument(
        "--session-id",
        metavar="SESSION_ID",
        help="Resume a persisted session (requires DATABASE_URL). "
             "Interactive mode starts a new session automatically when omitted "
             "and DATABASE_URL is set.",
    )
    parser.add_argument(
        "--provider",
        choices=["anthropic", "ollama", "openai_compatible"],
        help="Override LLM_PROVIDER for this run only (docs/phase6/decisions.md H4). "
             "An explicit choice here is never treated as the self-hosted default (H46).",
    )
    parser.add_argument(
        "--model",
        metavar="MODEL",
        help="Override LLM_MODEL for this run only.",
    )
    parser.add_argument(
        "--list-models",
        metavar="PROVIDER",
        choices=["anthropic", "ollama", "openai_compatible"],
        help="Query and print the models actually available for PROVIDER, then exit "
             "(docs/phase6/decisions.md H48) -- does not run a query.",
    )
    args = parser.parse_args()

    if args.list_models:
        _print_model_list(args.list_models)
        return

    # CLI flags take precedence over the environment for this single run
    # (a human explicitly choosing beats an ambient env var, same principle
    # as H46: explicit always wins over incidental).
    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    setup_tracing("mcp-agent")
    resolved = _resolve_provider()

    if args.query:
        sys.exit(non_interactive_mode(resolved, args.query, session_id=args.session_id))
    else:
        interactive_mode(resolved, session_id=args.session_id)


if __name__ == "__main__":
    main()
