"""
Provider abstraction for the one LLM API call every agent turn makes
(docs/phase6/design.md Section 4.5, decisions.md H4). Exactly two
adapters, never more: Anthropic (native) and one OpenAI-compatible
adapter covering Llama, DeepSeek, Ollama, vLLM, and hosted
OpenAI-compatible endpoints (DeepSeek API, OpenRouter, Groq). Model
choice becomes a config value (LLM_PROVIDER/LLM_MODEL/LLM_BASE_URL/
LLM_API_KEY), never a code branch.

The real Anthropic client needs no wrapper here: anthropic.Anthropic
already exposes exactly the surface run_query calls --
client.messages.create(model=..., max_tokens=..., system=..., tools=...,
messages=...) -> a response with .stop_reason, .content (blocks with
.type/.text/.name/.input/.id), .usage.input_tokens/output_tokens.
OpenAICompatibleProvider below duck-types that same surface so
run_query, agent.py, and every existing test's fake client need zero
changes to use either provider interchangeably (the same additive-only
discipline as H31).

Anthropic remains the only *live* backend in production even after this
ships (H4) -- LLM_PROVIDER defaults to "anthropic" and the
OpenAI-compatible seam only activates when explicitly requested. It
exists to prove PHI-off-third-party is achievable when that becomes an
active business rule, and to let M1's local-LLM adversarial testing
(decisions.md H11) run through the real agent loop instead of talking to
Ollama directly the way it did before this module existed.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import anthropic
import httpx


@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict
    type: str = "tool_use"


@dataclass
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass
class NormalizedResponse:
    """Shaped identically to an anthropic.Anthropic response -- see module docstring."""

    stop_reason: str
    content: list = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)


def _block_get(block, key: str, default=None):
    """A content block may be an SDK object, one of our own dataclasses above
    (fresh from this provider), or a plain dict (round-tripped through the
    session store) -- read a field regardless of which."""
    if isinstance(block, dict):
        return block.get(key, default)
    return getattr(block, key, default)


def _to_openai_messages(system: str, messages: list) -> list[dict]:
    """
    Translate our internal Anthropic-shaped messages list into the OpenAI
    chat-completions shape. The three internal shapes agent.py actually
    produces: a plain-string user turn, an assistant turn (list of
    text/tool_use blocks), and a tool-result turn (list of tool_result
    dicts, role "user" in our shape) -- OpenAI wants each tool result as
    its own separate "tool"-role message, not bundled into one user turn.
    """
    openai_messages: list[dict] = [{"role": "system", "content": system}]

    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if isinstance(content, str):
            openai_messages.append({"role": role, "content": content})
            continue

        if role == "assistant":
            text_parts = []
            tool_calls = []
            for block in content:
                block_type = _block_get(block, "type")
                if block_type == "text":
                    text_parts.append(_block_get(block, "text") or "")
                elif block_type == "tool_use":
                    tool_calls.append({
                        "id": _block_get(block, "id"),
                        "type": "function",
                        "function": {
                            "name": _block_get(block, "name"),
                            "arguments": json.dumps(_block_get(block, "input") or {}),
                        },
                    })
            assistant_message: dict = {"role": "assistant", "content": "\n".join(text_parts) or None}
            if tool_calls:
                assistant_message["tool_calls"] = tool_calls
            openai_messages.append(assistant_message)
            continue

        # role == "user" with list content -- our own tool_result dicts.
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                openai_messages.append({
                    "role": "tool",
                    "tool_call_id": block.get("tool_use_id"),
                    "content": block.get("content", ""),
                })
            else:
                # Not a shape we produce ourselves -- pass through as text
                # rather than raising; never crash on an unexpected shape.
                openai_messages.append({"role": "user", "content": json.dumps(block)})

    return openai_messages


def _to_openai_tools(tools: list[dict]) -> list[dict]:
    """Anthropic's {name, description, input_schema} -> OpenAI's {type: function, function: {...}}."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for tool in tools
    ]


