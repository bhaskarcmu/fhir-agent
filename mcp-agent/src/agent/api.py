"""
Thin HTTP transport for the agent loop (docs/phase6/design.md Section 4.3,
decisions.md H14) -- turns mcp-agent from a CLI process holding a Python
list into an addressable service with sessions, matching triage-service's
own FastAPI convention. Not a UI, not a streaming design: exactly enough
to make sessions testable over HTTP, which M3's session store and M4's
concurrency work both need and a REPL can't exercise.

Every route call re-fetches clinical data through the same tool functions
the CLI uses -- nothing here caches or "recalls" prior clinical state
across turns; the session store persists conversation *history*
(what was asked, what was decided), never a cached FHIR read.

Usage:
  uvicorn agent.api:app --host 0.0.0.0 --port 8010

Environment variables: same as agent.agent (ANTHROPIC_API_KEY/CLAUDE_API_KEY,
FHIR_GATEWAY_URL, FHIR_API_KEY, TRIAGE_SERVICE_URL, and M5's provider seam
LLM_PROVIDER/LLM_MODEL/LLM_BASE_URL/LLM_API_KEY -- docs/phase6/decisions.md
H4) plus DATABASE_URL (required -- unlike the CLI, this transport has no
in-memory fallback, since an HTTP session with no persistence isn't a
session), plus M4's resilience knobs (MAX_CONCURRENT_LLM_QUERIES,
LLM_QUERY_QUEUE_DEADLINE_SECONDS, LLM_CIRCUIT_FAILURE_THRESHOLD,
LLM_CIRCUIT_RESET_SECONDS, LLM_ALERT_TOKENS_PER_MINUTE,
LLM_HARD_BACKSTOP_TOKENS_PER_MINUTE -- all optional, defaults in
agent_platform.resilience). /metrics exposes Prometheus counters/
histograms for LLM token usage, call outcomes, and rate-limit alerts
(docs/phase6/decisions.md H27).
"""

from __future__ import annotations

import os
import threading

import anthropic
import httpx
from fastapi import FastAPI, HTTPException, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import make_asgi_app
from pydantic import BaseModel

from agent_platform import (
    build_llm_client,
    create_session,
    current_trace_id,
    load_session,
    save_session,
    setup_tracing,
)

from .agent import MODEL as MODEL_DEFAULT
from .agent import run_query

# Concurrency limiter for query_session specifically -- not session count
# (M3 left that unbounded on purpose) but LLM calls actually in flight at
# once, which is what really threatens the single Anthropic API key's own
# rate limits and this process's thread pool (docs/phase6/milestone-plan.md
# M4's "concurrent-session-count scaling, deferred from M3"). A bounded
# wait with a deadline, not an unbounded queue: a request that can't get a
# slot within the deadline gets a 503 rather than waiting indefinitely,
# mirroring this repo's existing timeout-not-retry-forever convention
# (HttpTriageClient.java).
_MAX_CONCURRENT_QUERIES = int(os.environ.get("MAX_CONCURRENT_LLM_QUERIES", "10"))
_QUERY_QUEUE_DEADLINE_SECONDS = float(os.environ.get("LLM_QUERY_QUEUE_DEADLINE_SECONDS", "5"))
_query_slots = threading.Semaphore(_MAX_CONCURRENT_QUERIES)

app = FastAPI(
    title="MCP Agent API",
    description=(
        "HTTP transport for the refill-risk-triage agent "
        "(docs/phase6/decisions.md H14). Session-backed via Postgres."
    ),
    version="0.1.0",
)

setup_tracing("mcp-agent-api")
# Server span per incoming request (health, session create) -- setup_tracing()
# above only instruments outbound httpx calls (the CLI's use case, no incoming
# HTTP of its own). query_session's own trace ID instead comes from
# run_query's stats dict, captured before its root span closes -- see there.
FastAPIInstrumentor.instrument_app(app)

# Scraped by Prometheus the same way the Java services' /actuator/prometheus
# already is (docs/phase6/decisions.md H27, observability/prometheus.yml).
app.mount("/metrics", make_asgi_app())

_client: anthropic.Anthropic | object | None = None
_model = MODEL_DEFAULT
_gen_ai_system = "anthropic"


