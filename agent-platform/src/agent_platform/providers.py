"""
Provider abstraction for the one LLM API call every agent turn makes
(docs/phase6/design.md Section 4.5, decisions.md H4, superseded by H45).

Three provider *identities*, two adapter *implementations*:
  - "anthropic"         -- Anthropic native. Third-party-hosted.
  - "ollama"             -- a local, self-hosted Ollama instance. The only
                            identity eligible to be selected automatically
                            when nothing is configured (H45-H47).
  - "openai_compatible" -- any OTHER OpenAI-chat-completions-shaped
                            endpoint: DeepSeek API, OpenRouter, Groq, a
                            self-hosted vLLM box, etc. Third-party-hosted
                            by convention here (a self-hosted vLLM user
                            gets the same safety property "openai_compatible"
                            already had -- explicit opt-in required -- just
                            without automatic default-eligibility; see H45).

"ollama" and "openai_compatible" share one adapter implementation
(OpenAICompatibleProvider below) -- Ollama speaks the same wire protocol,
so no separate translation code is needed. The identity split exists
purely to answer one question safely: *who hosts the inference*. That
is the property that actually matters for keeping PHI off a third party
(H45), not which wire protocol is spoken.

The real Anthropic client needs no wrapper here: anthropic.Anthropic
already exposes exactly the surface run_query calls --
client.messages.create(model=..., max_tokens=..., system=..., tools=...,
messages=...) -> a response with .stop_reason, .content (blocks with
.type/.text/.name/.input/.id), .usage.input_tokens/output_tokens.
OpenAICompatibleProvider below duck-types that same surface so
run_query, agent.py, and every existing test's fake client need zero
changes to use any of the three identities interchangeably (the same
additive-only discipline as H31).

**The default flipped (H45, superseding H4's "Anthropic is the only
live backend"):** with no explicit LLM_PROVIDER set, build_llm_client()
now resolves to "ollama" -- self-hosted, free, and (the primary
rationale, not a side effect) PHI never leaves this host. Presence of a
paid API key is *not* enough to select a paid/third-party provider --
only an explicit LLM_PROVIDER does that (H46) -- because a key's mere
presence is an easily-accidental signal (a leftover .env, a shared
devcontainer image), while an explicit LLM_PROVIDER is a deliberate one.
This default is disclosed, never silently substituted -- see agent.py's
TTY-gated disclosure and docs/phase6/decisions.md H46.

**Production is not "the vacuum" (H47):** DEPLOYMENT_ENV=production
makes an unset LLM_PROVIDER a loud error instead of a silent Llama
fallback -- a minimal guardrail pending the fuller environment-tier
design deferred to M7 ("Strong Model in Production," not yet built).

list_models() below is the discovery seam a human or a test script can
use to see what is actually available before choosing -- opt-in only,
never called unless something explicitly asks; it either succeeds or
raises, no partial/best-effort degradation (docs/phase6/decisions.md
H48).
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


DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-5"
# Self-hosted, zero-required-config identity -- these two defaults are
# why LLM_PROVIDER=ollama needs nothing else set to work, unlike
# "openai_compatible" which requires an explicit LLM_BASE_URL/LLM_MODEL
# (there's no safe generic default for an arbitrary third-party endpoint).
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"
DEFAULT_OLLAMA_MODEL = "llama3.2:1b"

_VALID_PROVIDERS = ("anthropic", "ollama", "openai_compatible")


@dataclass
class ResolvedProvider:
    """
    What build_llm_client() resolves LLM_PROVIDER (or its absence) into.
    A small dataclass rather than a growing bare tuple -- it was already
    an awkward 3-tuple before is_default existed.

    client:         anthropic.Anthropic or OpenAICompatibleProvider.
    model:          resolved model name.
    gen_ai_system:  "anthropic" | "ollama" | "openai_compatible" -- for
                    telemetry (fhir_agent's gen_ai.system attribute).
                    Explicit, never inferred via isinstance(): every
                    existing test in this repo exercises run_query with a
                    duck-typed fake client, not a real SDK instance, so
                    type-based detection would mislabel all of them.
    is_default:     True only when LLM_PROVIDER was unset and this is the
                    Ollama fallback (H46) -- False for every explicit
                    choice, including an explicit LLM_PROVIDER=ollama.
                    Callers use this to decide whether to show the
                    cost/privacy disclosure (agent.py) -- never to change
                    behavior itself.
    """

    client: object
    model: str
    gen_ai_system: str
    is_default: bool = False


def _construct_client(provider: str) -> object:
    """
    Build the actual client object for an already-decided provider
    identity, reading only infrastructure-level config (base URL, API
    key) from the current environment -- never a per-session secret,
    since nothing session-scoped is persisted here (docs/phase6/
    decisions.md H49: only provider/model are persisted per session,
    deliberately not base_url/api_key).
    """
    if provider == "ollama":
        base_url = os.environ.get("LLM_BASE_URL", DEFAULT_OLLAMA_BASE_URL)
        return OpenAICompatibleProvider(base_url=base_url, api_key=os.environ.get("LLM_API_KEY", ""))

    if provider == "openai_compatible":
        base_url = os.environ.get("LLM_BASE_URL", "")
        if not base_url:
            raise RuntimeError(
                "LLM_BASE_URL is not set (required when LLM_PROVIDER=openai_compatible -- "
                "there's no safe generic default for an arbitrary third-party endpoint). "
                "e.g. export LLM_BASE_URL=https://api.deepseek.com/v1"
            )
        return OpenAICompatibleProvider(base_url=base_url, api_key=os.environ.get("LLM_API_KEY", ""))

    # provider == "anthropic"
    api_key = os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("CLAUDE_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set (CLAUDE_API_KEY is also accepted).")
    return anthropic.Anthropic(api_key=api_key)


def build_llm_client() -> ResolvedProvider:
    """
    Resolve LLM_PROVIDER/LLM_MODEL/LLM_BASE_URL/LLM_API_KEY (and
    DEPLOYMENT_ENV) into a ResolvedProvider for a *new* session/process --
    i.e. this is the "nothing has been decided yet" entry point. To
    rebuild the client for an *existing* session's already-pinned
    provider/model, use build_client_for() instead (docs/phase6/
    decisions.md H49) -- model choice is a per-session decision, so a
    resumed session must keep using what it was created with, not
    silently pick up today's default or this process's own config.

    Raises RuntimeError on misconfiguration (mirrors session_store.py's
    DATABASE_URL contract) -- callers decide whether that means sys.exit
    (the CLI) or a 503 (the HTTP transport).

    With LLM_PROVIDER unset, resolves to "ollama" (H45) -- self-hosted,
    free, and (the actual point) PHI never leaves this host. A paid key
    being present is not enough on its own to select a paid provider
    (H46); DEPLOYMENT_ENV=production makes the unset case a loud error
    instead, since production is never allowed to be "the vacuum" (H47).
    """
    provider = os.environ.get("LLM_PROVIDER", "").strip().lower()
    explicit = bool(provider)

    if not explicit:
        if os.environ.get("DEPLOYMENT_ENV", "").strip().lower() == "production":
            raise RuntimeError(
                "DEPLOYMENT_ENV=production but LLM_PROVIDER is not set. Production "
                "deployments must explicitly choose a provider -- refusing to silently "
                "fall back to the self-hosted Ollama default in a production environment "
                "(docs/phase6/decisions.md H47). Set LLM_PROVIDER=anthropic (or "
                "whichever provider this deployment is meant to run) explicitly."
            )
        provider = "ollama"

    if provider not in _VALID_PROVIDERS:
        raise RuntimeError(
            f"Unrecognized LLM_PROVIDER={provider!r} -- expected one of {_VALID_PROVIDERS}."
        )

    # Construct the client first -- it validates base_url/API-key
    # prerequisites, which should surface before a missing-model error
    # when both are absent (openai_compatible requires both explicitly).
    client = _construct_client(provider)

    if provider == "ollama":
        model = os.environ.get("LLM_MODEL", DEFAULT_OLLAMA_MODEL)
    elif provider == "openai_compatible":
        model = os.environ.get("LLM_MODEL", "")
        if not model:
            raise RuntimeError(
                "LLM_MODEL is not set (required when LLM_PROVIDER=openai_compatible). "
                "e.g. export LLM_MODEL=deepseek-chat"
            )
    else:
        model = os.environ.get("LLM_MODEL", DEFAULT_ANTHROPIC_MODEL)

    return ResolvedProvider(client, model, provider, is_default=not explicit)


def build_client_for(provider: str, model: str) -> object:
    """
    Rebuild just the client object for an already-decided (provider,
    model) pair -- used to resume an existing session with the exact
    provider it was pinned to at creation (docs/phase6/decisions.md H49),
    regardless of what LLM_PROVIDER this process would otherwise default
    or resolve to right now. Infrastructure-level config (base URL, API
    key) still comes from the current environment -- see
    _construct_client()'s docstring on why that's not a session-persisted
    value. Raises RuntimeError the same way build_llm_client() does if
    that infrastructure config is missing (e.g. no ANTHROPIC_API_KEY, but
    the session was pinned to "anthropic").
    """
    if provider not in _VALID_PROVIDERS:
        raise RuntimeError(f"Unknown provider {provider!r} recorded for this session.")
    return _construct_client(provider)


# ── Discovery (docs/phase6/decisions.md H48) ─────────────────────────────
# Opt-in only -- nothing above calls these. A human (--list-models) or a
# test script calls one of these explicitly; it either returns a real
# list or raises. No partial results, no silent fallback to the default:
# discovery failing means "can't list options," full stop.

def list_anthropic_models(api_key: str) -> list[str]:
    client = anthropic.Anthropic(api_key=api_key)
    return [m.id for m in client.models.list()]


def list_ollama_models(base_url: str = DEFAULT_OLLAMA_BASE_URL) -> list[str]:
    # Ollama's own /api/tags, not /v1/models -- the OpenAI-compatible
    # surface Ollama exposes doesn't include a models-list endpoint with
    # local model names the way /api/tags does.
    root = base_url.rstrip("/").removesuffix("/v1")
    response = httpx.get(f"{root}/api/tags", timeout=10.0)
    response.raise_for_status()
    return [m["name"] for m in response.json().get("models", [])]


def list_openai_compatible_models(base_url: str, api_key: str = "") -> list[str]:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    response = httpx.get(f"{base_url.rstrip('/')}/models", headers=headers, timeout=10.0)
    response.raise_for_status()
    return [m["id"] for m in response.json().get("data", [])]