def _from_openai_response(data: dict) -> NormalizedResponse:
    """
    Translate an OpenAI chat-completions response into our normalized
    shape. Tool-call argument JSON that fails to parse (a real thing weak
    local models produce, decisions.md H11) falls back to an empty input
    rather than raising -- the same fail-closed-on-malformed-input
    discipline M1's enum gate already applies downstream.
    """
    choice = data["choices"][0]
    message = choice.get("message", {})
    finish_reason = choice.get("finish_reason", "stop")

    content: list = []
    text = message.get("content")
    if text:
        content.append(TextBlock(text=text))

    for tool_call in message.get("tool_calls") or []:
        function = tool_call.get("function", {})
        raw_arguments = function.get("arguments") or "{}"
        try:
            parsed_input = json.loads(raw_arguments)
        except json.JSONDecodeError:
            parsed_input = {}
        content.append(ToolUseBlock(
            id=tool_call.get("id", ""),
            name=function.get("name", ""),
            input=parsed_input,
        ))

    stop_reason = "tool_use" if finish_reason == "tool_calls" else "end_turn"

    usage_data = data.get("usage") or {}
    usage = Usage(
        input_tokens=usage_data.get("prompt_tokens"),
        output_tokens=usage_data.get("completion_tokens"),
    )

    return NormalizedResponse(stop_reason=stop_reason, content=content, usage=usage)


class OpenAICompatibleProvider:
    """
    Duck-types anthropic.Anthropic's minimal surface
    (client.messages.create(**kwargs)) so run_query needs zero changes to
    use this interchangeably with a real Anthropic client. Talks to any
    server implementing the OpenAI chat-completions REST shape: Ollama,
    vLLM, DeepSeek API, OpenRouter, Groq, hosted OpenAI-compatible
    endpoints.

    Raises plain httpx errors on failure (HTTPStatusError, ConnectError,
    TimeoutException, ...) -- agent_platform.resilience's circuit breaker
    treats httpx.HTTPError as a tripping failure for exactly this reason
    (docs/phase6/decisions.md H4), so M4's protections cover this provider
    the same as the native Anthropic one.
    """

    def __init__(self, base_url: str, api_key: str = ""):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    @property
    def messages(self) -> "OpenAICompatibleProvider":
        return self

    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        tools: list[dict] | None = None,
        messages: list[dict] | None = None,
        **_ignored,
    ) -> NormalizedResponse:
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        payload: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": _to_openai_messages(system, messages or []),
        }
        if tools:
            payload["tools"] = _to_openai_tools(tools)

        response = httpx.post(
            f"{self._base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=60.0,
        )
        response.raise_for_status()
        return _from_openai_response(response.json())


def build_llm_client() -> tuple[object, str, str]:
    """
    Resolve LLM_PROVIDER/LLM_MODEL/LLM_BASE_URL/LLM_API_KEY into a
    (client, model, gen_ai_system) triple. Anthropic is the default and
    only *live* production backend (H4) -- the OpenAI-compatible seam
    activates only when LLM_PROVIDER is explicitly set to
    "openai_compatible". Raises RuntimeError on misconfiguration (mirrors
    session_store.py's DATABASE_URL contract) -- callers decide whether
    that means sys.exit (the CLI) or a 503 (the HTTP transport).

    gen_ai_system is returned explicitly rather than left for a caller to
    infer via isinstance(client, ...) -- every existing test in this repo
    exercises run_query with a duck-typed fake client, not a real
    anthropic.Anthropic instance, so type-based detection would call
    every one of them "openai_compatible". Explicit is simpler and
    correct for both real and faked clients.
    """
    provider = os.environ.get("LLM_PROVIDER", "anthropic").strip().lower()

    if provider == "openai_compatible":
        base_url = os.environ.get("LLM_BASE_URL", "")
        if not base_url:
            raise RuntimeError(
                "LLM_BASE_URL is not set (required when LLM_PROVIDER=openai_compatible). "
                "e.g. export LLM_BASE_URL=http://localhost:11434/v1 for a local Ollama."
            )
        model = os.environ.get("LLM_MODEL", "")
        if not model:
            raise RuntimeError(
                "LLM_MODEL is not set (required when LLM_PROVIDER=openai_compatible). "
                "e.g. export LLM_MODEL=llama3.2:1b"
            )
        client = OpenAICompatibleProvider(base_url=base_url, api_key=os.environ.get("LLM_API_KEY", ""))
        return client, model, "openai_compatible"

    if provider != "anthropic":
        raise RuntimeError(
            f"Unrecognized LLM_PROVIDER={provider!r} -- expected 'anthropic' or 'openai_compatible'."
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("CLAUDE_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set (CLAUDE_API_KEY is also accepted).")
    client = anthropic.Anthropic(api_key=api_key)
    return client, os.environ.get("LLM_MODEL", "claude-sonnet-4-5"), "anthropic"