def _get_client() -> anthropic.Anthropic:
    """
    Returns the cached LLM client, building it on first call via
    agent_platform.build_llm_client() (docs/phase6/decisions.md H4, M5) --
    Anthropic by default, or the OpenAI-compatible seam when
    LLM_PROVIDER=openai_compatible. Also caches the resolved model/
    gen_ai_system for _get_model_and_system() to read -- kept as a
    separate function (not folded into this one's return value) so this
    function's own contract -- and every existing test mocking it with
    `return_value=object()` -- stays unchanged.
    """
    global _client, _model, _gen_ai_system
    if _client is None:
        if not os.environ.get("FHIR_GATEWAY_URL"):
            raise RuntimeError("FHIR_GATEWAY_URL is not set.")
        _client, _model, _gen_ai_system = build_llm_client()
    return _client


def _get_model_and_system() -> tuple[str, str]:
    _get_client()  # ensures _model/_gen_ai_system are resolved
    return _model, _gen_ai_system


class SessionCreated(BaseModel):
    session_id: str


class QueryRequest(BaseModel):
    query: str


class QueryResponse(BaseModel):
    response: str
    trace_id: str | None = None


class HealthResponse(BaseModel):
    status: str


@app.get("/health", response_model=HealthResponse, tags=["ops"])
def health(response: Response) -> HealthResponse:
    trace_id = current_trace_id()
    if trace_id:
        response.headers["X-Trace-Id"] = trace_id
    return HealthResponse(status="ok")


@app.post("/sessions", response_model=SessionCreated, tags=["sessions"])
def create_new_session(response: Response) -> SessionCreated:
    """Start a new, empty, persisted session."""
    try:
        session_id = create_session()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=f"Session store unavailable: {exc}")

    trace_id = current_trace_id()
    if trace_id:
        response.headers["X-Trace-Id"] = trace_id
    return SessionCreated(session_id=session_id)


@app.post("/sessions/{session_id}/query", response_model=QueryResponse, tags=["sessions"])
def query_session(session_id: str, body: QueryRequest, response: Response) -> QueryResponse:
    """
    Ask a question within an existing session. Loads prior history, runs
    the same agent loop the CLI uses (including M1's fail-closed enum
    gate and M3's context-budget compaction), persists the result.
    """
    try:
        client = _get_client()
        model, gen_ai_system = _get_model_and_system()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    try:
        messages, token_count = load_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown session_id: {session_id}")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=f"Session store unavailable: {exc}")

    if not _query_slots.acquire(timeout=_QUERY_QUEUE_DEADLINE_SECONDS):
        raise HTTPException(
            status_code=503,
            detail=(
                f"Too many concurrent queries in flight (max {_MAX_CONCURRENT_QUERIES}); "
                "retry shortly."
            ),
        )
    try:
        stats: dict = {}
        final_text, messages = run_query(
            client, body.query, messages, verbose=False, token_count=token_count, stats=stats,
            model=model, gen_ai_system=gen_ai_system,
        )
    except (anthropic.APIError, httpx.HTTPError) as exc:
        # A single call failure below the circuit breaker's threshold --
        # run_query doesn't turn this into a REVIEW decision (only a
        # tripped breaker or exceeded cost backstop does, docs/phase6/
        # decisions.md H20); without this handler it would fall through
        # to FastAPI's default 500, an ungraceful failure mode for a
        # milestone specifically about deploy resilience. 502, not 500:
        # the failure is in the upstream LLM API, not this service's own
        # code. httpx.HTTPError covers the M5 OpenAI-compatible provider,
        # which raises plain httpx errors rather than anthropic's.
        raise HTTPException(status_code=502, detail=f"LLM API error: {exc}")
    finally:
        _query_slots.release()

    save_session(session_id, messages, stats.get("token_count", token_count))

    # Read from stats, not current_trace_id() -- run_query's root span has
    # already closed by the time control returns here (see agent.py's own
    # comment on this exact pitfall).
    trace_id = stats.get("trace_id")
    if trace_id:
        response.headers["X-Trace-Id"] = trace_id
    return QueryResponse(response=final_text, trace_id=trace_id)
