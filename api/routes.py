"""
HTTP route handlers for the university QA agent.

Exposes two endpoints:

    POST /chat   -- accepts a natural-language question and returns an answer.
                    Manages multi-turn session state via ``session_store``.
    GET  /health -- verifies the API process and database connection are alive.

Usage::

    from api.routes import router
    app.include_router(router)

Settings used:
    MAX_CLARIFICATION_ROUNDS, MAX_SQL_RETRIES, DB_RESULTS_ROW_LIMIT,
    CONVERSATION_HISTORY_WINDOW (all read from ``config.settings``).
"""

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from agent.state import AgentState
from agent.tracing import Tracer
from api.dependencies import (
    get_connector,
    get_few_shot_examples,
    get_graph,
    get_llm,
    get_schema_context,
)
from api.session_store import ConversationHistory, session_store
from config.settings import settings
from db.base import DatabaseConnector

_logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    """Request body for POST /chat."""

    session_id: str = Field(min_length=1, max_length=256)
    """Client-generated stable identifier for the conversation."""

    question: str = Field(min_length=1, max_length=2000)
    """The user's natural-language question for this turn."""


class ChatResponse(BaseModel):
    """Response body for POST /chat."""

    session_id: str
    """Echo of the session identifier for client correlation."""

    answer: str | None
    """Natural-language answer, clarification question, or error message."""

    status: str
    """Final graph status: ``'done'``, ``'asking_clarification'``, or ``'error'``."""

    trace_id: str
    """Unique run identifier; use to find the matching LangSmith trace."""


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    status: str
    """Always ``'ok'`` — the process is alive."""

    db_ok: bool
    """``True`` if the database connector healthcheck passed."""


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    response: Response,
    graph=Depends(get_graph),
    schema_context: str = Depends(get_schema_context),
    llm=Depends(get_llm),
    few_shot_examples: str = Depends(get_few_shot_examples),
    connector=Depends(get_connector),
) -> ChatResponse:
    """
    Process one turn of a conversation and return the agent's response.

    Loads the session history, builds the initial ``AgentState``, invokes the
    LangGraph graph, and persists the updated state back to the session store.

    Fresh questions reset all clarification fields.  Clarification continuations
    (detected via ``last_status == "asking_clarification"``) carry forward
    ``accumulated_intent``, ``last_clarification_question``, and
    ``ambiguity_count``.

    Args:
        req: The chat request containing ``session_id`` and ``question``.
        graph: Compiled LangGraph graph (injected from ``app.state``).
        schema_context: Prompt-ready schema string (injected from ``app.state``).
        llm: LangChain LLM instance (injected from ``app.state``).
        few_shot_examples: SQL few-shot string (injected from ``app.state``).
        connector: Database connector (injected from ``app.state``).

    Returns:
        ``ChatResponse`` with the answer, terminal status, and trace identifier.

    Raises:
        HTTPException: 500 if the graph raises an unhandled exception.
    """
    history = session_store.get(req.session_id)
    is_continuation = history.last_status == "asking_clarification"

    trace_id = str(uuid4())
    tracer = Tracer(trace_id=trace_id, session_id=req.session_id)

    window = settings.conversation_history_window * 2  # messages = turns × 2
    state: AgentState = {
        "question": req.question,
        "schema_context": schema_context,
        "sql": None,
        "sql_error": None,
        "retry_count": 0,
        "db_results": None,
        "answer": None,
        "status": "analyzing",
        "conversation_history": history.turns[-window:],
        "accumulated_intent": history.accumulated_intent if is_continuation else None,
        "last_clarification": history.last_clarification_question if is_continuation else None,
        "ambiguity_count": history.ambiguity_count if is_continuation else 0,
        "trace_id": trace_id,
        "session_id": req.session_id,
        "tracer": tracer,
    }

    config = {
        "configurable": {
            "llm": llm,
            "connector": connector,
            "few_shot_examples": few_shot_examples,
            "max_clarification_rounds": settings.max_clarification_rounds,
            "max_sql_retries": settings.max_sql_retries,
            "db_results_row_limit": settings.db_results_row_limit,
        }
    }

    try:
        result = await graph.ainvoke(state, config=config)
    except Exception:
        _logger.exception("Graph failed for session=%s trace=%s", req.session_id, trace_id)
        raise HTTPException(status_code=500, detail="Internal agent error")

    new_turns = history.turns + [
        {"role": "user", "content": req.question},
        {"role": "assistant", "content": result.get("answer") or ""},
    ]

    session_store.save(
        req.session_id,
        ConversationHistory(
            last_status=result["status"],
            last_clarification_question=result.get("last_clarification"),
            accumulated_intent=result.get("accumulated_intent"),
            ambiguity_count=result.get("ambiguity_count", 0),
            turns=new_turns,
        ),
    )

    # there are currently 5 error cases:
    # LLM response format error, out of scope, sql validation, db error in sql execution,
    # and too many disambiguation turns
    # for simplicity, all return 422 with detailed error message

    if result["status"] == "error":
        response.status_code = 422

    return ChatResponse(
        session_id=req.session_id,
        answer=result.get("answer"),
        status=result["status"],
        trace_id=trace_id,
    )


@router.get("/health", response_model=HealthResponse)
async def health(connector: DatabaseConnector = Depends(get_connector)) -> HealthResponse:
    """
    Check that the API process and database connection are healthy.

    Args:
        connector: Database connector (injected from ``app.state``).

    Returns:
        ``HealthResponse`` with ``status='ok'`` and the database reachability flag.
    """
    try:
        db_ok = await connector.healthcheck()
    except Exception:
        db_ok = False

    return HealthResponse(status="ok", db_ok=db_ok)
