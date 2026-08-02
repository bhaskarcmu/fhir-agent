"""
Unit tests for agent_platform.providers (docs/phase6/decisions.md H4,
milestone-plan.md M5): the conversation-history/tool-schema translation
between our internal Anthropic-shaped messages and the OpenAI
chat-completions shape, and the LLM_PROVIDER/LLM_MODEL/LLM_BASE_URL env
var contract. No network -- see mcp-agent/tests/test_provider_integration.py
for the live Ollama test that exercises this through the real agent loop.

Run:
  python3 -m pytest agent-platform/tests/test_providers.py -v
"""

from __future__ import annotations

import pytest

from agent_platform.providers import (
    OpenAICompatibleProvider,
    TextBlock,
    ToolUseBlock,
    _from_openai_response,
    _to_openai_messages,
    _to_openai_tools,
    build_llm_client,
)


# ── Outbound: our messages/tools -> OpenAI shape ────────────────────────

def test_plain_string_user_turn_passes_through():
    result = _to_openai_messages("sys", [{"role": "user", "content": "hi"}])
    assert result == [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]


def test_assistant_text_block_becomes_plain_content():
    messages = [{"role": "assistant", "content": [TextBlock(text="hello")]}]
    result = _to_openai_messages("sys", messages)
    assert result[1] == {"role": "assistant", "content": "hello"}


def test_assistant_tool_use_block_becomes_a_tool_call():
    messages = [{"role": "assistant", "content": [
        ToolUseBlock(id="t1", name="assess_refill_risk", input={"patient_id": "p1"})
    ]}]
    result = _to_openai_messages("sys", messages)
    assistant_msg = result[1]
    assert assistant_msg["content"] is None
    assert assistant_msg["tool_calls"] == [{
        "id": "t1",
        "type": "function",
        "function": {"name": "assess_refill_risk", "arguments": '{"patient_id": "p1"}'},
    }]


def test_assistant_block_as_plain_dict_works_the_same_as_a_dataclass():
    """Round-tripped through the session store, blocks become plain dicts (docs/phase6/decisions.md H28)."""
    messages = [{"role": "assistant", "content": [
        {"type": "tool_use", "id": "t1", "name": "assess_refill_risk", "input": {"patient_id": "p1"}}
    ]}]
    result = _to_openai_messages("sys", messages)
    assert result[1]["tool_calls"][0]["function"]["name"] == "assess_refill_risk"


def test_tool_result_turn_becomes_a_separate_tool_role_message_per_result():
    messages = [{"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": "result-1"},
        {"type": "tool_result", "tool_use_id": "t2", "content": "result-2"},
    ]}]
    result = _to_openai_messages("sys", messages)
    assert result[1] == {"role": "tool", "tool_call_id": "t1", "content": "result-1"}
    assert result[2] == {"role": "tool", "tool_call_id": "t2", "content": "result-2"}


def test_tool_definitions_translate_to_openai_function_shape():
    tools = [{
        "name": "get_patient_summary",
        "description": "find a patient",
        "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    }]
    result = _to_openai_tools(tools)
    assert result == [{
        "type": "function",
        "function": {
            "name": "get_patient_summary",
            "description": "find a patient",
            "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        },
    }]


# ── Inbound: OpenAI response -> our normalized shape ────────────────────

def test_tool_calls_response_maps_to_tool_use_stop_reason():
    data = {
        "choices": [{
            "finish_reason": "tool_calls",
            "message": {"tool_calls": [{"id": "c1", "function": {"name": "submit_decision", "arguments": '{"decision": "REVIEW"}'}}]},
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    resp = _from_openai_response(data)
    assert resp.stop_reason == "tool_use"
    assert resp.content == [ToolUseBlock(id="c1", name="submit_decision", input={"decision": "REVIEW"})]
    assert resp.usage.input_tokens == 10
    assert resp.usage.output_tokens == 5


def test_plain_text_response_maps_to_end_turn():
    data = {"choices": [{"finish_reason": "stop", "message": {"content": "All good."}}]}
    resp = _from_openai_response(data)
    assert resp.stop_reason == "end_turn"
    assert resp.content == [TextBlock(text="All good.")]


def test_malformed_tool_call_arguments_fail_closed_to_empty_input_not_a_crash():
    """
    A genuinely weak model producing invalid JSON in tool-call arguments
    (decisions.md H11) must not crash the translation layer -- it falls
    back to an empty input, the same fail-closed-on-malformed-input
    discipline M1's enum gate already applies downstream.
    """
    data = {
        "choices": [{
            "finish_reason": "tool_calls",
            "message": {"tool_calls": [{"id": "c1", "function": {"name": "submit_decision", "arguments": "not valid json"}}]},
        }],
    }
    resp = _from_openai_response(data)
    assert resp.content[0].input == {}


def test_missing_usage_is_handled_gracefully():
    data = {"choices": [{"finish_reason": "stop", "message": {"content": "hi"}}]}
    resp = _from_openai_response(data)
    assert resp.usage.input_tokens is None
    assert resp.usage.output_tokens is None


# ── build_llm_client() env var contract ──────────────────────────────────

def test_defaults_to_anthropic_when_llm_provider_is_unset(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    _client, model, system = build_llm_client()
    assert system == "anthropic"
    assert model == "claude-sonnet-4-5"


def test_llm_model_overrides_the_anthropic_default(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_MODEL", "claude-opus-4")
    _client, model, _system = build_llm_client()
    assert model == "claude-opus-4"


def test_anthropic_requires_an_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        build_llm_client()


def test_openai_compatible_requires_base_url(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="LLM_BASE_URL"):
        build_llm_client()


def test_openai_compatible_requires_a_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="LLM_MODEL"):
        build_llm_client()


def test_openai_compatible_builds_the_provider_when_fully_configured(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("LLM_MODEL", "llama3.2:1b")
    client, model, system = build_llm_client()
    assert isinstance(client, OpenAICompatibleProvider)
    assert model == "llama3.2:1b"
    assert system == "openai_compatible"


def test_unrecognized_provider_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "something_else")
    with pytest.raises(RuntimeError, match="Unrecognized LLM_PROVIDER"):
        build_llm_client()
