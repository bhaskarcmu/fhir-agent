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
FHIR_GATEWAY_URL, FHIR_API_KEY, TRIAGE_SERVICE_URL) plus DATABASE_URL
(required -- unlike the CLI, this transport has no in-memory fallback,
since an HTTP session with no persistence isn't a session).
"""

from __future__ import annotations

import os

import anthropic
from fastapi import FastAPI, HTTPException, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel

from agent_platform import create_session, current_trace_id, load_session, save_session, setup_tracing

from .agent import run_query

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

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("CLAUDE_API_KEY", "")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set (CLAUDE_API_KEY is also accepted).")
        if not os.environ.get("FHIR_GATEWAY_URL"):
            raise RuntimeError("FHIR_GATEWAY_URL is not set.")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


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
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    try:
        messages, token_count = load_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown session_id: {session_id}")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=f"Session store unavailable: {exc}")

    stats: dict = {}
    final_text, messages = run_query(
        client, body.query, messages, verbose=False, token_count=token_count, stats=stats
    )
    save_session(session_id, messages, stats.get("token_count", token_count))

    # Read from stats, not current_trace_id() -- run_query's root span has
    # already closed by the time control returns here (see agent.py's own
    # comment on this exact pitfall).
    trace_id = stats.get("trace_id")
    if trace_id:
        response.headers["X-Trace-Id"] = trace_id
    return QueryResponse(response=final_text, trace_id=trace_id)
