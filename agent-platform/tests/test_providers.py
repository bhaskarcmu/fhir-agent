"""
Unit tests for agent_platform.providers (docs/phase6/decisions.md H4,
superseded by H45-H49; milestone-plan.md M5): the conversation-history/
tool-schema translation between our internal Anthropic-shaped messages
and the OpenAI chat-completions shape, and the
LLM_PROVIDER/LLM_MODEL/LLM_BASE_URL/DEPLOYMENT_ENV env var contract for
all three provider identities (anthropic, ollama, openai_compatible). No
network -- see mcp-agent/tests/test_provider_integration.py for the live
Ollama test that exercises this through the real agent loop.

Run:
  python3 -m pytest agent-platform/tests/test_providers.py -v
"""

from __future__ import annotations

import pytest

from agent_platform.providers import (
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_MODEL,
    OpenAICompatibleProvider,
    ResolvedProvider,
    TextBlock,
    ToolUseBlock,
    _from_openai_response,
    _to_openai_messages,
    _to_openai_tools,
    build_client_for,
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


# ── build_llm_client() env var contract (docs/phase6/decisions.md H45-H47) ──

def _clear_llm_env(monkeypatch):
    for var in ("LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY",
                "ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "DEPLOYMENT_ENV"):
        monkeypatch.delenv(var, raising=False)


def test_defaults_to_ollama_when_llm_provider_is_unset(monkeypatch):
    """H45: the default flipped -- self-hosted, not Anthropic -- even with no key at all."""
    _clear_llm_env(monkeypatch)
    resolved = build_llm_client()
    assert resolved.gen_ai_system == "ollama"
    assert resolved.model == DEFAULT_OLLAMA_MODEL
    assert isinstance(resolved.client, OpenAICompatibleProvider)
    assert resolved.is_default is True


def test_a_present_anthropic_key_does_not_override_the_ollama_default(monkeypatch):
    """
    H46: presence of a paid key alone is not a choice. Only an explicit
    LLM_PROVIDER is -- a key can be present for all sorts of incidental
    reasons (a leftover .env, a shared devcontainer image).
    """
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    resolved = build_llm_client()
    assert resolved.gen_ai_system == "ollama"
    assert resolved.is_default is True


def test_explicit_llm_provider_ollama_is_not_flagged_as_default(monkeypatch):
    """is_default distinguishes "fell back" from "chose ollama on purpose"."""
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    resolved = build_llm_client()
    assert resolved.gen_ai_system == "ollama"
    assert resolved.is_default is False


def test_llm_base_url_and_model_override_the_ollama_defaults(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_BASE_URL", "http://remote-ollama:11434/v1")
    monkeypatch.setenv("LLM_MODEL", "llama3.2:3b")
    resolved = build_llm_client()
    assert resolved.model == "llama3.2:3b"
    assert resolved.client._base_url == "http://remote-ollama:11434/v1"


def test_explicit_llm_provider_anthropic_requires_an_api_key(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        build_llm_client()


def test_explicit_llm_provider_anthropic_with_a_key_works(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    resolved = build_llm_client()
    assert resolved.gen_ai_system == "anthropic"
    assert resolved.model == "claude-sonnet-4-5"
    assert resolved.is_default is False


def test_llm_model_overrides_the_anthropic_default(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_MODEL", "claude-opus-4")
    resolved = build_llm_client()
    assert resolved.model == "claude-opus-4"


def test_openai_compatible_requires_base_url(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    with pytest.raises(RuntimeError, match="LLM_BASE_URL"):
        build_llm_client()


def test_openai_compatible_requires_a_model(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    with pytest.raises(RuntimeError, match="LLM_MODEL"):
        build_llm_client()


def test_openai_compatible_builds_the_provider_when_fully_configured(monkeypatch):
    """openai_compatible has no safe generic default -- unlike ollama, both must be explicit."""
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("LLM_MODEL", "deepseek-chat")
    resolved = build_llm_client()
    assert isinstance(resolved.client, OpenAICompatibleProvider)
    assert resolved.model == "deepseek-chat"
    assert resolved.gen_ai_system == "openai_compatible"
    assert resolved.is_default is False


def test_unrecognized_provider_raises(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "something_else")
    with pytest.raises(RuntimeError, match="Unrecognized LLM_PROVIDER"):
        build_llm_client()


# ── DEPLOYMENT_ENV=production guardrail (docs/phase6/decisions.md H47) ──

def test_production_with_no_explicit_provider_refuses_to_default(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("DEPLOYMENT_ENV", "production")
    with pytest.raises(RuntimeError, match="DEPLOYMENT_ENV=production"):
        build_llm_client()


def test_production_with_an_explicit_provider_is_fine(monkeypatch):
    """The guardrail only fires on the *absent* case -- an explicit choice is always respected."""
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("DEPLOYMENT_ENV", "production")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    resolved = build_llm_client()
    assert resolved.gen_ai_system == "anthropic"


def test_non_production_deployment_env_does_not_trigger_the_guardrail(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("DEPLOYMENT_ENV", "development")
    resolved = build_llm_client()
    assert resolved.gen_ai_system == "ollama"


# ── build_client_for() -- resuming a session with its own pinned choice ──

def test_build_client_for_rebuilds_the_pinned_provider_regardless_of_current_default(monkeypatch):
    """
    H49: a session pinned to "anthropic" must resume as anthropic even if
    this process's current environment would otherwise default to ollama.
    """
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    client = build_client_for("anthropic", "claude-sonnet-4-5")
    assert not isinstance(client, OpenAICompatibleProvider)


def test_build_client_for_ollama_uses_current_infra_config(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_BASE_URL", "http://remote-ollama:11434/v1")
    client = build_client_for("ollama", "llama3.2:1b")
    assert client._base_url == "http://remote-ollama:11434/v1"


def test_build_client_for_unknown_provider_raises(monkeypatch):
    with pytest.raises(RuntimeError, match="Unknown provider"):
        build_client_for("not_a_real_provider", "some-model")


# ── Discovery (docs/phase6/decisions.md H48) -- opt-in, no network here ──
# Only the plumbing/parsing is unit-tested (mocked HTTP); the live,
# real-Ollama discovery path is exercised in
# mcp-agent/tests/test_provider_integration.py.

def test_list_ollama_models_parses_the_tags_response(monkeypatch):
    import httpx

    from agent_platform import providers

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"models": [{"name": "llama3.2:1b"}, {"name": "deepseek-r1:1.5b"}]}

    def _fake_get(url, **kwargs):
        assert url == f"{DEFAULT_OLLAMA_BASE_URL.removesuffix('/v1')}/api/tags"
        return _FakeResponse()

    monkeypatch.setattr(httpx, "get", _fake_get)
    assert providers.list_ollama_models() == ["llama3.2:1b", "deepseek-r1:1.5b"]


def test_list_ollama_models_propagates_a_real_failure_rather_than_swallowing_it(monkeypatch):
    """H48: discovery either succeeds or raises -- no silent empty-list fallback."""
    import httpx

    from agent_platform import providers

    def _fake_get(url, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "get", _fake_get)
    with pytest.raises(httpx.ConnectError):
        providers.list_ollama_models()


def test_list_openai_compatible_models_parses_the_v1_models_response(monkeypatch):
    import httpx

    from agent_platform import providers

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"id": "deepseek-chat"}, {"id": "deepseek-reasoner"}]}

    monkeypatch.setattr(httpx, "get", lambda url, **kwargs: _FakeResponse())
    result = providers.list_openai_compatible_models("https://api.deepseek.com/v1", api_key="sk-x")
    assert result == ["deepseek-chat", "deepseek-reasoner"]
