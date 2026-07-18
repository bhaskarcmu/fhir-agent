"""
Unit tests for the tool-use loop and MCP<->Anthropic schema translation. The Anthropic
client and MCP ClientSession are both mocked here — no network, no API key needed. The
real end-to-end path (real Claude, real MCP server, real registry data) is exercised
separately by tests/test_groundedness_eval.py, which self-skips without a key/DB.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import mcp.types as mcp_types
import pytest

from provider_search_agent.agent import _anthropic_client, mcp_tools_to_anthropic_tools, run_query


def _tool_use_block(name: str, tool_input: dict, block_id: str = "toolu_1"):
    return SimpleNamespace(type="tool_use", name=name, input=tool_input, id=block_id)


def _text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def _response(stop_reason: str, content: list):
    return SimpleNamespace(stop_reason=stop_reason, content=content)


def test_mcp_tools_to_anthropic_tools_translates_inputschema_field_name():
    mcp_tools = [
        mcp_types.Tool(name="get_provider", description="fetch by NPI",
                        inputSchema={"type": "object", "required": ["npi"]}),
    ]
    result = mcp_tools_to_anthropic_tools(mcp_tools)
    assert result == [{
        "name": "get_provider", "description": "fetch by NPI",
        "input_schema": {"type": "object", "required": ["npi"]},
    }]


def test_mcp_tools_to_anthropic_tools_handles_missing_description():
    mcp_tools = [mcp_types.Tool(name="x", description=None, inputSchema={"type": "object"})]
    result = mcp_tools_to_anthropic_tools(mcp_tools)
    assert result[0]["description"] == ""


def test_anthropic_client_missing_key_raises(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY or CLAUDE_API_KEY"):
        _anthropic_client()


def test_anthropic_client_accepts_claude_api_key_fallback(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_API_KEY", "sk-test-fake")
    client = _anthropic_client()
    assert client is not None  # constructing the client doesn't validate the key


@pytest.mark.asyncio
async def test_run_query_single_tool_call_then_final_answer():
    anthropic_client = MagicMock()
    anthropic_client.messages.create.side_effect = [
        _response("tool_use", [_tool_use_block("get_provider", {"npi": "1234567890"})]),
        _response("end_turn", [_text_block("Dr. Doe, NPI 1234567890.")]),
    ]

    session = AsyncMock()
    session.call_tool.return_value = SimpleNamespace(
        isError=False, content=[SimpleNamespace(text='{"npi": "1234567890", "name": "Dr. Doe"}')],
    )

    result = await run_query("find NPI 1234567890", session, anthropic_client, [], verbose=False)

    assert result == "Dr. Doe, NPI 1234567890."
    session.call_tool.assert_awaited_once_with("get_provider", {"npi": "1234567890"})


@pytest.mark.asyncio
async def test_run_query_propagates_mcp_error_flag_as_is_error():
    anthropic_client = MagicMock()
    anthropic_client.messages.create.side_effect = [
        _response("tool_use", [_tool_use_block("get_provider", {"npi": "9999999999"})]),
        _response("end_turn", [_text_block("That NPI was not found.")]),
    ]

    session = AsyncMock()
    session.call_tool.return_value = SimpleNamespace(
        isError=True, content=[SimpleNamespace(text='{"error_type": "not_found"}')],
    )

    await run_query("find NPI 9999999999", session, anthropic_client, [], verbose=False)

    # The second messages.create call's tool_result content must carry is_error=True,
    # so Claude sees the failure signal rather than a plain success-shaped body.
    second_call_messages = anthropic_client.messages.create.call_args_list[1].kwargs["messages"]
    tool_result = second_call_messages[-1]["content"][0]
    assert tool_result["is_error"] is True


@pytest.mark.asyncio
async def test_run_query_no_tool_call_returns_text_directly():
    anthropic_client = MagicMock()
    anthropic_client.messages.create.return_value = _response(
        "end_turn", [_text_block("Please clarify the specialty you need.")],
    )
    session = AsyncMock()

    result = await run_query("find me a doctor", session, anthropic_client, [], verbose=False)

    assert result == "Please clarify the specialty you need."
    session.call_tool.assert_not_awaited()
